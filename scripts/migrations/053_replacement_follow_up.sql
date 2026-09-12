-- Provider state and operator follow-up answer different questions. A workflow
-- timeout cannot erase an accepted fulfillment or establish that it shipped.
BEGIN;

ALTER TABLE pellier.replacements
    ADD COLUMN IF NOT EXISTS workflow_resolution TEXT,
    ADD COLUMN IF NOT EXISTS workflow_checked_at TIMESTAMPTZ;
ALTER TABLE pellier.replacements
    DROP CONSTRAINT IF EXISTS replacement_workflow_resolution_check;
ALTER TABLE pellier.replacements
    ADD CONSTRAINT replacement_workflow_resolution_check CHECK (
        workflow_resolution IS NULL
        OR workflow_resolution = 'operator_review_required'
        OR (workflow_resolution = 'shipment_recorded' AND status = 'shipped')
    );

-- This annotates an existing durable shipment; it does not infer one from a
-- Step Functions execution or change any stock, approval, or provider outcome.
UPDATE pellier.replacements SET workflow_resolution = 'shipment_recorded'
 WHERE status = 'shipped' AND workflow_resolution IS DISTINCT FROM 'shipment_recorded';

CREATE INDEX IF NOT EXISTS replacement_workflow_observation
    ON pellier.replacements (workflow_checked_at NULLS FIRST, created_at)
    WHERE workflow_execution_arn IS NOT NULL
      AND workflow_resolution IS NULL AND status <> 'shipped';

GRANT UPDATE (workflow_resolution, workflow_checked_at)
    ON pellier.replacements TO pellier_fulfillment;

COMMIT;
