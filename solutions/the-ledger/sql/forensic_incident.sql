\set ON_ERROR_STOP on
\pset footer off

-- Pellier governed workshop: the auditor's question, after Lab 4.
--
-- "Show me everything that moved money on Jessica's account, and prove the
-- denied attempt moved nothing." Every answer is read from the tables that
-- own it; nothing here writes.
--
--   psql -X -P pager=off -f solutions/the-ledger/sql/forensic_incident.sql

\echo '1. The lineage, from her request to the credit'
-- A shopper's request carries no amount. The investigation that answered it
-- opened one review; a person decided it; one execution turn ran it; the
-- credit names the review it pays.
SELECT r.id                     AS request,
       r.source_turn_id         AS shopper_turn,
       r.status                 AS request_status,
       r.answered_turn_id       AS investigation_turn,
       v.id                     AS review,
       v.status                 AS decision,
       v.decided_by_name        AS decided_by,
       v.execution_turn_id,
       v.last_attempt->>'outcome' AS last_answer,
       c.credit_id,
       c.amount_cents
  FROM pellier.approvals r
  LEFT JOIN pellier.approvals v ON v.id = r.answered_by_review_id
  LEFT JOIN pellier.store_credits c ON c.approval_id = v.id
 WHERE r.tool = 'store_credit_request'
   AND r.customer_id = 'CUST-JESSICA'
 ORDER BY r.id;

\echo ''
\echo '2. Every credit review on her account, and what its key left behind'
-- One row per review, with the write key it admits. An executed credit leaves
-- one tool_audit row and one store_credits row for that key; a call Cedar
-- denied leaves neither, and its stored answer says so.
SELECT v.id                                                     AS review,
       (v.args->>'amount_cents')::int                           AS approved_cents,
       cardinality(v.order_ids)                                 AS orders_covered,
       v.issue,
       v.last_attempt->>'outcome'                               AS last_answer,
       v.last_attempt->>'policy'                                AS policy,
       left(v.last_attempt->>'policy_digest', 23)               AS policy_set,
       k.key                                                    AS idempotency_key,
       (SELECT count(*) FROM pellier.tool_audit
         WHERE args->>'idempotency_key' = k.key)                AS tool_audit_rows,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key = k.key)                         AS store_credits_rows
  FROM pellier.approvals v
 CROSS JOIN LATERAL (SELECT 'operator-review:' || v.id || ':' || left(v.action_hash, 32)) AS k(key)
 WHERE v.tool = 'give_store_credit'
   AND v.customer_id = 'CUST-JESSICA'
 ORDER BY v.id;

\echo ''
\echo '3. The orders each credit covers'
-- An order holds one store_credit_id, so no order is paid twice.
SELECT o.id AS order_id, pc.name AS product, o.amount_paid_cents, o.return_status,
       o.store_credit_id
  FROM pellier.orders o
  JOIN pellier.product_catalog pc ON pc."productId" = o.product_id
 WHERE o.customer_id = 'CUST-JESSICA'
 ORDER BY o.id;
