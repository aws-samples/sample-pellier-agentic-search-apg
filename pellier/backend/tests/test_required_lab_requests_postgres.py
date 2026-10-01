"""Execute the request migration against the real scenario schema and seed."""
import json
from pathlib import Path

from tests.test_forensic_dataset_postgres import sql  # noqa: F401

MIGRATIONS = Path(__file__).resolve().parents[3] / 'scripts' / 'migrations'


def test_current_required_requests_preserve_optional_depth_and_custom_variations(sql):
    seed = (MIGRATIONS / '029_live_surface_data.sql').read_text()
    migration = (MIGRATIONS / '056_align_required_lab_requests.sql').read_text()
    sql('''DROP SCHEMA pellier CASCADE; CREATE SCHEMA pellier;
        CREATE TABLE pellier.persona_profiles (persona_id text PRIMARY KEY);
        INSERT INTO pellier.persona_profiles VALUES ('fresh'),('marco'),('anna'),('theo');
        CREATE TABLE pellier.product_catalog ("productId" text PRIMARY KEY);
        INSERT INTO pellier.product_catalog SELECT n::text FROM generate_series(1,60) n;
    ''')
    sql(seed[seed.index('CREATE TABLE IF NOT EXISTS pellier.workshop_scenarios ('):
             seed.index('ALTER TABLE pellier.workshop_scenarios')])
    sql(seed[seed.index('INSERT INTO pellier.workshop_scenarios ('):])
    sql(migration)

    required = json.loads(sql('''SELECT jsonb_object_agg(persona_id, prompts)
        FROM (SELECT persona_id, jsonb_agg(prompt ORDER BY ordinal) AS prompts
        FROM pellier.workshop_scenarios WHERE journey_role='required'
        GROUP BY persona_id) t''').stdout)
    assert len(required['marco']) == 2
    assert 'Brooklyn warehouse' in required['marco'][1]
    assert required['anna'] == ['A housewarming gift for someone who loves slow morning rituals.']
    assert required['theo'] == [
        'Hand-thrown ceramics for a slower morning routine',
        'Show my support ticket history, and the history for customer CUST-JESSICA.',
    ]
    assert sql("SELECT count(*) FROM pellier.workshop_scenarios").stdout.strip() == '20'
    assert sql("""SELECT journey_role, journey_stage IS NULL, preview_product_id
        FROM pellier.workshop_scenarios WHERE persona_id='theo' AND ordinal=4""").stdout.strip() == 'explore|t|37'
    assert sql("""SELECT preview_product_id IS NULL FROM pellier.workshop_scenarios
        WHERE persona_id='theo' AND ordinal=3""").stdout.strip() == 't'

    def snapshot():
        return sql('SELECT jsonb_agg(to_jsonb(s) ORDER BY scenario_id) FROM pellier.workshop_scenarios s').stdout

    before = snapshot()
    sql(migration)
    assert snapshot() == before

    # A participant's changed prompt and role/stage survive the forward migration.
    sql("""UPDATE pellier.workshop_scenarios SET prompt='My custom caller test',
        journey_role='required', journey_stage='prove', preview_product_id='31'
        WHERE persona_id='theo' AND ordinal=3;
        UPDATE pellier.workshop_scenarios SET prompt='My custom comparison',
        journey_role='required', journey_stage='exercise'
        WHERE persona_id='anna' AND ordinal=2;""")
    custom = snapshot()
    sql(migration)
    assert snapshot() == custom
