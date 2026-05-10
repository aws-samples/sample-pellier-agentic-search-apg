"""E2E test harness for Pellier storefront.

Lives at the workspace root (not under pellier/backend/tests) because
E2E spans the full stack: Playwright driving the React frontend, which in
turn calls the FastAPI backend, which in turn validates JWTs issued by a
dedicated Cognito dev pool.

Scripts here run in CI only and are not part of the backend pytest suite.
"""
