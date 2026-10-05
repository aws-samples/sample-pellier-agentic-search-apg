-- Pellier's whole database: one schema, ten tables, one application role.
--
-- Read it top to bottom. The store's data comes first (catalog, stock,
-- customers, orders, policies, tickets), then the governed money path
-- (approvals, store credits), then the two evidence tables (tool_audit,
-- retrieval_receipts), then who may read what (the role, its grants and
-- row-level security).
--
-- Applied once, to an empty database, by scripts/setup/database-setup.sh.
-- The seed follows: scripts/seed_pellier_catalog.py loads the 100 products,
-- then scripts/migrations/002_seed.sql loads everything else. A reset drops
-- the schema and runs the same three steps, so a reset database is a fresh one.

\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS vector;   -- embeddings: Cohere Embed v4, 1024 numbers
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- fast "name contains" lookups

CREATE SCHEMA pellier;


-- ===========================================================================
-- 1. The catalog: 100 products
-- ===========================================================================
-- "productId" keeps the camelCase name the API returns; product_id is the
-- same value for SQL you type by hand. persona_id groups a product into a
-- storefront edit (marco, anna, theo, house, fresh, signature) and
-- storefront_rank orders that edit's grid.

CREATE TABLE pellier.product_catalog (
    "productId"     text PRIMARY KEY,
    product_id      text GENERATED ALWAYS AS ("productId") STORED UNIQUE,
    name            text NOT NULL,
    brand           text NOT NULL,
    color           text,
    price           numeric(10,2) NOT NULL,
    description     text,
    category        text,                     -- the store department
    tags            jsonb NOT NULL DEFAULT '[]',
    materials       jsonb NOT NULL DEFAULT '[]',
    rating          numeric(3,2) NOT NULL DEFAULT 0,
    reviews         integer NOT NULL DEFAULT 0,
    "imgUrl"        text,
    badge           text,
    tier            integer NOT NULL DEFAULT 1,
    quantity        integer NOT NULL DEFAULT 0,  -- units across all warehouses
    embedding       vector(1024),
    persona_id      text,
    storefront_rank smallint,
    -- Full-text search: name and brand weigh most, the description least.
    description_tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(name, '')), 'A')
     || setweight(to_tsvector('english', coalesce(brand, '')), 'A')
     || setweight(to_tsvector('english', coalesce(category, '')), 'B')
     || setweight(to_tsvector('english', coalesce(color, '')), 'B')
     || setweight(to_tsvector('english',
            coalesce(jsonb_path_query_array(tags, '$[*]')::text, '')), 'C')
     || setweight(to_tsvector('english', coalesce(description, '')), 'D')
    ) STORED,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Vector search: HNSW on cosine distance, pgvector's default build settings.
CREATE INDEX product_catalog_embedding_hnsw ON pellier.product_catalog
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
-- Keyword search: the full-text column above.
CREATE INDEX product_catalog_description_tsv_gin ON pellier.product_catalog
    USING gin (description_tsv);
-- "Name contains" and "department contains" lookups (check_stock, browse_department).
CREATE INDEX product_catalog_name_trgm ON pellier.product_catalog
    USING gin (lower(name) gin_trgm_ops);
CREATE INDEX product_catalog_category_trgm ON pellier.product_catalog
    USING gin (lower(category) gin_trgm_ops);
CREATE INDEX product_catalog_storefront_edit ON pellier.product_catalog
    (persona_id, storefront_rank) WHERE storefront_rank IS NOT NULL;

CREATE FUNCTION pellier.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

CREATE TRIGGER product_catalog_set_updated_at
    BEFORE UPDATE ON pellier.product_catalog
    FOR EACH ROW EXECUTE FUNCTION pellier.set_updated_at();


-- ===========================================================================
-- 2. Stock: one row per product per warehouse
-- ===========================================================================
-- Three warehouses, so 300 rows. A warehouse's name, city and ship window
-- sit on every row, which is all check_stock needs from one SELECT.

CREATE TABLE pellier.warehouse_inventory (
    product_id      text NOT NULL REFERENCES pellier.product_catalog ("productId"),
    warehouse_code  text NOT NULL,           -- BK-01, ATX-02, PDX-01
    warehouse_name  text NOT NULL,           -- Brooklyn, Austin, Portland
    city            text NOT NULL,           -- Brooklyn, NY
    ship_window_min integer NOT NULL,        -- business days, low end
    ship_window_max integer NOT NULL,        -- business days, high end
    quantity        integer NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    PRIMARY KEY (product_id, warehouse_code),
    CHECK (ship_window_min >= 0 AND ship_window_max >= ship_window_min)
);


