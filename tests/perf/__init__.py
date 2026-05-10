"""Performance smoke harness for Pellier storefront.

Lives at the workspace root (not under ``pellier/backend/tests``)
because these tests exercise the running HTTP surface end-to-end - a
seeded dev catalog reachable over the network, not the in-process
backend unit-test fixtures. They are intentionally skipped unless
``PERF_TEST_BASE_URL`` points at a live stack (docker-compose or the
workshop Code Editor box).

Task 7.1 - ``.kiro/specs/pellier-storefront/tasks.md``.
"""
