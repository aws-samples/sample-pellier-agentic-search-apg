"""
AgentCore Policy Service — Cedar-based policy evaluation for agent actions.

Solution: _check_policy() implemented with all three policy checks,
plus natural language policy creation via AgentCore Policy API.
"""
import logging
import re
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_POLICIES = [
    {
        "id": "max-restock-quantity",
        "name": "Maximum Restock Quantity",
        "description": "Prevent restocking more than 500 units at once",
        "cedar": (
            'forbid (\n  principal,\n  action == Action::"restock_product",\n'
            '  resource\n)\nwhen { resource.quantity > 500 };'
        ),
        "applies_to": "restock_product",
    },
    {
        "id": "restrict-categories",
        "name": "Restricted Categories",
        "description": "Block searches for weapons, tobacco, and alcohol",
        "cedar": (
            'forbid (\n  principal,\n  action == Action::"search_products",\n'
            '  resource\n)\nwhen {\n  resource.query like "*weapon*" ||\n'
            '  resource.query like "*tobacco*" ||\n  resource.query like "*alcohol*" ||\n'
            '  resource.query like "*gun*" ||\n  resource.query like "*ammunition*"\n};'
        ),
        "applies_to": "search_products",
    },
    {
        "id": "price-ceiling",
        "name": "Price Ceiling",
        "description": "Block price optimization above $10,000",
        "cedar": (
            'forbid (\n  principal,\n  action == Action::"set_price",\n'
            '  resource\n)\nwhen { resource.price > 10000 };'
        ),
        "applies_to": "set_price",
    },
]

RESTRICTED_WORDS = {"weapon", "weapons", "gun", "guns", "ammunition", "tobacco", "alcohol"}


class PolicyService:
    """Evaluate agent actions against Cedar policies (local engine)."""

    def __init__(self):
        self.policies = list(DEFAULT_POLICIES)
        logger.info(f"PolicyService initialized with {len(self.policies)} default policies")

    def list_policies(self) -> List[Dict[str, Any]]:
        return self.policies

    def evaluate(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
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

    def _check_policy(self, policy, action, params):
        """Check a single policy against parameters."""
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

        return None


_policy_service: Optional[PolicyService] = None
_policy_lock = threading.Lock()


def get_policy_service() -> PolicyService:
    global _policy_service
    if _policy_service is None:
        with _policy_lock:
            if _policy_service is None:
                _policy_service = PolicyService()
    return _policy_service


def create_policy_from_natural_language(
    gateway_id: str,
    policy_name: str,
    natural_language_rule: str,
    region: str = None,
) -> Dict[str, Any]:
    """Create an AgentCore Policy from a natural language description."""
    import boto3
    from config import settings

    region = region or settings.AWS_REGION

    try:
        client = boto3.client("bedrock-agentcore-control", region_name=region)
        policy_engine_id = _get_or_create_policy_engine(client, gateway_id)

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

    except Exception as e:
        logger.error(f"Failed to create NL policy: {e}")
        return {"error": str(e)}


def _get_or_create_policy_engine(client, gateway_id: str) -> str:
    """Get existing policy engine for a gateway, or create one."""
    try:
        response = client.list_policy_engines()
        for engine in response.get("policyEngines", []):
            if engine.get("gatewayId") == gateway_id:
                return engine["policyEngineId"]

        response = client.create_policy_engine(
            name="pellier-policy-engine",
            description="Policy engine for Pellier agent actions",
            gatewayIdentifier=gateway_id,
        )
        engine_id = response["policyEngineId"]
        logger.info(f"✅ Policy engine created: {engine_id}")
        return engine_id

    except Exception as e:
        logger.error(f"Failed to get/create policy engine: {e}")
        raise
