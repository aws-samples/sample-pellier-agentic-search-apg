"""
AgentCore Policy Service — Cedar-based policy evaluation for agent actions.

Provides local Cedar policy evaluation with default deny-list rules
for restricted categories, price ceilings, and restock limits.
"""
import logging
import re
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Default Cedar policies
DEFAULT_POLICIES = [
    {
        "id": "max-restock-quantity",
        "name": "Maximum Restock Quantity",
        "description": "Prevent restocking more than 500 units at once",
        "cedar": (
            'forbid (\n'
            '  principal,\n'
            '  action == Action::"restock_shelf",\n'
            '  resource\n'
            ')\n'
            'when { resource.quantity > 500 };'
        ),
        "applies_to": "restock_shelf",
    },
    {
        "id": "restrict-categories",
        "name": "Restricted Categories",
        "description": "Block searches for weapons, tobacco, and alcohol",
        "cedar": (
            'forbid (\n'
            '  principal,\n'
            '  action == Action::"find_pieces",\n'
            '  resource\n'
            ')\n'
            'when {\n'
            '  resource.query like "*weapon*" ||\n'
            '  resource.query like "*tobacco*" ||\n'
            '  resource.query like "*alcohol*" ||\n'
            '  resource.query like "*gun*" ||\n'
            '  resource.query like "*ammunition*"\n'
            '};'
        ),
        "applies_to": "find_pieces",
    },
    {
        "id": "price-ceiling",
        "name": "Price Ceiling",
        "description": "Block price optimization above $10,000",
        "cedar": (
            'forbid (\n'
            '  principal,\n'
            '  action == Action::"set_price",\n'
            '  resource\n'
            ')\n'
            'when { resource.price > 10000 };'
        ),
        "applies_to": "set_price",
    },
    {
        "id": "process-return-allowed-reasons",
        "name": "Process Return — Allowed Reasons",
        "description": (
            "Reject return reasons not in the canonical set. The reason "
            "field drives both Cedar enforcement here and the workflow "
            "branch in BusinessLogic.process_return (only 'damaged' "
            "decrements quantity), so a free-form reason would silently "
            "skip the inventory adjustment. Cedar gates it before the "
            "tool runs; the SQL CHECK constraint is defense-in-depth."
        ),
        "cedar": (
            'forbid (\n'
            '  principal,\n'
            '  action == Action::"process_return",\n'
            '  resource\n'
            ')\n'
            'when {\n'
            '  !(resource.reason in '
            '["damaged","wrong_size","not_as_described","changed_mind","other"])\n'
            '};'
        ),
        "applies_to": "process_return",
    },
]

# Canonical set of return reasons. Mirrored in:
#   - the Cedar policy `process-return-allowed-reasons` above
#   - the SQL CHECK constraint in scripts/migrations/005_theo_returns.sql
#   - the defense-in-depth guard in BusinessLogic.process_return
# Three layers, one truth.
RETURN_REASONS = {
    "damaged", "wrong_size", "not_as_described", "changed_mind", "other",
}

RESTRICTED_WORDS = {"weapon", "weapons", "gun", "guns", "ammunition", "tobacco", "alcohol"}