-- ===========================================================================
-- 3. Customers: Anna, Marco, Theo and Jessica
-- ===========================================================================
-- cognito_username is the sign-in name, in lowercase. It ties a verified
-- token to its customer, and row-level security (section 11) reads it. It is
-- never empty, so a session that names no one (an empty name) matches no
-- customer.

CREATE TABLE pellier.customers (
    id                  text PRIMARY KEY CHECK (id ~ '^CUST-[A-Z]+$'),
    name                text NOT NULL,
    cognito_username    text NOT NULL UNIQUE CHECK (cognito_username ~ '^[a-z0-9._-]+$'),
    preferences_summary text
);


-- ===========================================================================
-- 4. Orders, each with where it shipped and whether it came back
-- ===========================================================================
-- return_status is NULL until the customer sends the item back:
--   requested  the customer asked to return it
--   received   it came back; staff may credit it
--   refunded   it came back and was paid back to the card, so it is not credited
-- store_credit_id names the one store credit that covers a received return
-- (section 8 adds the reference once store_credits exists).

CREATE TABLE pellier.orders (
    id                bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id       text NOT NULL REFERENCES pellier.customers (id),
    product_id        text NOT NULL REFERENCES pellier.product_catalog ("productId"),
    quantity          integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
    amount_paid_cents integer NOT NULL CHECK (amount_paid_cents >= 0),
    currency          char(3) NOT NULL DEFAULT 'USD',
    ship_to           text NOT NULL,
    placed_at         timestamptz NOT NULL DEFAULT now(),
    return_status     text CHECK (return_status IN ('requested', 'received', 'refunded')),
    store_credit_id   bigint
);

CREATE INDEX orders_customer ON pellier.orders (customer_id, placed_at DESC);


-- ===========================================================================
-- 5. Return policies, one per store department
-- ===========================================================================

CREATE TABLE pellier.return_policies (
    category_name      text PRIMARY KEY,     -- a department, or 'default'
    return_window_days integer NOT NULL,
    conditions         text NOT NULL,
    refund_method      text NOT NULL
);


-- ===========================================================================
-- 6. Support tickets
-- ===========================================================================

CREATE TABLE pellier.support_tickets (
    ticket_id   text PRIMARY KEY,            -- TKT-2026-5021
    customer_id text NOT NULL REFERENCES pellier.customers (id),
    subject     text NOT NULL,
    status      text NOT NULL CHECK (status IN ('open', 'pending', 'resolved', 'closed')),
    channel     text NOT NULL DEFAULT 'email',
    last_note   text,
    opened_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    -- A resolved or closed ticket says when; an open one does not.
    CHECK ((status IN ('resolved', 'closed')) = (resolved_at IS NOT NULL))
);

CREATE INDEX support_tickets_customer ON pellier.support_tickets (customer_id, opened_at DESC);


-- ===========================================================================
-- 7. Approvals: what a person decides
-- ===========================================================================
-- Two kinds of row:
--
--   store_credit_request  a shopper asked for credit in chat. It names no
--                         amount, so nobody can approve it. It is open until
--                         staff investigate the case, then answered.
--   give_store_credit     the exact credit the Operator's Planner proposed:
--                         args holds customer_id, amount_cents and reason,
--                         action_hash fingerprints them, and order_ids lists
--                         the returned orders it covers. Nadia approves or
--                         declines it.
--
-- The lineage reads down one table: a request's source_turn_id is the shopper's
-- turn, answered_turn_id the investigation, answered_by_review_id the credit
-- review that investigation opened, and that review's execution_turn_id the
-- run that wrote the credit.
--
-- last_attempt is the desk's record of the last time a person ran the
-- approved credit, overwritten on each attempt. Only an allowed or denied
-- attempt on the Gateway rail is an answer from the Gateway:
--   outcome          allowed, denied, refused (the desk sent nothing) or failed
--   at               when the answer came back
--   idempotency_key  the review's write key
--   rail, policy     where it ran and the policy reading at the time
--   engine_mode, matching_forbids, policy_engine_id, policy_digest
--                    the engine's attribution, when it could be read
--   detail           the Gateway's words for a denial, the error for a
--                    failure, or what was missing for a refusal
-- It is a record of the answer, not proof that anything ran: tool_audit holds
-- what ran, and store_credits what was paid.

