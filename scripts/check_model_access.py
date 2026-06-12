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

import os

import boto3

# The workshop's models are cross-region inference profiles (us.* / global.*)
# that resolve through us-east-1. The region is intentionally pinned, but honor
# an AWS_REGION override and warn loudly if it points elsewhere, so a future
# region move doesn't get a false "all-green" from a check that silently ran
# against the wrong endpoint.
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
if REGION != "us-east-1":
    print(
        f"⚠️  AWS_REGION={REGION} – this workshop's model access is validated in "
        f"us-east-1 (us.*/global.* inference profiles). Results may not reflect "
        f"the actual deploy region.\n"
    )

MODELS = [
    {
        "name": "Claude Opus 4.6",
        "model_id": "global.anthropic.claude-opus-4-6-v1",
        # Editorial specialists (Style Advisor, Curator, Experience Guide).
        # NOT hard-required: if Opus is denied but the Sonnet 4.6 fallback
        # below passes, the session still runs (editorial agents fall back to
        # Sonnet via BEDROCK_OPUS_MODEL). main() enforces "Opus OR Sonnet".
        "required": False,
        "role": "editorial",  # consumed by the fallback logic in main()
        "body": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Say hi."}],
        },
    },
    {
        "name": "Claude Sonnet 4.6 (Opus fallback)",
        "model_id": "global.anthropic.claude-sonnet-4-6",
        # Fallback for the editorial agents when Opus 4.6 is unavailable.
        # Not independently required; it only needs to work IF Opus doesn't.
        "required": False,
        "role": "editorial_fallback",
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
        # Cohere Embed v4 (enabled in Workshop Studio). The backend calls this in
        # us-east-1 via config.BEDROCK_EMBEDDING_MODEL = "us.cohere.embed-v4:0",
        # so the probe must only accept forms that MATCH that config: the US
        # cross-region inference profile and (if the account exposes it) the bare
        # on-demand id. We deliberately do NOT probe eu./apac./global. — a non-US
        # profile "passing" would be a FALSE GREEN: it would report embeddings
        # healthy while the id the backend actually invokes (us.*) is still denied,
        # and it would route workshop data cross-region (e.g. to the EU). If us.*
        # is still provisioning, this check should FAIL loudly, matching reality.
        #
        # output_dimension=1024 keeps vectors aligned with the vector(1024)
        # schema + committed cache.
        "name": "Cohere Embed v4",
        "model_id_variants": [
            "us.cohere.embed-v4:0",
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
        # NOTE: name the ACTUAL model that was denied. A new account's Bedrock
        # Marketplace subscriptions provision asynchronously; AWS returns
        # "subscription ... still being processed. Try again after 15 minutes."
        # This is account/event-side and usually self-resolves — it is NOT an
        # IAM or app bug. (Earlier this message hardcoded "Cohere Embed v4",
        # which made Claude denials look like a Cohere problem.)
        print(
            f"    Access denied (AWS Marketplace): the subscription for\n"
            f"      '{model['name']}' is not yet active on this account. New\n"
            f"      accounts provision asynchronously — if the error says\n"
            f"      'still being processed', wait ~15 min and re-run. If it\n"
            f"      persists, the org/event admin must approve this model in\n"
            f"      the account's Bedrock model access / Private Marketplace."
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


def _upsert_env(env_path: str, key: str, value: str) -> None:
    """Set KEY=value in a .env file (replace existing line or append)."""
    import os
    line = f"{key}={value}\n"
    if os.path.exists(env_path):
        lines = open(env_path).read().splitlines(keepends=True)
        for i, l in enumerate(lines):
            if l.split("=", 1)[0].strip() == key:
                lines[i] = line
                break
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(line)
        open(env_path, "w").write("".join(lines))
    else:
        open(env_path, "w").write(line)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    # When set, write the resolved editorial model (Opus, or Sonnet fallback)
    # to this .env so the backend picks up whichever is actually accessible.
    parser.add_argument("--write-env", default=None,
                        help="Path to .env to update BEDROCK_OPUS_MODEL if Opus falls back to Sonnet")
    args = parser.parse_args()

    client = boto3.client("bedrock-runtime", region_name=REGION)
    print(f"Checking Bedrock model access in {REGION}...\n")

    results = {}  # name -> (passed, role, resolved_id)
    for model in MODELS:
        passed = check_model(client, model)
        role = model.get("role")
        shown_id = model.get("_resolved_id") or model.get("model_id") \
            or (model.get("model_id_variants") or ["?"])[0]
        results[model["name"]] = (passed, role, shown_id)
        # Tag: editorial pair is conditionally-required; others use `required`.
        if passed:
            tag = "\033[32m✓ PASS\033[0m"
        elif role in ("editorial", "editorial_fallback"):
            tag = "\033[33m• ----\033[0m"  # resolved together below
        elif model.get("required", True):
            tag = "\033[31m✗ FAIL\033[0m"
        else:
            tag = "\033[33m• SKIP\033[0m"
        print(f"  {tag}  {model['name']:<42} ({shown_id})")

    # --- Editorial resolution: Opus OR Sonnet must work ---
    opus_ok = results.get("Claude Opus 4.6", (False,))[0]
    sonnet_name = "Claude Sonnet 4.6 (Opus fallback)"
    sonnet_ok = results.get(sonnet_name, (False,))[0]
    sonnet_id = results.get(sonnet_name, (False, None, ""))[2]

    editorial_ok = opus_ok or sonnet_ok
    print()
    if opus_ok:
        print("Editorial agents: \033[32mOpus 4.6\033[0m (primary).")
    elif sonnet_ok:
        print("Editorial agents: \033[33mOpus 4.6 unavailable → falling back to Sonnet 4.6\033[0m.")
        if args.write_env:
            _upsert_env(args.write_env, "BEDROCK_OPUS_MODEL", sonnet_id)
            print(f"  → wrote BEDROCK_OPUS_MODEL={sonnet_id} to {args.write_env}")
        else:
            print(f"  → set BEDROCK_OPUS_MODEL={sonnet_id} in pellier/backend/.env")
    else:
        print("\033[31mEditorial agents: NEITHER Opus 4.6 nor Sonnet 4.6 is accessible.\033[0m")

    # --- Hard-required models (Haiku, Rerank, Embed) ---
    hard = [m["name"] for m in MODELS if m.get("required", True)]
    hard_missing = [n for n in hard if not results.get(n, (False,))[0]]

    print()
    if editorial_ok and not hard_missing:
        print("All required models accessible. Workshop is ready.")
    else:
        if hard_missing:
            print("\033[31mMissing required model(s): " + ", ".join(hard_missing) + "\033[0m")
        if not editorial_ok:
            print("\033[31mNo editorial model (Opus or Sonnet) — chat WILL fail.\033[0m")
        print("Enable them at: https://console.aws.amazon.com/bedrock/home#/modelaccess")
        sys.exit(1)


if __name__ == "__main__":
    main()