class PolicyService:
    """Evaluate agent actions against Cedar policies (local engine)."""

    def __init__(self):
        self.policies = list(DEFAULT_POLICIES)
        logger.info(f"PolicyService initialized with {len(self.policies)} default policies")

    def list_policies(self) -> List[Dict[str, Any]]:
        return self.policies

    def evaluate(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate an action against all matching Cedar policies.

        Returns:
            {
                "decision": "ALLOW" | "DENY",
                "violations": [...],
                "matching_policies": [...],
            }
        """
        violations: List[Dict[str, Any]] = []
        matching_policies: List[str] = []

        for policy in self.policies:
            if policy["applies_to"] != action:
                continue

            matching_policies.append(policy["id"])
            violation = self._check_policy(policy, action, parameters)
            if violation:
                violations.append(violation)

        decision = "DENY" if violations else "ALLOW"
        return {
            "decision": decision,
            "action": action,
            "parameters": parameters,
            "violations": violations,
            "matching_policies": matching_policies,
            "policies_evaluated": len(matching_policies),
        }

    def _check_policy(
        self, policy: Dict[str, Any], action: str, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Evaluate a single Cedar-style policy against an action + params.

        Returns a violation dict if the action is denied, or None if allowed.
        Handles the boutique's three operational policies: max-restock-quantity,
        restrict-categories, and price-ceiling. This is the live enforcement
        path consulted by ``policy_hook.PolicyEnforcementHook`` before every
        mutating tool call.
        """
        pid = policy["id"]

        if pid == "max-restock-quantity":
            try:
                qty = float(params.get("quantity", 0))
            except (TypeError, ValueError):
                qty = 0
            if qty > 500:
                return {
                    "policy_id": pid,
                    "policy_name": policy["name"],
                    "reason": f"Restock quantity {qty} exceeds maximum of 500 units",
                    "cedar_condition": "resource.quantity > 500",
                }

        elif pid == "restrict-categories":
            query = str(params.get("query", "")).lower()
            found = RESTRICTED_WORDS & set(re.findall(r'\w+', query))
            if found:
                return {
                    "policy_id": pid,
                    "policy_name": policy["name"],
                    "reason": f"Query contains restricted terms: {', '.join(sorted(found))}",
                    "cedar_condition": 'resource.query like "*<term>*"',
                }

        elif pid == "price-ceiling":
            try:
                price = float(params.get("price", 0))
            except (TypeError, ValueError):
                price = 0
            if price > 10000:
                return {
                    "policy_id": pid,
                    "policy_name": policy["name"],
                    "reason": f"Price ${price:,.2f} exceeds ceiling of $10,000",
                    "cedar_condition": "resource.price > 10000",
                }

        elif pid == "process-return-allowed-reasons":
            reason = str(params.get("reason", "")).strip().lower()
            if reason not in RETURN_REASONS:
                return {
                    "policy_id": pid,
                    "policy_name": policy["name"],
                    "reason": (
                        f"Return reason '{reason}' is not in the allowed set "
                        f"({', '.join(sorted(RETURN_REASONS))})."
                    ),
                    "cedar_condition": (
                        'resource.reason in '
                        '["damaged","wrong_size","not_as_described",'
                        '"changed_mind","other"]'
                    ),
                }

        return None


# Singleton (thread-safe)
_policy_service: Optional[PolicyService] = None
_policy_lock = threading.Lock()


def get_policy_service() -> PolicyService:
    global _policy_service
    if _policy_service is None:
        with _policy_lock:
            if _policy_service is None:
                _policy_service = PolicyService()
    return _policy_service


# ============================================================================
# AgentCore Policy API — Natural Language Policy Creation
# ============================================================================

def create_policy_from_natural_language(
    gateway_id: str,
    policy_name: str,
    natural_language_rule: str,
    region: str = None,
) -> Dict[str, Any]:
    """
    Create an AgentCore Policy from a natural language description.

    AgentCore Policy automatically compiles natural language rules into
    Cedar policies and attaches them to the Gateway for real-time enforcement.
    This replaces the need to write Cedar syntax manually.

    Example natural language rules:
        - "Forbid restocking more than 500 units in a single operation"
        - "Allow all agents to search products but block weapons and tobacco"
        - "Only allow the inventory agent to call restock_shelf"

    Args:
        gateway_id: AgentCore Gateway ID to attach the policy to
        policy_name: Human-readable policy name
        natural_language_rule: Plain English description of the policy rule
        region: AWS region (defaults to settings.AWS_REGION)

    Returns:
        Dict with policy_id, cedar_statement, and status
    """
    import boto3
    from config import settings

    region = region or settings.AWS_REGION

    try:
        client = boto3.client("bedrock-agentcore-control", region_name=region)

        # Step 1: Create or get the policy engine for this gateway
        policy_engine_id = _get_or_create_policy_engine(client, gateway_id)

        # Step 2: Create the policy using natural language
        # AgentCore auto-compiles to Cedar
        response = client.create_policy(
            policyEngineId=policy_engine_id,
            name=policy_name,
            description=natural_language_rule,
            validationMode="FAIL_ON_ANY_FINDINGS",
            definition={
                "naturalLanguage": {
                    "statement": natural_language_rule,
                }
            },
        )

        policy_id = response.get("policyId", "")
        logger.info(f"✅ Policy created from natural language: {policy_id}")

        return {
            "policy_id": policy_id,
            "name": policy_name,
            "natural_language": natural_language_rule,
            "status": response.get("status", "CREATING"),
            "policy_engine_id": policy_engine_id,
        }

    except ImportError:
        logger.warning("boto3 not available for AgentCore Policy API")
        return {"error": "boto3 not available"}
    except Exception as e:
        logger.error(f"Failed to create NL policy: {e}")
        return {"error": str(e)}


def _get_or_create_policy_engine(client, gateway_id: str) -> str:
    """Get existing policy engine for a gateway, or create one."""
    try:
        # List existing policy engines
        response = client.list_policy_engines()
        for engine in response.get("policyEngines", []):
            if engine.get("gatewayId") == gateway_id:
                return engine["policyEngineId"]

        # Create new policy engine attached to the gateway
        response = client.create_policy_engine(
            name=f"pellier-policy-engine",
            description="Policy engine for Pellier agent actions",
            gatewayIdentifier=gateway_id,
        )
        engine_id = response["policyEngineId"]
        logger.info(f"✅ Policy engine created: {engine_id}")
        return engine_id

    except Exception as e:
        logger.error(f"Failed to get/create policy engine: {e}")
        raise
