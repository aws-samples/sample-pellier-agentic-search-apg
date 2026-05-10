#!/usr/bin/env python3
"""
Generate MCP server configuration for Aurora PostgreSQL.

Creates two config files:
1. pellier/config/mcp-server-config.json (for general MCP use)
2. ~/.aws/amazonq/default.json (for Q Developer in IDE)

Environment Variables Required (set by bootstrap-labs.sh):
- DB_CLUSTER_ARN: Aurora cluster ARN
- DB_SECRET_ARN: Secrets Manager ARN for database credentials
- DB_NAME: Database name (default: postgres)
- AWS_REGION: AWS region (default: us-west-2)
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
    aws_region = os.environ.get('AWS_REGION', 'us-west-2')
    
    # Validate required variables
    if not db_cluster_arn:
        print("ERROR: DB_CLUSTER_ARN environment variable not set", file=sys.stderr)
        print("This should be set by bootstrap-labs.sh at line 67", file=sys.stderr)
        return 1
    
    if not db_secret_arn:
        print("ERROR: DB_SECRET_ARN environment variable not set", file=sys.stderr)
        print("This should be passed from CloudFormation outputs", file=sys.stderr)
        return 1
    
    # MCP server configuration (same for both files)
    mcp_server_config = {
        "command": "uvx",
        "args": [
            "awslabs.postgres-mcp-server@latest",
            "--resource_arn", db_cluster_arn,
            "--secret_arn", db_secret_arn,
            "--database", db_name,
            "--region", aws_region,
            "--readonly", "True"
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
    # File 2: Q Developer config (~/.aws/amazonq/default.json)
    # =========================================================================
    
    # Q Developer configuration format
    q_developer_config = {
        "mcpServers": {
            "awslabs.postgres-mcp-server": mcp_server_config
        },
        "useLegacyMcpJson": True  # Support for legacy mcp.json files
    }
    
    # Determine Q Developer config location
    home = Path.home()
    q_config_dir = home / ".aws" / "amazonq"
    q_config_dir.mkdir(parents=True, exist_ok=True)
    q_config_file = q_config_dir / "default.json"
    
    try:
        # Check if file already exists and merge configs
        if q_config_file.exists():
            with open(q_config_file, 'r') as f:
                existing_config = json.load(f)
            
            # Merge MCP servers (keep existing, add/update ours)
            if "mcpServers" not in existing_config:
                existing_config["mcpServers"] = {}
            
            existing_config["mcpServers"]["awslabs.postgres-mcp-server"] = mcp_server_config
            existing_config["useLegacyMcpJson"] = True
            
            q_developer_config = existing_config
        
        # Write Q Developer config
        with open(q_config_file, 'w') as f:
            json.dump(q_developer_config, f, indent=2)
        
        print(f"✅ Q Developer config: {q_config_file}")
        
        # Set proper permissions
        q_config_file.chmod(0o600)
        
    except Exception as e:
        print(f"ERROR: Failed to write Q Developer config: {e}", file=sys.stderr)
        return 1
    
    # =========================================================================
    # Summary
    # =========================================================================
    print()
    print("=" * 70)
    print("✅ MCP Configuration Generated Successfully!")
    print("=" * 70)
    print()
    print("📁 Configuration Files Created:")
    print(f"   1. Workshop: {workshop_file}")
    print(f"   2. Q Developer: {q_config_file}")
    print()
    print("🔧 Server Configuration:")
    print(f"   • Server: AWS Labs PostgreSQL MCP Server (uvx)")
    print(f"   • Database Cluster: {db_cluster_arn}")
    print(f"   • Secret ARN: {db_secret_arn}")
    print(f"   • Database: {db_name}")
    print(f"   • Region: {aws_region}")
    print(f"   • Read-only: True")
    print()
    print("🎯 Usage:")
    print("   • Amazon Q Developer: Open Q Chat in VS Code")
    print("   • Ask: 'What tables exist in pellier schema?'")
    print("   • MCP tools available: get_table_schema, run_query")
    print()
    print("💡 Verification:")
    print("   • Open VS Code → Amazon Q sidebar")
    print("   • Settings → MCP Servers → Should see 'awslabs.postgres-mcp-server'")
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