\set ON_ERROR_STOP on
BEGIN;

-- A Gateway authentication failure has no authenticated principal and no
-- Cedar decision. Keep boundary observations separate from policy receipts.
-- The privileged proof runner records sanitized observations and exact-key
-- SQL snapshots. No bearer token, tool payload, or free-text reason is stored.
CREATE TABLE IF NOT EXISTS pellier.governance_boundary_observations (
    observation_id BIGSERIAL PRIMARY KEY,
    proof_run_id TEXT NOT NULL,
    case_name TEXT NOT NULL,
    invocation_id TEXT NOT NULL UNIQUE,
    operation_key TEXT NOT NULL,
    tool TEXT NOT NULL CHECK (tool IN ('initiate_return', 'issue_credit')),
    verified_username TEXT,
    observation JSONB NOT NULL CHECK (jsonb_typeof(observation) = 'object'),
    workshop_run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS governance_boundary_run_idx
    ON pellier.governance_boundary_observations (proof_run_id, observation_id);
DROP TRIGGER IF EXISTS governance_boundary_append_only ON pellier.governance_boundary_observations;
CREATE TRIGGER governance_boundary_append_only
    BEFORE UPDATE OR DELETE ON pellier.governance_boundary_observations
    FOR EACH ROW EXECUTE FUNCTION pellier.reject_evidence_mutation();
REVOKE ALL ON pellier.governance_boundary_observations FROM PUBLIC, pellier_agent, pellier_query;

COMMENT ON TABLE pellier.governance_boundary_observations IS
    'Append-only CLI boundary observations and keyed Aurora snapshots, not provider policy logs.';
COMMIT;
