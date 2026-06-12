#!/usr/bin/env python3
"""
Generate MCP server configuration for Aurora PostgreSQL.

Writes one config file:
- pellier/config/mcp-server-config.json — read by the workshop and
  consumable by any MCP host (VS Code chat extension, Claude Code,
  Strands `MCPClient`, Bedrock AgentCore Gateway).

Environment Variables Required (set by bootstrap-labs.sh):
- DB_CLUSTER_ARN: Aurora cluster ARN
- DB_SECRET_ARN: Secrets Manager ARN for database credentials
- DB_NAME: Database name (default: postgres)
- AWS_REGION: AWS region (default: us-east-1)
"""

import json
import os
import sys
from pathlib import Path


def generate_mcp_config():
    """Generate MCP server configuration files."""
    
    # Get environment variables (set by bootstrap-labs.sh)
    db_cluster_arn = os.environ.get('DB_CLUSTER_ARN')
    db_secret_arn = os.environ.get('DB_SECRET_ARN')
    db_name = os.environ.get('DB_NAME', 'postgres')
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    
    # Validate required variables
    if not db_cluster_arn:
        print("ERROR: DB_CLUSTER_ARN environment variable not set", file=sys.stderr)
        print("This should be set by bootstrap-labs.sh at line 67", file=sys.stderr)
        return 1
    
    if not db_secret_arn:
        print("ERROR: DB_SECRET_ARN environment variable not set", file=sys.stderr)
        print("This should be passed from CloudFormation outputs", file=sys.stderr)
        return 1
    
    # MCP server configuration (same for both files).
    #
    # Flag names track the current awslabs.postgres-mcp-server CLI:
    #   --db_cluster_arn   (NOT the older --resource_arn)
    #   --connection_method rdsapi   (RDS Data API path — uses the cluster ARN
    #                                 + secret, no host/port needed)
    #   read-only is the DEFAULT; you opt INTO writes with --allow_write_query.
    #   So we simply omit that flag (the older "--readonly True" value-flag is
    #   gone and the server rejects it as an unrecognized argument).
    mcp_server_config = {
        "command": "uvx",
        "args": [
            "awslabs.postgres-mcp-server@latest",
            "--connection_method", "rdsapi",
            "--db_cluster_arn", db_cluster_arn,
            "--secret_arn", db_secret_arn,
            "--database", db_name,
            "--region", aws_region
        ],
        "env": {
            "AWS_REGION": aws_region,
            "FASTMCP_LOG_LEVEL": "ERROR"
        },
        "disabled": False,
        "autoApprove": []
    }
    
    # =========================================================================
    # File 1: Workshop config (pellier/config/mcp-server-config.json)
    # =========================================================================
    workshop_config = {
        "mcpServers": {
            "awslabs.postgres-mcp-server": mcp_server_config
        }
    }
    
    # Determine output directory (../config from backend/)
    workshop_dir = Path(__file__).parent.parent / "config"
    workshop_dir.mkdir(parents=True, exist_ok=True)
    workshop_file = workshop_dir / "mcp-server-config.json"
    
    try:
        with open(workshop_file, 'w') as f:
            json.dump(workshop_config, f, indent=2)
        print(f"✅ Workshop config: {workshop_file}")
    except Exception as e:
        print(f"ERROR: Failed to write workshop config: {e}", file=sys.stderr)
        return 1
    
    # =========================================================================
    # Summary
    # =========================================================================
    print()
    print("=" * 70)
    print("✅ MCP Configuration Generated Successfully!")
    print("=" * 70)
    print()
    print("📁 Configuration File:")
    print(f"   {workshop_file}")
    print()
    print("🔧 Server Configuration:")
    print(f"   • Server: awslabs.postgres-mcp-server (uvx)")
    print(f"   • Database Cluster: {db_cluster_arn}")
    print(f"   • Secret ARN: {db_secret_arn}")
    print(f"   • Database: {db_name}")
    print(f"   • Region: {aws_region}")
    print(f"   • Connection: rdsapi (RDS Data API)")
    print(f"   • Read-only: default (no --allow_write_query)")
    print()
    print("🎯 Usage:")
    print("   • Any MCP host (VS Code chat extension, Claude Code,")
    print("     Strands MCPClient, AgentCore Gateway) consumes this JSON.")
    print("   • Tools advertised: get_table_schema, run_query, ...")
    print()
    print("💡 Verification (Act III §02):")
    print("   • cat pellier/config/mcp-server-config.json | python3 -m json.tool")
    print("   • uvx awslabs.postgres-mcp-server@latest --help")
    print("=" * 70)

    return 0


def main():
    """Main entry point."""
    print()
    print("=" * 70)
    print("MCP Configuration Generator for Aurora PostgreSQL")
    print("=" * 70)
    print()
    
    # Check for required environment variables
    db_cluster_arn = os.environ.get('DB_CLUSTER_ARN')
    db_secret_arn = os.environ.get('DB_SECRET_ARN')
    
    if not db_cluster_arn or not db_secret_arn:
        print("❌ Missing Required Environment Variables")
        print()
        if not db_cluster_arn:
            print("   - DB_CLUSTER_ARN: Not set")
            print("     Expected: Set by bootstrap-labs.sh at line 67")
        if not db_secret_arn:
            print("   - DB_SECRET_ARN: Not set")
            print("     Expected: Passed from CloudFormation outputs")
        print()
        print("💡 Troubleshooting:")
        print("   1. Check CloudFormation stack outputs for DB_SECRET_ARN")
        print("   2. Verify bootstrap-labs.sh is sourcing .env file correctly")
        print("   3. Check /workshop/sample-pellier-agentic-search-apg/.env")
        print()
        return 1
    
    # Generate configuration
    return generate_mcp_config()


if __name__ == "__main__":
    sys.exit(main())