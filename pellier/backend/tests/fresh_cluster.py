"""A throwaway PostgreSQL 18 + pgvector cluster that runs Pellier's real setup scripts.

The harness runs scripts/setup/database-setup.sh and database-reset.sh themselves,
so the proof covers the commands bootstrap and reset execute, not a copy of them.

The data directory lives under $TMPDIR (on disk). Only the socket directory sits in
a short /tmp path, because macOS caps a unix-socket path at about 104 bytes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
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
    bin: Path
    root: Path
    socket: Path

    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "DB_HOST": str(self.socket),
            "DB_PORT": "5432",
            "DB_NAME": "postgres",
            "DB_USER": "postgres",
            "DB_PASSWORD": "",
            "PYTHON": sys.executable,
            "REPO": str(REPO),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
        }

    def psql(self, sql: str) -> str:
        done = subprocess.run(
            [str(self.bin / "psql"), "-X", "-h", str(self.socket), "-U", "postgres",
             "-d", "postgres", "-At", "-v", "ON_ERROR_STOP=1"],
            input=sql, capture_output=True, text=True, timeout=120,
        )
        if done.returncode:
            raise AssertionError(f"psql failed: {done.stderr}\nSQL: {sql}")
        return done.stdout.strip()

    def stop(self) -> None:
        subprocess.run([str(self.bin / "pg_ctl"), "-D", str(self.root / "data"),
                        "-m", "immediate", "-w", "stop"], capture_output=True)
        shutil.rmtree(self.socket, ignore_errors=True)


def _start_step(args: list[str], log: Path) -> None:
    done = subprocess.run(args, capture_output=True, text=True)
    if done.returncode:
        server_log = log.read_text()[-4000:] if log.is_file() else ""
        raise AssertionError(f"{Path(args[0]).name} failed ({done.returncode}):\n"
                             f"{done.stderr}\n{server_log}")


def start_cluster(root: Path) -> Cluster:
    pg = _pg_bin()
    if pg is None:
        pytest.skip("PostgreSQL 18 with pgvector is required for the fresh-setup harness")
    socket = Path(tempfile.mkdtemp(prefix="pgsock-", dir="/tmp"))
    cluster = Cluster(bin=pg, root=root, socket=socket)
    log = root / "pg.log"
    try:
        _start_step([str(pg / "initdb"), "-D", str(root / "data"), "-U", "postgres",
                     "-A", "trust", "--no-locale", "--encoding=UTF8", "--no-sync"], log)
        _start_step([str(pg / "pg_ctl"), "-D", str(root / "data"), "-l", str(log),
                     "-o", f"-F -h '' -k {socket} "
                           "-c shared_preload_libraries=pg_stat_statements",
                     "-w", "start"], log)
    except BaseException:
        cluster.stop()
        raise
    return cluster


def _run(script: Path, cluster: Cluster) -> None:
    done = subprocess.run(["bash", str(script)], env=cluster.env(),
                          capture_output=True, text=True, timeout=900)
    if done.returncode:
        raise AssertionError(f"{script.name} failed ({done.returncode}):\n"
                             f"{done.stdout[-4000:]}\n{done.stderr[-4000:]}")


def run_setup(cluster: Cluster) -> None:
    _run(SETUP, cluster)


def run_reset(cluster: Cluster) -> None:
    _run(RESET, cluster)


@pytest.fixture(scope="module")
def fresh_db():
    tmp = tempfile.TemporaryDirectory(prefix="pellier-fresh-")
    try:
        cluster = start_cluster(Path(tmp.name))
        try:
            run_setup(cluster)
            yield cluster
        finally:
            cluster.stop()
    finally:
        tmp.cleanup()
