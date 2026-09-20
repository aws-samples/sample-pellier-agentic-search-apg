"""Execute the fixture's transaction and race two seeders on isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

import pytest
from tests.test_forensic_dataset import _load_seeder


@pytest.fixture
def sql(request):
    temporary = tempfile.TemporaryDirectory(prefix="pellier-seed-", dir="/tmp")
    request.addfinalizer(temporary.cleanup)
    tmp_path = Path(temporary.name)
    candidates = [Path(os.environ.get('PG_BIN', '/nonexistent')),
                  Path('/opt/homebrew/opt/postgresql@17/bin'),
                  *sorted(Path('/usr/lib/postgresql').glob('*/bin'), reverse=True)]
    found = shutil.which('initdb')
    if found:
        candidates.insert(0, Path(found).resolve().parent)
    binaries = next((p for p in candidates if all((p / name).is_file() for name in ('postgres', 'pg_ctl', 'initdb', 'psql'))), None)
    if binaries is None:
        pytest.skip('PostgreSQL server binaries required for isolated transaction proof')
    socket = tmp_path / 'socket'
    socket.mkdir()
    data = tmp_path / 'data'
    def run(args, **kw):
        return subprocess.run(args, capture_output=True, text=True, timeout=30, **kw)
    run([str(binaries/'initdb'), '-D', str(data), '-U', 'proof', '-A', 'trust',
         '--no-locale', '--encoding=UTF8', '--no-sync'], check=True)
    run([str(binaries/'pg_ctl'), '-D', str(data), '-l', str(tmp_path/'postgres.log'),
         '-o', f"-F -h '' -k {socket}", '-w', 'start'], check=True)
    def execute(statement, check=True):
        return run([str(binaries/'psql'), '-X', '-h', str(socket), '-U', 'proof',
                    '-d', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1'], input=statement, check=check)
    try:
        execute('''CREATE SCHEMA pellier;
          CREATE TABLE pellier.orders (id bigserial PRIMARY KEY, customer_id text, product_id text, quantity int);
          CREATE TABLE pellier.returns (customer_id text, product_id text, reason text, status text, quantity int, order_id bigint REFERENCES pellier.orders);
          CREATE TABLE pellier.governed_turn_receipts (turn_id text PRIMARY KEY, session_id text, principal_sub text,
            principal_verified bool, rail text, policy_events jsonb, terminal_status text, terminal_outcome jsonb, latency_ms int);
          CREATE TABLE pellier.tool_audit (audit_id bigserial PRIMARY KEY, session_id text, tool text, caller text, args jsonb, result jsonb, latency_ms int);
          CREATE TABLE pellier.governed_receipts (audit_id bigint, session_id text, principal_id text, principal_label text,
            tool text, caller text, decision text, args jsonb, policy_name text);
          INSERT INTO pellier.orders(customer_id,product_id,quantity) VALUES ('CUST-THEO','ordinary-order',7);
        ''')
        yield execute
    finally:
        run([str(binaries/'pg_ctl'), '-D', str(data), '-m', 'immediate', '-w', 'stop'], check=True)


def test_concurrent_seed_rerun_and_clear_preserve_business_state(sql):
    seeder = _load_seeder()
    sql(seeder.clear_sql())
    assert sql('SELECT count(*) FROM pellier.orders').stdout.strip() == '1'
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(sql, [seeder.seed_sql(), seeder.seed_sql()]))
    sql(seeder.seed_sql())
    assert sql('''SELECT (SELECT count(*) FROM pellier.orders),
      (SELECT count(*) FROM pellier.returns), (SELECT count(*) FROM pellier.governed_turn_receipts),
      (SELECT count(*) FROM pellier.tool_audit), (SELECT count(*) FROM pellier.governed_receipts)''').stdout.strip() == '2|1|3|2|1'
    assert sql('''SELECT count(*) FROM pellier.returns r JOIN pellier.orders o ON o.id=r.order_id
      WHERE o.product_id='ordinary-order' ''').stdout.strip() == '0'
    assert sql(seeder.clear_sql(), check=False).returncode != 0
    assert sql("SELECT quantity FROM pellier.orders WHERE product_id='ordinary-order'").stdout.strip() == '7'
    assert sql('SELECT count(*) FROM pellier.returns').stdout.strip() == '1'
