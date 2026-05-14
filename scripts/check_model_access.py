#!/usr/bin/env python3
"""
Check Bedrock model access for the four models Pellier requires.

Usage:
    python3 scripts/check_model_access.py

Verifies invoke access by sending a minimal request to each model.
Prints a clear pass/fail for each.
"""

import json
import sys

import boto3

REGION = "us-west-2"

MODELS = [
    {
        "name": "Claude Opus 4.6",
        "model_id": "global.anthropic.claude-opus-4-6-v1",
        "body": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Say hi."}],
        },
    },
    {
        "name": "Claude Haiku 4.5",
        "model_id": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "body": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Say hi."}],
        },
    },
    {
        "name": "Cohere Embed v4",
        "model_id": "global.cohere.embed-v4:0",
        "body": {
            "texts": ["test"],
            "input_type": "search_query",
            "embedding_types": ["float"],
            "output_dimension": 1024,
        },
    },
    {
        "name": "Cohere Rerank v3.5",
        "model_id": "cohere.rerank-v3-5:0",
        "body": {
            "api_version": 2,
            "query": "test",
            "documents": ["hello world", "goodbye world"],
            "top_n": 1,
        },
    },
]


def check_model(client, model: dict) -> bool:
    try:
        response = client.invoke_model(
            modelId=model["model_id"],
            body=json.dumps(model["body"]),
            contentType="application/json",
            accept="application/json",
        )
        # Read the body to confirm a valid response
        response["body"].read()
        return True
    except client.exceptions.AccessDeniedException:
        print(f"    Access denied — enable this model in the Bedrock console")
        return False
    except Exception as e:
        error_str = str(e)
        if "ValidationException" in error_str:
            # Model is accessible but request format was wrong — still a pass for access check
            print(f"    Note: model accessible but test payload rejected ({e.__class__.__name__})")
            return True
        print(f"    Error: {e}")
        return False


def main():
    client = boto3.client("bedrock-runtime", region_name=REGION)
    print(f"Checking Bedrock model access in {REGION}...\n")

    all_passed = True
    for model in MODELS:
        passed = check_model(client, model)
        status = "\033[32m✓ PASS\033[0m" if passed else "\033[31m✗ FAIL\033[0m"
        print(f"  {status}  {model['name']:<20} ({model['model_id']})")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All models accessible. Workshop is ready.")
    else:
        print("Some models are not accessible.")
        print("Enable them at: https://console.aws.amazon.com/bedrock/home#/modelaccess")
        sys.exit(1)


if __name__ == "__main__":
    main()