CREATE TABLE pellier.approvals (
    id                bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id       text NOT NULL REFERENCES pellier.customers (id),
    tool              text NOT NULL CHECK (tool IN ('give_store_credit', 'store_credit_request')),
    status            text NOT NULL,
    args              jsonb NOT NULL DEFAULT '{}',
    action_hash       text,
    order_ids         bigint[] NOT NULL DEFAULT '{}',
    issue             text,                  -- what the case is about, shown to staff
    recommendation    jsonb,                 -- the Planner's rationale and items, for the desk
    source_turn_id    text,
    requested_by_sub  text,                  -- the verified subject that asked, if any
    requester_kind    text NOT NULL DEFAULT 'unverified'
                      CHECK (requester_kind IN ('shopper', 'operator', 'unverified')),
    requested_at      timestamptz NOT NULL DEFAULT now(),
    decided_by        text,                  -- the staff member's verified subject
    decided_by_name   text,                  -- and their username, for the record
    decided_at        timestamptz,
    execution_turn_id text,                  -- set once, when the approved credit first runs
    last_attempt      jsonb,                 -- the desk's last execute attempt and its answer
    answered_turn_id  text,
    answered_by_review_id bigint REFERENCES pellier.approvals (id),

    CONSTRAINT approvals_status_by_kind CHECK (
           (tool = 'give_store_credit'    AND status IN ('pending', 'approved', 'rejected'))
        OR (tool = 'store_credit_request' AND status IN ('open', 'answered'))),
    -- A decision names who decided and when; nothing else carries one.
    CONSTRAINT approvals_decision_recorded CHECK (CASE
        WHEN status IN ('approved', 'rejected') THEN decided_by IS NOT NULL AND decided_at IS NOT NULL
        ELSE decided_by IS NULL AND decided_at IS NULL END),
    CONSTRAINT approvals_runs_only_when_approved CHECK (
        execution_turn_id IS NULL OR status = 'approved'),
    CONSTRAINT approvals_answer_recorded CHECK (
        (status = 'answered') = (answered_turn_id IS NOT NULL))
);

-- One live review per exact credit: a second proposal of the same credit
-- resolves to the first instead of opening a second card. The key is the
-- terms (customer, amount, reason), not the orders, so two live reviews with
-- different terms can cover the same order. The Planner does not propose
-- one, and if a person approved both, apply_store_credit's order check pays
-- only the first: an order holds one store_credit_id.
CREATE UNIQUE INDEX approvals_one_live_review ON pellier.approvals (customer_id, tool, action_hash)
    WHERE status IN ('pending', 'approved');
-- One open credit request per customer.
CREATE UNIQUE INDEX approvals_one_open_request ON pellier.approvals (customer_id)
    WHERE tool = 'store_credit_request' AND status = 'open';


-- ===========================================================================
-- 8. Store credits: money given back, one row per approved review
-- ===========================================================================
-- Positive whole cents up to $500. That ceiling is a safety check on any
-- credit. The $100 authorization limit is Lab 4's Cedar policy, a separate
-- control, so a $100.01 credit is valid here and only the policy refuses it.

