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
        # REQUIRED at runtime: every shopper query is embedded live via this
        # model before the pgvector search (services/embeddings.py → embed_query).
        # The committed cache (data/embeddings_cache.json) only seeds the catalog
        # corpus; it does NOT cover runtime query embedding. If this model is
        # inaccessible, /api/health reports bedrock:inaccessible and search fails.
        #
        # Cohere Embed English v3 is enabled by default in AWS Workshop Studio
        # accounts and invokes on-demand by bare model ID (no inference profile).
        # Note: v3 does NOT accept output_dimension — it returns 1024-dim natively.
        "name": "Cohere Embed English v3",
        "model_id": "cohere.embed-english-v3",
        "required": True,
        "body": {
            "texts": ["test"],
            "input_type": "search_query",
            "embedding_types": ["float"],
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
    except client.exceptions.AccessDeniedException as e:
        msg = str(e)
        if "private marketplace" in msg.lower() or "marketplace subscription" in msg.lower():
            # The account is behind an AWS Private Marketplace (common for
            # Workshop Studio / event accounts) that has NOT allow-listed this
            # third-party model. IAM permission is irrelevant — governance wins.
            print(
                "    Access denied (Private Marketplace): this model is not on the\n"
                "      account's approved-products list. The org/event admin must add it\n"
                "      to the Private Marketplace, or switch to a model enabled by default\n"
                "      in Workshop Studio (e.g. cohere.embed-english-v3 for embeddings)."
            )
        else:
            print("    Access denied — enable this model in the Bedrock console (Model access).")
        return False
    except Exception as e:
        error_str = str(e)
        if "ValidationException" in error_str:
            low = error_str.lower()
            # A ValidationException is NOT proof of access. Two cases that look
            # like "access works" but are real failures:
            if "on-demand throughput isn't supported" in low or "on-demand throughput is not supported" in low:
                print(
                    "    FAIL: this model has no on-demand throughput by bare model ID.\n"
                    "      Invoke it through a cross-region inference profile instead\n"
                    "      (e.g. us.<model-id>)."
                )
                return False
            if "output_dimension" in low:
                print(
                    "    FAIL: the request includes output_dimension, which this model\n"
                    "      rejects (Embed English v3 returns 1024-dim natively — drop it)."
                )
                return False
            # Any other ValidationException is a genuine payload-shape issue and
            # does imply the model is reachable. Treat as a pass for ACCESS only.
            print(f"    Note: model reachable; test payload rejected ({e.__class__.__name__}). Access OK.")
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
        label = model["name"] + ("" if req else "  (optional)")
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
            + "."
        )
    if required_ok:
        print("All required models accessible. Workshop is ready.")
    else:
        print("\033[31mRequired model access is missing — the session WILL fail.\033[0m")
        print("Enable them at: https://console.aws.amazon.com/bedrock/home#/modelaccess")
        sys.exit(1)


if __name__ == "__main__":
    main()
