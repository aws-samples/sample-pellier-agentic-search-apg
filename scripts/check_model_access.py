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
        "required": True,  # editorial specialists at runtime
        "body": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Say hi."}],
        },
    },
    {
        "name": "Claude Haiku 4.5",
        "model_id": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "required": True,  # reporting/routing specialists at runtime
        "body": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Say hi."}],
        },
    },
    {
        "name": "Cohere Rerank v3.5",
        "model_id": "us.cohere.rerank-v3-5:0",  # cross-region inference profile (no on-demand by bare ID)
        "required": True,  # Anna's rerank proof + find_pieces at runtime
        "body": {
            "api_version": 2,
            "query": "test",
            "documents": ["hello world", "goodbye world"],
            "top_n": 1,
        },
    },
    {
        # NOT required at runtime: the catalog is seeded from a committed
        # embeddings cache (data/embeddings_cache.json). Embed access is only
        # needed to *regenerate* that cache after a catalog change. We still
        # report it so facilitators know, but it does not fail the preflight.
        "name": "Cohere Embed v4",
        "model_id": "us.cohere.embed-v4:0",  # cross-region inference profile (no on-demand by bare ID)
        "required": False,
        "body": {
            "texts": ["test"],
            "input_type": "search_query",
            "embedding_types": ["float"],
            "output_dimension": 1024,
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

    required_ok = True
    optional_missing = []
    for model in MODELS:
        passed = check_model(client, model)
        req = model.get("required", True)
        if passed:
            tag = "\033[32m✓ PASS\033[0m"
        elif req:
            tag = "\033[31m✗ FAIL\033[0m"
        else:
            tag = "\033[33m• SKIP\033[0m"
        label = model["name"] + ("" if req else "  (optional — cache covers it)")
        print(f"  {tag}  {label:<40} ({model['model_id']})")
        if not passed:
            if req:
                required_ok = False
            else:
                optional_missing.append(model["name"])

    print()
    if optional_missing:
        print(
            "Note: optional model(s) not accessible: "
            + ", ".join(optional_missing)
            + ".\n      The catalog seeds from the committed embeddings cache, so this\n"
            "      does not block the workshop. You only need Embed v4 to\n"
            "      regenerate data/embeddings_cache.json after a catalog change."
        )
    if required_ok:
        print("All required models accessible. Workshop is ready.")
    else:
        print("\033[31mRequired model access is missing — the session WILL fail.\033[0m")
        print("Enable them at: https://console.aws.amazon.com/bedrock/home#/modelaccess")
        sys.exit(1)


if __name__ == "__main__":
    main()
