"""Run proof candidate selection against real exhausted and rejected returns."""
from tests.test_forensic_dataset_postgres import sql  # noqa: F401
from tests.test_identity_principal_selection import _load_proof_driver


def test_preflight_excludes_consumed_quantity_but_not_rejected_returns(sql, monkeypatch):
    sql("""CREATE TABLE pellier.product_catalog(product_id text PRIMARY KEY, name text);
      INSERT INTO pellier.product_catalog VALUES ('101','Exhausted'),('102','Available'),('103','Also exhausted');
      INSERT INTO pellier.orders(customer_id,product_id,quantity) VALUES
        ('CUST-JESSICA','101',1),('CUST-JESSICA','102',2),('CUST-JESSICA','103',1);
      INSERT INTO pellier.returns(customer_id,product_id,quantity,status) VALUES
        ('CUST-JESSICA','101',1,'requested'),('CUST-JESSICA','102',2,'rejected'),('CUST-JESSICA','103',1,'approved');""")
    driver = _load_proof_driver()
    def query(_cfg, statement):
        result = sql(statement, check=False)
        return result.returncode, result.stdout, result.stderr
    monkeypatch.setattr(driver, '_psql', query)
    assert driver._eligible_products({}) == [(102, 'Available')]
    assert driver._resolve_product({}, 101)[0] is None
    assert driver._resolve_product({}, None)[0] == 102


def test_rls_probe_uses_valid_business_input_and_always_rolls_back(sql, monkeypatch):
    sql("""CREATE ROLE pellier_agent NOBYPASSRLS;
      GRANT USAGE ON SCHEMA pellier TO pellier_agent;
      GRANT SELECT, INSERT ON pellier.returns TO pellier_agent;
      ALTER TABLE pellier.returns ADD CHECK (reason IN ('damaged','other'));
      ALTER TABLE pellier.returns ALTER COLUMN status SET DEFAULT 'pending';
      ALTER TABLE pellier.returns ADD CHECK (status IN ('pending','approved','rejected'));
      ALTER TABLE pellier.returns ENABLE ROW LEVEL SECURITY;
      CREATE POLICY scoped ON pellier.returns TO pellier_agent
        USING (customer_id = CASE current_setting('pellier.principal_sub',true)
          WHEN 'jessica' THEN 'CUST-JESSICA' ELSE 'CUST-MARCO' END);""")
    driver = _load_proof_driver()
    def query(_cfg, statement, *, role=None):
        result = sql(f'SET ROLE {role}; ' + statement, check=False)
        return result.returncode, result.stdout, result.stderr
    monkeypatch.setattr(driver, '_psql', query)
    owner = driver._rls_write({}, 'jessica', 102)
    denied = driver._rls_write({}, 'marco', 102)
    assert owner['queried'] and not owner['refused'], owner
    assert denied['queried'] and denied['refused'] and denied['sqlstate'] == '42501', denied
    assert sql('SELECT count(*) FROM pellier.returns').stdout.strip() == '0'
