#!/usr/bin/env python3
"""
Test AgentCore Gateway authentication with Cognito JWT.

Usage:
    uv run test_gateway_auth.py \
      --gateway-url $GATEWAY_URL \
      --cognito-pool-id $COGNITO_POOL \
      --cognito-client-id $COGNITO_CLIENT
"""
import argparse
import boto3
import base64
import hashlib
import hmac
import json
import os
import sys

from test_gateway_tools import discover_gateway_tools, expected_tools_for_token


def get_cognito_token(
    pool_id: str,
    client_id: str,
    region: str,
    credentials_secret_arn: str | None = None,
) -> str:
    """Obtain a JWT token from Cognito using the workshop test user."""
    client = boto3.client("cognito-idp", region_name=region)

    if credentials_secret_arn:
        secret = boto3.client(
            "secretsmanager", region_name=region
        ).get_secret_value(SecretId=credentials_secret_arn)
        first_user = json.loads(secret["SecretString"])["users"][0]
        username = first_user["username"]
        password = first_user["password"]
    else:
        username = os.environ["COGNITO_USERNAME"]
        password = os.environ["COGNITO_PASSWORD"]

    client_secret = client.describe_user_pool_client(
        UserPoolId=pool_id,
        ClientId=client_id,
    )["UserPoolClient"].get("ClientSecret")
    auth_parameters = {
        "USERNAME": username,
        "PASSWORD": password,
    }
    if client_secret:
        digest = hmac.new(
            client_secret.encode("utf-8"),
            f"{username}{client_id}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        auth_parameters["SECRET_HASH"] = base64.b64encode(digest).decode("ascii")

    try:
        response = client.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters=auth_parameters,
        )
        token = response["AuthenticationResult"]["AccessToken"]
        return token
    except client.exceptions.NotAuthorizedException:
        print("ERROR: Invalid credentials. Check COGNITO_USERNAME and COGNITO_PASSWORD env vars.")
        sys.exit(1)
    except client.exceptions.UserNotFoundException:
        print("ERROR: The configured Cognito test user was not found.")
        sys.exit(1)
    except Exception as e:
        print(
            "ERROR: Failed to obtain a Cognito token "
            f"({e.__class__.__name__})."
        )
        sys.exit(1)


def test_gateway_auth(gateway_url: str, token: str):
    """Test that the Gateway accepts the JWT in a real MCP session."""
    try:
        tools = discover_gateway_tools(gateway_url, token)
        tool_count = len(tools)
        print("JWT token obtained successfully")
        print("Gateway authentication: PASSED")
        print(f"  Tools discovered: {tool_count}")
        expected = expected_tools_for_token(token)
        observed = {tool.name.rsplit("__", 1)[-1] for tool in tools}
        if tool_count != len(expected) or observed != expected:
            print(
                "Gateway authentication: FAILED "
                f"(expected the caller's {len(expected)}-tool catalogue)"
            )
            sys.exit(1)
    except Exception as e:
        print("Gateway authentication: FAILED")
        print(f"  Connection error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Test AgentCore Gateway authentication")
    parser.add_argument("--gateway-url", required=True, help="AgentCore Gateway URL")
    parser.add_argument("--cognito-pool-id", required=True, help="Cognito User Pool ID")
    parser.add_argument("--cognito-client-id", required=True, help="Cognito App Client ID")
    parser.add_argument(
        "--credentials-secret-arn",
        default=os.getenv("COGNITO_TEST_CREDENTIALS_SECRET_ARN"),
        help=(
            "Secret containing the workshop users; otherwise set "
            "COGNITO_USERNAME and COGNITO_PASSWORD"
        ),
    )
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Testing Gateway Authentication")
    print(f"  Gateway: {args.gateway_url}")
    print(f"  Cognito Pool: {args.cognito_pool_id}")
    print(f"{'='*60}\n")

    token = get_cognito_token(
        args.cognito_pool_id,
        args.cognito_client_id,
        args.region,
        args.credentials_secret_arn,
    )
    test_gateway_auth(args.gateway_url, token)

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
