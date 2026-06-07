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
        # Cohere Embed v4 (enabled in Workshop Studio). v4 has no on-demand
        # throughput by bare model ID, so the accessible form is usually a
        # cross-region inference profile (us./eu./apac.). We don't assume which
        # prefix the account exposes — `model_id_variants` lists every form and
        # the check passes on the FIRST that works, reporting which one. The
        # backend default (config.BEDROCK_EMBEDDING_MODEL) is us.cohere.embed-v4:0;
        # if a different variant wins here, set BEDROCK_EMBEDDING_MODEL to it.
        #
        # output_dimension=1024 keeps vectors aligned with the vector(1024)
        # schema + committed cache.
        "name": "Cohere Embed v4",
        "model_id_variants": [
            "us.cohere.embed-v4:0",
            "eu.cohere.embed-v4:0",
            "apac.cohere.embed-v4:0",
            "global.cohere.embed-v4:0",
            "cohere.embed-v4:0",
        ],
        "required": True,
        "body": {
            "texts": ["test"],
            "input_type": "search_query",
            "embedding_types": ["float"],
            "output_dimension": 1024,
        },
    },
]


def _invoke_one(client, model_id: str, body: dict):
    """Try one model ID. Returns (status, detail) where status is one of:
    ok | reachable | denied | denied_marketplace | no_ondemand | bad_dim | error."""
    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        # Read the body to confirm a valid response
        response["body"].read()
        return ("ok", "")
    except client.exceptions.AccessDeniedException as e:
        msg = str(e).lower()
        if "private marketplace" in msg or "marketplace subscription" in msg:
            return ("denied_marketplace", str(e))
        return ("denied", str(e))
    except Exception as e:
        low = str(e).lower()
        if "validationexception" in low:
            # A ValidationException is NOT proof of access. Distinguish the
            # "looks reachable but actually unusable" cases from a benign
            # payload-shape rejection (which DOES imply access).
            if "on-demand throughput is" in low and "supported" in low:
                return ("no_ondemand", str(e))
            if "output_dimension" in low:
                return ("bad_dim", str(e))
            return ("reachable", str(e))  # payload quibble → access OK
        return ("error", str(e))


def check_model(client, model: dict) -> bool:
    """Check one model. Supports a single `model_id` or a `model_id_variants`
    list — for the latter, tries each in order and passes on the FIRST that
    works, printing which variant won so config can be set to match."""
    variants = model.get("model_id_variants") or [model["model_id"]]
    body = model["body"]
    multi = len(variants) > 1

    results = []  # (variant, status, detail) for diagnostics if all fail
    for mid in variants:
        status, detail = _invoke_one(client, mid, body)
        if status in ("ok", "reachable"):
            if multi:
                note = "" if status == "ok" else " (reachable; test payload rejected — access OK)"
                print(f"    Accessible via: {mid}{note}")
                model["_resolved_id"] = mid
            elif status == "reachable":
                print(f"    Note: model reachable; test payload rejected. Access OK.")
            return True
        results.append((mid, status, detail))

    # Nothing worked — print the most actionable reason.
    if any(s == "denied_marketplace" for _, s, _ in results):
        print(
            "    Access denied (Private Marketplace): not on the account's\n"
            "      approved-products list. The org/event admin must add Cohere\n"
            "      Embed v4 to the Private Marketplace for this account."
        )
    elif all(s in ("no_ondemand", "denied") for _, s, _ in results) and multi:
        print(
            "    None of the tried IDs are accessible. Variants attempted:\n"
            + "\n".join(f"        - {mid} → {s}" for mid, s, _ in results)
            + "\n      Enable Cohere Embed v4 (Model access) or check the inference-profile prefix."
        )
    elif any(s == "no_ondemand" for _, s, _ in results):
        print(
            "    FAIL: no on-demand throughput by bare model ID — use a\n"
            "      cross-region inference profile (us./eu./apac.)."
        )
    elif any(s == "bad_dim" for _, s, _ in results):
        print("    FAIL: output_dimension rejected by this model.")
    else:
        print(f"    Access denied / error. Last: {results[-1][2] if results else 'unknown'}")
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
        shown_id = model.get("_resolved_id") or model.get("model_id") \
            or (model.get("model_id_variants") or ["?"])[0]
        print(f"  {tag}  {label:<40} ({shown_id})")
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
