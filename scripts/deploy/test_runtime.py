#!/usr/bin/env python3
"""
Test the deployed Pellier AgentCore Runtime.

Usage:
    uv run test_runtime.py --runtime-id $AGENT_RUNTIME_ID --prompt "Find running shoes under $50" --token "$TOKEN"
    uv run test_runtime.py --runtime-id $AGENT_RUNTIME_ID --prompt "What's trending?" --token "$TOKEN" --stream
"""
import argparse
import boto3
import json
import os
import sys


def test_runtime(runtime_id: str, prompt: str, token: str, region: str, stream: bool = False):
    """Send a prompt to the deployed AgentCore Runtime and print the response."""
    client = boto3.client("bedrock-agentcore-runtime", region_name=region)

    print(f"\n{'='*60}")
    print(f"Prompt: {prompt}")
    print(f"Runtime: {runtime_id}")
    print(f"Stream: {stream}")
    print(f"{'='*60}\n")

    payload = json.dumps({"prompt": prompt, "session_id": "test-session"})

    if stream:
        response = client.invoke_agent_runtime_streaming(
            agentRuntimeId=runtime_id,
            payload=payload,
            authToken=token,
        )
        print("Response (streaming):")
        for event in response.get("body", []):
            if "chunk" in event:
                chunk = event["chunk"]
                if "bytes" in chunk:
                    text = chunk["bytes"].decode("utf-8")
                    print(text, end="", flush=True)
        print("\n")
    else:
        response = client.invoke_agent_runtime(
            agentRuntimeId=runtime_id,
            payload=payload,
            authToken=token,
        )
        body = json.loads(response["body"].read())
        print("Response:")
        print(json.dumps(body, indent=2))

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Test Pellier AgentCore Runtime")
    parser.add_argument("--runtime-id", required=True, help="AgentCore Runtime ID")
    parser.add_argument("--prompt", required=True, help="Prompt to send")
    parser.add_argument("--token", required=True, help="Cognito JWT token")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--stream", action="store_true", help="Use streaming response")
    args = parser.parse_args()

    test_runtime(args.runtime_id, args.prompt, args.token, args.region, args.stream)


if __name__ == "__main__":
    main()
