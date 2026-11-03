"""Participant-facing identity for the configured PostgreSQL data source."""


def database_source_label() -> str:
    """Name the database actually configured for this process.

    Local development runs the Aurora-compatible schema on PostgreSQL. A deployed
    Aurora cluster endpoint is identifiable by the RDS cluster hostname, including
    the remote host preserved by the local SSM launcher; any other
    remote PostgreSQL host stays generic rather than being promoted to Aurora by
    assumption.
    """
    from config import settings

    host = str(settings.DB_HOST or "").strip().lower()
    local_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
    if host in local_hosts and settings.DB_TUNNEL_REMOTE_HOST:
        host = settings.DB_TUNNEL_REMOTE_HOST.strip().lower()
    if host in local_hosts:
        return "Local PostgreSQL"
    if host.endswith(".rds.amazonaws.com") and (
        ".cluster-" in host or ".cluster-ro-" in host
    ):
        return "Aurora PostgreSQL"
    return "PostgreSQL"
