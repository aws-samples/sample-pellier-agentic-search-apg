#!/usr/bin/env python3
"""
Check Bedrock model access for Pellier's application and managed Runtime.

Usage:
    python3 scripts/check_model_access.py

Verifies invoke access by sending a minimal request to each model.
Prints a clear pass/fail for each.
"""

import json
import os
import sys
from pathlib import Path

import boto3


def _load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    for env_path in (root / ".env", root / "pellier" / "backend" / ".env"):
        if not env_path.is_file():
            continue
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip("'\"")


_load_env()

# Keep the model-access preflight in the same region as Aurora, Gateway,
# Runtime, and Cognito for local and workshop runs.
REGION = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "us-east-1"

MODELS = [
    {
        "name": "Claude Opus 5",
        "model_id": "global.anthropic.claude-opus-5",
        # Editorial specialists (Search Agent, Personalization Agent, Customer Service Agent).
        # NOT hard-required: if Opus is denied but a Sonnet fallback
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
        "name": "Claude Sonnet",
        "model_id_variants": [
            "global.anthropic.claude-sonnet-5",
        ],
        # Hard-required: routing, reporting specialists, structured extraction,
        # the AgentCore Runtime, AND the Claude Code CLI lane all pin this
        # global Sonnet 5 profile. Keep an explicit profile rather than a
        # floating CLI alias so preflight and participant sessions agree.
        "required": True,
        "role": "sonnet",
        "access_hint": (
            "Enable Claude Sonnet 5 in Bedrock model access."
        ),
        "body": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Say hi."}],
        },
    },
    {
        "name": "Claude Haiku 4.5",
        # Fast mode is a first-class participant control, not a soft hint.
        # Pin the global inference profile so preflight proves the exact profile
        # the app and managed Runtime invoke for that option.
        "model_id": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "required": True,
        "role": "fast",
        "access_hint": (
            "Enable Claude Haiku 4.5 in Bedrock model access."
        ),
        "body": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Say hi."}],
        },
    },
    {
        "name": "Cohere Rerank v3.5",
        "model_id": "cohere.rerank-v3-5:0",
        "required": True,  # Anna's rerank proof + search_products at runtime
        "api": "bedrock-agent-runtime.rerank",
        "body": {
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
        # the configured region via config.BEDROCK_EMBEDDING_MODEL = "us.cohere.embed-v4:0",
        # so the probe resolves and persists the working form for BOTH backend
        # and MCP tool Lambdas: the US cross-region inference profile and (if the
        # account exposes it) the bare on-demand id. Do not probe eu./apac./global.
        # profiles, which could route workshop data outside its US deployment.
        # If neither accepted form can be invoked, fail rather than retaining
        # a stale successful preflight marker.
        #
        # output_dimension=1024 keeps vectors aligned with the vector(1024)
        # schema + committed cache.
        "name": "Cohere Embed v4",
        "model_id_variants": [
            "us.cohere.embed-v4:0",
            "cohere.embed-v4:0",
        ],
        "required": True,
        "access_hint": (
            "Enable Cohere Embed v4 or check the US inference-profile prefix."
        ),
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
    ok | denied | denied_marketplace | no_ondemand | bad_dim | error."""
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
            # Validation rejection is never invocation proof. Preserve these
            # actionable explanations while failing every rejected payload.
            if "on-demand throughput is" in low and "supported" in low:
                return ("no_ondemand", str(e))
            if "output_dimension" in low:
                return ("bad_dim", str(e))
        return ("error", str(e))


def _rerank_one(client, model_id: str, body: dict):
    model_arn = (
        model_id
        if model_id.startswith("arn:")
        else f"arn:aws:bedrock:{REGION}::foundation-model/{model_id}"
    )
    try:
        client.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": body["query"]}}],
            sources=[
                {
                    "type": "INLINE",
                    "inlineDocumentSource": {
                        "type": "TEXT",
                        "textDocument": {"text": document},
                    },
                }
                for document in body["documents"]
            ],
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {"modelArn": model_arn},
                    "numberOfResults": int(body.get("top_n") or 1),
                },
            },
        )
        return ("ok", "")
    except client.exceptions.AccessDeniedException as e:
        msg = str(e).lower()
        if "private marketplace" in msg or "marketplace subscription" in msg:
            return ("denied_marketplace", str(e))
        return ("denied", str(e))
    except Exception as e:
        return ("error", str(e))


def check_model(client, rerank_client, model: dict) -> bool:
    """Check one model. Supports a single `model_id` or a `model_id_variants`
    list — for the latter, tries each in order and passes on the FIRST that
    works, printing which variant won so config can be set to match."""
    variants = model.get("model_id_variants") or [model["model_id"]]
    body = model["body"]
    multi = len(variants) > 1
    probe = _rerank_one if model.get("api") == "bedrock-agent-runtime.rerank" else _invoke_one
    probe_client = rerank_client if model.get("api") == "bedrock-agent-runtime.rerank" else client

    results = []  # (variant, status, detail) for diagnostics if all fail
    for mid in variants:
        status, detail = probe(probe_client, mid, body)
        if status == "ok":
            if multi:
                model["_note"] = f"Accessible via: {mid}"
                model["_resolved_id"] = mid
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
            + f"\n      {model.get('access_hint', 'Enable one of these models in Bedrock model access.')}"
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
    # When set, persist every resolved model used by the app, Runtime, and
    # managed Runtime so later bootstrap stages cannot fall back to a denied ID.
    parser.add_argument("--write-env", default=None,
                        help="Path to .env to update with resolved model IDs")
    args = parser.parse_args()

    if args.write_env:
        # Clear a stale success marker before making any live calls.
        _upsert_env(args.write_env, "BEDROCK_MODEL_ACCESS_READY", "false")

    client = boto3.client("bedrock-runtime", region_name=REGION)
    rerank_client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    print(f"Checking Bedrock model access in {REGION}...\n")

    results = {}  # name -> (passed, role, resolved_id)
    for model in MODELS:
        model.pop("_resolved_id", None)
        passed = check_model(client, rerank_client, model)
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
        if passed and model.get("_note"):
            print(f"    {model['_note']}")

    # --- Editorial resolution: Opus OR Sonnet must work ---
    opus_ok = results.get("Claude Opus 5", (False,))[0]
    opus_id = results.get("Claude Opus 5", (False, None, ""))[2]
    sonnet_name = "Claude Sonnet"
    sonnet_ok = results.get(sonnet_name, (False,))[0]
    sonnet_id = results.get(sonnet_name, (False, None, ""))[2]
    fast_name = "Claude Haiku 4.5"
    fast_ok = results.get(fast_name, (False,))[0]
    fast_id = results.get(fast_name, (False, None, ""))[2]

    editorial_ok = opus_ok or sonnet_ok
    print()
    if opus_ok:
        print("Editorial agents: \033[32mOpus 5\033[0m (primary).")
    elif sonnet_ok:
        print("Editorial agents: \033[33mOpus 5 unavailable → falling back to Sonnet\033[0m.")
    else:
        print("\033[31mEditorial agents: NEITHER Opus 5 nor a Sonnet fallback is accessible.\033[0m")

    editorial_id = opus_id if opus_ok else sonnet_id
    if editorial_ok and args.write_env:
        _upsert_env(args.write_env, "BEDROCK_OPUS_MODEL", editorial_id)
        _upsert_env(args.write_env, "BEDROCK_CHAT_MODEL", editorial_id)
        print(f"  → wrote BEDROCK_OPUS_MODEL={editorial_id} to {args.write_env}")

    # --- Sonnet role defaults: app routing/reporting + managed Runtime ---
    print()
    if sonnet_ok:
        print(f"Routing/reporting + Runtime: \033[32m{sonnet_id}\033[0m.")
        if args.write_env:
            _upsert_env(args.write_env, "BEDROCK_SONNET_MODEL", sonnet_id)
            _upsert_env(args.write_env, "BEDROCK_ROUTER_MODEL", sonnet_id)
            _upsert_env(args.write_env, "BEDROCK_REPORTING_MODEL", sonnet_id)
            _upsert_env(args.write_env, "AGENT_MODEL_ID", sonnet_id)
            print(f"  → wrote app and Runtime model IDs to {args.write_env}")
    else:
        print("\033[31mRouting/reporting + Runtime: no Sonnet is accessible.\033[0m")

    # --- Fast response mode: Haiku is intentionally required ---
    print()
    if fast_ok:
        print(f"Fast response mode: \033[32m{fast_id}\033[0m.")
        if args.write_env:
            _upsert_env(args.write_env, "BEDROCK_FAST_MODEL", fast_id)
            print(f"  → wrote BEDROCK_FAST_MODEL={fast_id} to {args.write_env}")
    else:
        print("\033[31mFast response mode: Claude Haiku 4.5 is not accessible.\033[0m")

    # Backend settings and the MCP Lambda deployer use distinct environment
    # keys. Persist both before READY so a working bare-model fallback cannot
    # leave either execution path invoking the denied inference profile.
    embedding_ok, _, embedding_id = results["Cohere Embed v4"]
    if embedding_ok and args.write_env:
        _upsert_env(args.write_env, "BEDROCK_EMBEDDING_MODEL", embedding_id)
        _upsert_env(args.write_env, "BEDROCK_EMBED_MODEL_ID", embedding_id)
        print(f"  → wrote backend and MCP embedding model IDs: {embedding_id}")

    # --- Hard-required models (Sonnet, Haiku, Rerank, Embed) ---
    hard = [m["name"] for m in MODELS if m.get("required", True)]
    hard_missing = [n for n in hard if not results.get(n, (False,))[0]]

    print()
    if editorial_ok and not hard_missing:
        if args.write_env:
            _upsert_env(args.write_env, "BEDROCK_MODEL_ACCESS_READY", "true")
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