CREATE TABLE pellier.store_credits (
    credit_id       bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    approval_id     bigint NOT NULL UNIQUE REFERENCES pellier.approvals (id),
    customer_id     text NOT NULL REFERENCES pellier.customers (id),
    amount_cents    integer NOT NULL CHECK (amount_cents BETWEEN 1 AND 50000),
    currency        text NOT NULL DEFAULT 'USD',
    reason          text NOT NULL,
    issued_by       text,
    idempotency_key text NOT NULL UNIQUE,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX store_credits_customer ON pellier.store_credits (customer_id, created_at DESC);

-- An order holds at most one credit id, so no order can be credited twice.
ALTER TABLE pellier.orders
    ADD CONSTRAINT orders_store_credit_id_fkey
    FOREIGN KEY (store_credit_id) REFERENCES pellier.store_credits (credit_id);

-- The only way a credit is written. It refuses, with a readable status, any
-- credit a person did not approve exactly, and any order already credited.
-- The rules live here rather than in the application, so every caller is held
-- to them: the Operator desk, the Gateway Lambda, and anyone typing SQL.
--
-- The write key is the approved review's own:
--   operator-review:<review id>:<first 32 characters of its action_hash>
-- Retrying that key returns the first credit instead of writing a second.
CREATE FUNCTION pellier.apply_store_credit(
    p_idempotency_key text,
    p_customer_id     text,
    p_amount_cents    integer,
    p_reason          text,
    p_issued_by       text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_key      text := btrim(coalesce(p_idempotency_key, ''));
    v_reason   text := btrim(coalesce(p_reason, ''));
    v_args     jsonb;
    v_existing pellier.store_credits%ROWTYPE;
    v_review   pellier.approvals%ROWTYPE;
    v_orders   bigint[];
    v_credit   bigint;
    v_replay   boolean := false;
BEGIN
    IF v_key = '' THEN
        RETURN jsonb_build_object('status', 'error', 'message', 'idempotency_key is required.');
    END IF;
    IF p_amount_cents IS NULL OR p_amount_cents <= 0 THEN
        RETURN jsonb_build_object('status', 'error', 'message', 'Credit amount must be positive.');
    END IF;
    IF p_amount_cents > 50000 THEN
        RETURN jsonb_build_object('status', 'policy_blocked', 'message',
            format('Credit of $%s exceeds the $500.00 safety ceiling.',
                   to_char(p_amount_cents / 100.0, 'FM999999.00')));
    END IF;
    IF v_reason = '' THEN
        RETURN jsonb_build_object('status', 'error', 'message', 'A reason is required for a credit.');
    END IF;
    v_args := jsonb_build_object('customer_id', p_customer_id,
                                 'amount_cents', p_amount_cents, 'reason', v_reason);

    -- Lock this customer's approved reviews, so a concurrent retry of the same
    -- key waits for the first write and then finds it.
    PERFORM 1 FROM pellier.approvals
     WHERE customer_id = p_customer_id AND tool = 'give_store_credit' AND status = 'approved'
       FOR UPDATE;

    SELECT * INTO v_existing FROM pellier.store_credits WHERE idempotency_key = v_key;
    IF FOUND THEN
        -- 1. A retry of a key already used returns the first credit.
        IF jsonb_build_object('customer_id', v_existing.customer_id,
                              'amount_cents', v_existing.amount_cents,
                              'reason', v_existing.reason) <> v_args THEN
            RETURN jsonb_build_object('status', 'idempotency_conflict', 'message',
                'Idempotency key was already used with different arguments.');
        END IF;
        v_credit := v_existing.credit_id;
        v_replay := true;
    ELSE
        -- 2. A person approved exactly this credit, and this is that review's key.
        IF NOT EXISTS (SELECT 1 FROM pellier.approvals
                        WHERE customer_id = p_customer_id AND tool = 'give_store_credit'
                          AND status = 'approved') THEN
            RETURN jsonb_build_object('status', 'approval_required', 'denied_by', 'approval_guard',
                'message', format('No confirmed review approves a store credit for %s. '
                                  'A person approves the exact credit before it is written.',
                                  p_customer_id));
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pellier.approvals
                        WHERE customer_id = p_customer_id AND tool = 'give_store_credit'
                          AND status = 'approved' AND args = v_args) THEN
            RETURN jsonb_build_object('status', 'approval_mismatch', 'denied_by', 'approval_guard',
                'message', format('The confirmed review for %s approves different arguments. '
                                  'Amount, reason and customer must match the approval exactly.',
                                  p_customer_id));
        END IF;
        SELECT * INTO v_review FROM pellier.approvals
         WHERE customer_id = p_customer_id AND tool = 'give_store_credit'
           AND status = 'approved' AND args = v_args
           AND v_key = 'operator-review:' || id || ':' || left(action_hash, 32);
        IF NOT FOUND THEN
            RETURN jsonb_build_object('status', 'approval_key_mismatch', 'denied_by', 'approval_guard',
                'message', format('The confirmed review for %s approves these arguments under '
                                  'its own write key only. One approval admits one credit, and '
                                  'this key is not that review''s key.', p_customer_id));
        END IF;

        -- 3. Every order the review covers is this customer's, came back, and
        --    holds no credit yet.
        PERFORM 1 FROM pellier.orders WHERE id = ANY (v_review.order_ids) FOR UPDATE;
        SELECT array_agg(id ORDER BY id) INTO v_orders FROM pellier.orders
         WHERE id = ANY (v_review.order_ids) AND customer_id = p_customer_id
           AND return_status = 'received' AND store_credit_id IS NULL;
        IF cardinality(v_review.order_ids) = 0
           OR coalesce(cardinality(v_orders), 0) <> cardinality(v_review.order_ids) THEN
            RETURN jsonb_build_object('status', 'not_creditable', 'denied_by', 'order_guard',
                'message', 'A credit covers received returns that no other credit covers, '
                           'and this review names an order that is not one.',
                'order_ids', to_jsonb(v_review.order_ids));
        END IF;

        INSERT INTO pellier.store_credits
               (approval_id, customer_id, amount_cents, reason, issued_by, idempotency_key)
        VALUES (v_review.id, p_customer_id, p_amount_cents, v_reason,
                nullif(btrim(coalesce(p_issued_by, '')), ''), v_key)
        RETURNING credit_id INTO v_credit;
        UPDATE pellier.orders SET store_credit_id = v_credit WHERE id = ANY (v_orders);
    END IF;

    RETURN (
        SELECT jsonb_build_object(
            'status', 'success',
            'credit_id', c.credit_id,
            'review_id', c.approval_id,
            'customer_id', c.customer_id,
            'customer_name', cu.name,
            'amount_cents', c.amount_cents,
            'amount', to_char(c.amount_cents / 100.0, 'FM999999.00'),
            'balance_cents', (SELECT sum(amount_cents) FROM pellier.store_credits
                               WHERE customer_id = c.customer_id),
            'reason', c.reason,
            'issued_by', c.issued_by,
            'order_ids', (SELECT coalesce(jsonb_agg(o.id ORDER BY o.id), '[]')
                            FROM pellier.orders o WHERE o.store_credit_id = c.credit_id),
            'idempotent_replay', v_replay)
          FROM pellier.store_credits c
          JOIN pellier.customers cu ON cu.id = c.customer_id
         WHERE c.credit_id = v_credit);
END $$;

-- The same rules hold for any other insert, the owner's included. A credit row
-- belongs to an approved credit review with exactly its terms, carries that
-- review's own key, and covers received returns that no other credit covers.
-- apply_store_credit checks all of this first so it can answer with a
-- readable status; this trigger refuses any insert that gets past it. It is a
-- BEFORE INSERT trigger: it covers how a credit row is written, not a later
-- UPDATE or DELETE of one, which nothing in Pellier issues.
CREATE FUNCTION pellier.store_credits_require_approval() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_review pellier.approvals%ROWTYPE;
BEGIN
    SELECT * INTO v_review FROM pellier.approvals WHERE id = NEW.approval_id;
    IF NOT FOUND
       OR v_review.tool IS DISTINCT FROM 'give_store_credit'
       OR v_review.status IS DISTINCT FROM 'approved'
       OR v_review.customer_id IS DISTINCT FROM NEW.customer_id
       OR v_review.args IS DISTINCT FROM jsonb_build_object(
              'customer_id', NEW.customer_id, 'amount_cents', NEW.amount_cents,
              'reason', NEW.reason)
       OR NEW.idempotency_key IS DISTINCT FROM
              'operator-review:' || v_review.id || ':' || left(v_review.action_hash, 32) THEN
        RAISE EXCEPTION 'store credit for % is not the credit an approved review names, under its key',
                        NEW.customer_id
            USING ERRCODE = 'check_violation', CONSTRAINT = 'store_credits_require_approval';
    END IF;
    IF cardinality(v_review.order_ids) = 0 OR EXISTS (
           SELECT 1 FROM unnest(v_review.order_ids) AS covered (order_id)
             LEFT JOIN pellier.orders o ON o.id = covered.order_id
            WHERE o.id IS NULL
               OR o.customer_id IS DISTINCT FROM NEW.customer_id
               OR o.return_status IS DISTINCT FROM 'received'
               OR o.store_credit_id IS NOT NULL) THEN
        RAISE EXCEPTION 'store credit for % covers an order that is not an uncredited received return',
                        NEW.customer_id
            USING ERRCODE = 'check_violation', CONSTRAINT = 'store_credits_require_approval';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER store_credits_require_approval
    BEFORE INSERT ON pellier.store_credits
    FOR EACH ROW EXECUTE FUNCTION pellier.store_credits_require_approval();


-- ===========================================================================
-- 9. tool_audit: one row per tool call that ran
-- ===========================================================================
-- A row is written when a tool runs, and completed once with its result and
-- latency. After that it never changes, and no row is ever deleted. A call
-- Cedar denies never runs, so it leaves no row: the absence is the proof.
-- build_fingerprint names the application build that made the call.

CREATE TABLE pellier.tool_audit (
    audit_id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    session_id        text NOT NULL,         -- the turn id for an agent's call
    tool              text NOT NULL,
    caller            text NOT NULL,         -- the agent, 'gateway', or the staff member
    args              jsonb,
    result            jsonb,
    latency_ms        integer,
    build_fingerprint text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX tool_audit_session ON pellier.tool_audit (session_id, created_at);

CREATE FUNCTION pellier.tool_audit_fill_once() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'pellier.tool_audit is append-only evidence; DELETE is not permitted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.result IS NOT NULL OR OLD.latency_ms IS NOT NULL THEN
        RAISE EXCEPTION 'pellier.tool_audit row % already finalized', OLD.audit_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (NEW.audit_id, NEW.session_id, NEW.tool, NEW.caller, NEW.args,
        NEW.build_fingerprint, NEW.created_at)
       IS DISTINCT FROM
       (OLD.audit_id, OLD.session_id, OLD.tool, OLD.caller, OLD.args,
        OLD.build_fingerprint, OLD.created_at) THEN
        RAISE EXCEPTION 'pellier.tool_audit identity columns are immutable'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER tool_audit_fill_once
    BEFORE UPDATE OR DELETE ON pellier.tool_audit
    FOR EACH ROW EXECUTE FUNCTION pellier.tool_audit_fill_once();


-- ===========================================================================
-- 10. retrieval_receipts: how one search ranked its results
-- ===========================================================================
-- Each search_products call writes one receipt: the plan, both ranked lists,
-- the fused RRF scores, the rerank scores, and a snapshot of every cited
-- product as it was shown. Lab 1 recomputes the RRF scores from these ranks.
-- Append-only.

CREATE TABLE pellier.retrieval_receipts (
    receipt_id             bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    turn_id                text,
    session_id             text,
    principal_sub          text,
    rail                   text,             -- in-process or gateway-mcp
    trace_id               text,
    query_hash             text NOT NULL,
    query_preview          text,
    search_plan            jsonb NOT NULL,
    hard_constraints       jsonb NOT NULL DEFAULT '{}',
    soft_preferences       jsonb NOT NULL DEFAULT '{}',
    exclusions             jsonb NOT NULL DEFAULT '[]',
    relaxations            jsonb NOT NULL DEFAULT '[]',
    embedding_model        text,
    rerank_model           text,
    retrieval_config       jsonb NOT NULL DEFAULT '{}',
    index_parameters       jsonb NOT NULL DEFAULT '{}',
    candidate_product_ids  jsonb NOT NULL DEFAULT '[]',
    vector_ranks           jsonb NOT NULL DEFAULT '{}',  -- product id -> rank
    lexical_ranks          jsonb NOT NULL DEFAULT '{}',  -- product id -> rank
    rrf_scores             jsonb NOT NULL DEFAULT '{}',  -- product id -> fused score
    rerank_scores          jsonb NOT NULL DEFAULT '{}',
    merchandising_rules    jsonb NOT NULL DEFAULT '[]',
    memory_record_ids_used jsonb NOT NULL DEFAULT '[]',
    citation_ids           jsonb NOT NULL DEFAULT '[]',
    citation_snapshots     jsonb NOT NULL DEFAULT '[]',
    citation_snapshot_hash text,
    latency_breakdown      jsonb NOT NULL DEFAULT '{}',
    modeled_cost_usd       numeric(12,6),
    created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX retrieval_receipts_turn ON pellier.retrieval_receipts (turn_id, created_at DESC);
CREATE INDEX retrieval_receipts_session ON pellier.retrieval_receipts (session_id, created_at DESC);

CREATE FUNCTION pellier.retrieval_receipts_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'retrieval_receipts are append-only';
END $$;

CREATE TRIGGER retrieval_receipts_append_only
    BEFORE UPDATE OR DELETE ON pellier.retrieval_receipts
    FOR EACH ROW EXECUTE FUNCTION pellier.retrieval_receipts_append_only();


-- ===========================================================================
-- 11. Who may read what
-- ===========================================================================
-- The application connects as the database owner. These paths use that
-- connection as it is:
--   * catalog, stock and return-policy reads, which are not about any one
--     customer (search_products, browse_department, compare_products,
--     check_stock, get_return_policy);
--   * the approvals writes: a shopper's credit request (ask_a_person), the
--     Planner's proposal and Nadia's decision;
--   * the staff money path, apply_store_credit, which is held by its own
--     checks above and by Cedar on the Gateway;
--   * the evidence writes to tool_audit and retrieval_receipts;
--   * a signed-in shopper's name and preferences, read at the start of a
--     turn (pellier_agent may read only id and cognito_username);
--   * three Operator reads of one client: the client record's orders and
--     tickets (routes/operator.py), the Planner's received returns
--     (services/operator_graph.py) and the orders a review covers
--     (services/operator_review.py). Staff may read any client, and these
--     are fixed SQL for the client the desk opened, not a model's tool call,
--     so there is no signed-in shopper to name. require_operator gates them.
--
-- Reads of one customer's orders and tickets on that customer's behalf run as
-- pellier_agent instead: get_orders and get_tickets, whether a shopper's agent
-- or the Operator's Investigator asks, and the order history and order count
-- a signed-in shopper's turn starts with. Each runs inside a transaction that
-- sets the role and names one customer:
--
--     SET LOCAL ROLE pellier_agent;
--     SELECT set_config('pellier.principal_username', 'theo', true);
--
-- pellier/backend/services/database.py and scripts/deploy/common/dataapi.py
-- are the two places that do this. Who is named depends on the rail. In
-- process, the customer comes from the signed token (for the Investigator,
-- the client the desk opened). On the Gateway, it is the customer Cedar's
-- owner-only permit admitted. Either way the policies below return only that
-- customer's rows, even if the tool's own SQL asks for someone else's. With
-- no name set, the role sees nothing.
--
-- This contains a wrong query, not an untrusted session: a session running
-- as pellier_agent can set the name itself, so the name is only as good as
-- the code that binds it in those two places.

-- The role is shared by every database on the cluster, so it is created once.
-- NOBYPASSRLS keeps the policies binding; the owner joins it to SET ROLE into it.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pellier_agent') THEN
        CREATE ROLE pellier_agent NOLOGIN NOINHERIT NOBYPASSRLS;
    END IF;
END $$;
GRANT pellier_agent TO CURRENT_USER;

-- What the role may touch: the two customer tables, the catalog get_orders
-- joins, and the two customer columns the policies read. INSERT on tickets is
-- there for Lab 4's proof that a write for another customer is refused; the
-- application never writes tickets as this role.
GRANT USAGE ON SCHEMA pellier TO pellier_agent;
GRANT SELECT ON pellier.product_catalog TO pellier_agent;
GRANT SELECT (id, cognito_username) ON pellier.customers TO pellier_agent;
GRANT SELECT ON pellier.orders TO pellier_agent;
GRANT SELECT, INSERT ON pellier.support_tickets TO pellier_agent;

REVOKE ALL ON FUNCTION pellier.apply_store_credit(text, text, integer, text, text) FROM PUBLIC;

ALTER TABLE pellier.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE pellier.support_tickets ENABLE ROW LEVEL SECURITY;

-- A row belongs to the customer whose sign-in name the session carries.
-- The same expression decides which rows the role sees (USING) and which rows
-- it may write (WITH CHECK).
CREATE POLICY orders_owner ON pellier.orders TO pellier_agent
    USING (customer_id = (SELECT id FROM pellier.customers
                           WHERE cognito_username = current_setting('pellier.principal_username', true)))
    WITH CHECK (customer_id = (SELECT id FROM pellier.customers
                                WHERE cognito_username = current_setting('pellier.principal_username', true)));

CREATE POLICY support_tickets_owner ON pellier.support_tickets TO pellier_agent
    USING (customer_id = (SELECT id FROM pellier.customers
                           WHERE cognito_username = current_setting('pellier.principal_username', true)))
    WITH CHECK (customer_id = (SELECT id FROM pellier.customers
                                WHERE cognito_username = current_setting('pellier.principal_username', true)));
