"""Two sessions race one approved credit through pellier.apply_store_credit on PostgreSQL 18.

The function holds "write once" without raising the isolation level: it locks the customer's
approved reviews FOR UPDATE, then reads the key in a new statement. At READ COMMITTED that
statement takes a new snapshot, so a racing retry waits for the first write and returns it as a
replay. At REPEATABLE READ or SERIALIZABLE the retry keeps its first snapshot, misses the
credit, reaches the order lock and fails with 40001: a stricter level turns the clean answer
into an error the caller must retry. Either way exactly one credit row exists.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

import psycopg
import pytest

from tests.fresh_cluster import Cluster, fresh_db  # noqa: F401

CALL = "SELECT pellier.apply_store_credit(%s, %s, 2500, 'race', NULL) AS result"
BLOCKED_SECONDS = 1.0


def _connect(cluster: Cluster) -> psycopg.Connection:
    return psycopg.connect(host=str(cluster.socket), port=5432, user="postgres",
                           dbname="postgres", autocommit=True)


def _approved_reviews(cluster: Cluster, customer: str, hashes: str) -> List[str]:
    """A customer with two received returns and one approved review per letter in hashes."""
    with _connect(cluster) as conn:
        conn.execute("INSERT INTO pellier.customers (id, name, cognito_username) "
                     "VALUES (%s, %s, %s)", (customer, customer, customer.lower()))
        conn.execute("INSERT INTO pellier.orders (customer_id, product_id, amount_paid_cents, "
                     "ship_to, return_status) SELECT %s, (SELECT min(\"productId\") FROM "
                     "pellier.product_catalog), 1250, 'race', 'received' "
                     "FROM generate_series(1, 2)", (customer,))
        keys = []
        for letter in hashes:
            row = conn.execute(
                "INSERT INTO pellier.approvals (customer_id, tool, args, status, order_ids, "
                "action_hash, requester_kind, decided_by, decided_at) "
                "SELECT %s, 'give_store_credit', jsonb_build_object('customer_id', %s::text, "
                "'amount_cents', 2500, 'reason', 'race'), 'approved', array_agg(id ORDER BY id), "
                "repeat(%s::text, 64), 'operator', 'race', now() "
                "FROM pellier.orders WHERE customer_id = %s "
                "RETURNING 'operator-review:' || id || ':' || left(action_hash, 32)",
                (customer, customer, letter, customer)).fetchone()
            keys.append(row[0])
        return keys


def _race(cluster: Cluster, customer: str, first_key: str, second_key: str,
          isolation: str) -> Dict[str, Any]:
    """Session A writes and holds its transaction; session B calls; A commits."""
    outcome: Dict[str, Any] = {}
    with _connect(cluster) as a, _connect(cluster) as b:
        a.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
        outcome["first"] = a.execute(CALL, (first_key, customer)).fetchone()[0]

        def second() -> None:
            try:
                b.execute(f"BEGIN ISOLATION LEVEL {isolation}")
                outcome["second"] = b.execute(CALL, (second_key, customer)).fetchone()[0]
                b.execute("COMMIT")
            except psycopg.Error as exc:
                outcome["sqlstate"] = exc.sqlstate
                b.execute("ROLLBACK")

        racer = threading.Thread(target=second)
        racer.start()
        racer.join(BLOCKED_SECONDS)
        outcome["waited"] = racer.is_alive()
        a.execute("COMMIT")
        racer.join(10)
    with _connect(cluster) as conn:
        outcome["rows"] = conn.execute(
            "SELECT count(*) FROM pellier.store_credits WHERE customer_id = %s",
            (customer,)).fetchone()[0]
    return outcome


def test_a_racing_retry_at_read_committed_waits_then_replays_the_first_credit(
    fresh_db: Cluster,  # noqa: F811
) -> None:
    (key,) = _approved_reviews(fresh_db, "CUST-RACEREAD", "c")
    out = _race(fresh_db, "CUST-RACEREAD", key, key, "READ COMMITTED")
    assert out["waited"], "the retry did not wait for the first write's lock"
    assert out["second"]["idempotent_replay"] is True
    assert out["second"]["credit_id"] == out["first"]["credit_id"]
    assert out["rows"] == 1


@pytest.mark.parametrize("isolation, customer", [("REPEATABLE READ", "CUST-RACEREPEAT"),
                                                 ("SERIALIZABLE", "CUST-RACESERIAL")])
def test_a_stricter_isolation_level_turns_the_replay_into_a_serialization_failure(
    fresh_db: Cluster, isolation: str, customer: str,  # noqa: F811
) -> None:
    (key,) = _approved_reviews(fresh_db, customer, "c")
    out = _race(fresh_db, customer, key, key, isolation)
    assert out["waited"]
    assert out.get("sqlstate") == "40001", out
    assert out["rows"] == 1


def test_a_second_approved_review_for_the_same_orders_is_refused_by_the_order_lock(
    fresh_db: Cluster,  # noqa: F811
) -> None:
    first, second = _approved_reviews(fresh_db, "CUST-RACEORDERS", "cd")
    out = _race(fresh_db, "CUST-RACEORDERS", first, second, "READ COMMITTED")
    assert out["waited"]
    assert out["second"]["status"] == "not_creditable"
    assert out["rows"] == 1
