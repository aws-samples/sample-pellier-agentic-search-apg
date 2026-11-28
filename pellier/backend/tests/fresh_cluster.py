"""A throwaway PostgreSQL 18 + pgvector cluster that runs Pellier's real setup scripts.

The harness runs scripts/setup/database-setup.sh and database-reset.sh themselves,
so the proof covers the commands bootstrap and reset execute, not a copy of them.

The fresh_db fixture seeds one cluster per pytest session and gives each test module a
private copy after a clean shutdown. Tests of setup itself can still start an empty cluster.
Data lives under $TMPDIR. Sockets use short /tmp paths for the macOS path-length limit.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SETUP = REPO / "scripts" / "setup" / "database-setup.sh"
RESET = REPO / "scripts" / "setup" / "database-reset.sh"


def _pg_bin() -> Path | None:
    candidates = [Path(os.environ.get("PG_BIN", "/nonexistent"))]
    found = shutil.which("initdb")
    if found:
        candidates.insert(0, Path(found).resolve().parent)
    candidates.append(Path("/opt/homebrew/opt/postgresql@18/bin"))
    for path in candidates:
        if all((path / name).is_file() for name in ("initdb", "pg_ctl", "psql", "pg_config")):
            share = subprocess.run([str(path / "pg_config"), "--sharedir"],
                                   capture_output=True, text=True).stdout.strip()
            if (Path(share) / "extension" / "vector.control").is_file():
                return path
    return None


@dataclass
class Cluster:
    """A running throwaway cluster. ``user`` and ``database`` are who the setup scripts and
    ``psql`` connect as; ``dataclasses.replace`` gives the same cluster as another login."""

    bin: Path
    root: Path
    socket: Path
    user: str = "postgres"
    database: str = "postgres"

    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "DB_HOST": str(self.socket),
            "DB_PORT": "5432",
            "DB_NAME": self.database,
            "DB_USER": self.user,
            "DB_PASSWORD": "",
            "PYTHON": sys.executable,
            "REPO": str(REPO),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
        }

    def psql(self, sql: str) -> str:
        done = subprocess.run(
            [str(self.bin / "psql"), "-X", "-h", str(self.socket), "-U", self.user,
             "-d", self.database, "-At", "-v", "ON_ERROR_STOP=1"],
            input=sql, capture_output=True, text=True, timeout=120,
        )
        if done.returncode:
            raise AssertionError(f"psql failed: {done.stderr}\nSQL: {sql}")
        return done.stdout.strip()

    def stop(self, *, clean: bool = False) -> None:
        command = [str(self.bin / "pg_ctl"), "-D", str(self.root / "data"),
                   "-m", "fast" if clean else "immediate", "-w", "stop"]
        if clean:
            _start_step(command, self.root / "pg.log")
        else:
            subprocess.run(command, capture_output=True)
        shutil.rmtree(self.socket, ignore_errors=True)


def _start_step(args: list[str], log: Path) -> None:
    done = subprocess.run(args, capture_output=True, text=True)
    if done.returncode:
        server_log = log.read_text()[-4000:] if log.is_file() else ""
        raise AssertionError(f"{Path(args[0]).name} failed ({done.returncode}):\n"
                             f"{done.stderr}\n{server_log}")


def _start_server(cluster: Cluster, server_options: str = "") -> None:
    log = cluster.root / "pg.log"
    _start_step([str(cluster.bin / "pg_ctl"), "-D", str(cluster.root / "data"), "-l", str(log),
                 "-o", f"-F -h '' -k {cluster.socket} {server_options}".rstrip(),
                 "-w", "start"], log)


def start_cluster(root: Path, server_options: str = "") -> Cluster:
    """Start a throwaway cluster; ``server_options`` adds ``-c name=value`` settings,
    such as preloading pg_stat_statements the way the workshop's Aurora cluster does."""
    pg = _pg_bin()
    if pg is None:
        message = "PostgreSQL 18 with pgvector is required for the fresh-setup harness"
        if os.environ.get("PELLIER_REQUIRE_POSTGRES"):
            # The workflow's Postgres job installs the cluster on purpose; a silent skip
            # there would pass the row-level security, credit replay and reset proofs
            # without running them.
            raise AssertionError(f"{message}; set PG_BIN to its bin directory")
        pytest.skip(message)
    socket = Path(tempfile.mkdtemp(prefix="pgsock-", dir="/tmp"))
    cluster = Cluster(bin=pg, root=root, socket=socket)
    log = root / "pg.log"
    try:
        _start_step([str(pg / "initdb"), "-D", str(root / "data"), "-U", "postgres",
                     "-A", "trust", "--no-locale", "--encoding=UTF8", "--no-sync"], log)
        _start_server(cluster, server_options)
    except BaseException:
        cluster.stop()
        raise
    return cluster


def _run(script: Path, cluster: Cluster) -> subprocess.CompletedProcess:
    done = subprocess.run(["bash", str(script)], env=cluster.env(),
                          capture_output=True, text=True, timeout=900)
    if done.returncode:
        raise AssertionError(f"{script.name} failed ({done.returncode}):\n"
                             f"{done.stdout[-4000:]}\n{done.stderr[-4000:]}")
    return done


def run_setup(cluster: Cluster) -> subprocess.CompletedProcess:
    return _run(SETUP, cluster)


def run_reset(cluster: Cluster) -> subprocess.CompletedProcess:
    return _run(RESET, cluster)


_TEMPLATE = pytest.StashKey[Cluster]()


def _stopped_template(session: pytest.Session) -> Cluster:
    # Consumers import fresh_db directly, so share the template through their pytest session.
    if _TEMPLATE in session.stash:
        return session.stash[_TEMPLATE]

    with ExitStack() as cleanup:
        root = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="pellier-template-"))
        cluster = start_cluster(Path(root))
        try:
            run_setup(cluster)
            cluster.stop(clean=True)
        except BaseException:
            cluster.stop()
            raise
        session.addfinalizer(cleanup.pop_all().close)
    session.stash[_TEMPLATE] = cluster
    return cluster


@contextmanager
def fresh_db_copy(session: pytest.Session) -> Iterator[Cluster]:
    """Run a private copy of this session's cleanly stopped, seeded cluster."""
    template = _stopped_template(session)
    with tempfile.TemporaryDirectory(prefix="pellier-fresh-") as temporary:
        root = Path(temporary)
        source = template.root / "data"
        if sys.platform == "darwin":
            _start_step(["cp", "-cR", str(source), str(root / "data")], root / "pg.log")
        elif sys.platform.startswith("linux"):
            _start_step(["cp", "-a", "--reflink=auto", str(source), str(root / "data")],
                        root / "pg.log")
        else:
            shutil.copytree(source, root / "data", symlinks=True)
        socket = Path(tempfile.mkdtemp(prefix="pgsock-", dir="/tmp"))
        cluster = Cluster(bin=template.bin, root=root, socket=socket)
        try:
            _start_server(cluster)
            yield cluster
        finally:
            cluster.stop()


@pytest.fixture(scope="module")
def fresh_db(request: pytest.FixtureRequest) -> Iterator[Cluster]:
    with fresh_db_copy(request.session) as cluster:
        yield cluster
