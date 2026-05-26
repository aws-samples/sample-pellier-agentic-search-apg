#!/usr/bin/env python3
"""
Deploy Pellier MCP Servers to Amazon Bedrock AgentCore Gateway.

Creates a gateway with 4 Lambda targets: search, pricing, recommendations,
experience. The ``search`` target now also exposes ``find_pieces_hybrid``
(vector + FTS + Cohere Rerank), and the new ``experience`` target carries
the two Theo-flow tools — ``process_return`` and ``escalate_to_stylist`` —
that previously stayed in-process. Together these surface every backend
``@tool`` (13 of 13) over Gateway, closing the gateway-vs-backend asymmetry.
Adapted from DAT403 deploy_gateway_simple.py for Pellier.
"""
import boto3
import json
import os
import sys
import time
import argparse
import logging
from typing import Dict, List, Any
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Tool schemas for Pellier MCP servers
TOOL_SCHEMAS = {
    "search": {
        "target_name": "pellier-search-server-function",
        "description": "Pellier search and inventory MCP server",
        "tools": [
            {
                "name": "semantic_search",
                "description": "Search products by natural language query using vector similarity.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "limit": {"type": "integer", "description": "Max results", "default": 5},
                        "max_price": {"type": "number", "description": "Maximum price filter"},
                        "min_rating": {"type": "number", "description": "Minimum star rating"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "find_pieces_hybrid",
                "description": (
                    "Hybrid retrieval: pgvector cosine + Postgres FTS merged via "
                    "RRF, then reranked by Cohere Rerank v3.5. Higher quality "
                    "than semantic_search at the cost of one extra Bedrock call."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "max_price": {"type": "number", "description": "Maximum price filter (post-rerank)"},
                        "min_rating": {"type": "number", "description": "Minimum star rating (post-rerank)", "default": 0.0},
                        "category": {"type": "string", "description": "Category substring filter (post-rerank)"},
                        "limit": {"type": "integer", "description": "Max results", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_inventory_health",
                "description": "Get inventory health summary across categories.",
                "inputSchema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "get_low_stock_products",
                "description": "Get products with critically low stock.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 5}},
                    "required": [],
                },
            },
            {
                "name": "restock_product",
                "description": "Restock a product (max 500 per policy).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string"},
                        "quantity": {"type": "integer"},
                    },
                    "required": ["product_id", "quantity"],
                },
            },
        ],
    },
    "pricing": {
        "target_name": "pellier-pricing-server-function",
        "description": "Pellier pricing analysis MCP server",
        "tools": [
            {
                "name": "find_deals",
                "description": "Find best-value products by rating-to-price ratio.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_price": {"type": "number"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_price_analysis",
                "description": "Price statistics by category.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"category": {"type": "string"}},
                    "required": [],
                },
            },
            {
                "name": "compare_products",
                "description": "Compare two products side by side.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_id_1": {"type": "string"},
                        "product_id_2": {"type": "string"},
                    },
                    "required": ["product_id_1", "product_id_2"],
                },
            },
        ],
    },
    "recommendation": {
        "target_name": "pellier-recommend-server-function",
        "description": "Pellier product recommendation MCP server",
        "tools": [
            {
                "name": "get_recommendations",
                "description": "Personalized product recommendations via semantic search.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "category": {"type": "string"},
                        "max_price": {"type": "number"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_trending_products",
                "description": "Most popular products by recent purchases.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 10},
                        "category": {"type": "string"},
                    },
                    "required": [],
                },
            },
        ],
    },
    "experience": {
        "target_name": "pellier-experience-server-function",
        "description": "Pellier experience-guide MCP server (returns + stylist handoff)",
        "tools": [
            {
                "name": "process_return",
                "description": (
                    "Process a return atomically: ownership check + INSERT into "
                    "pellier.returns + (if damaged) decrement product_catalog "
                    "quantity. Reason must be one of damaged, wrong_size, "
                    "not_as_described, changed_mind, other."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "product_id": {"type": "integer"},
                        "reason": {
                            "type": "string",
                            "enum": [
                                "changed_mind",
                                "damaged",
                                "not_as_described",
                                "other",
                                "wrong_size",
                            ],
                        },
                    },
                    "required": ["customer_id", "product_id", "reason"],
                },
            },
            {
                "name": "escalate_to_stylist",
                "description": (
                    "Hand the conversation off to a human stylist. Honest "
                    "fallback when no catalog tool can answer (cultural "
                    "dressing norms, body-image fit, out-of-policy returns)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                        "customer_id": {"type": "string"},
                    },
                    "required": [],
                },
            },
        ],
    },
}


@dataclass
class MCPTarget:
    lambda_arn: str
    server_type: str  # "search", "pricing", "recommendation"


@dataclass
class GatewayConfig:
    region: str = "us-east-1"
    gateway_name: str = "pellier-gateway"
    targets: List[MCPTarget] = field(default_factory=list)
    cognito_user_pool_id: str = None
    cognito_client_id: str = None

    @property
    def role_name(self):
        return f"{self.gateway_name}-role"


class BazaarGatewayDeployer:
    """Deploys Pellier MCP servers to AgentCore Gateway."""

    def __init__(self, config: GatewayConfig):
        self.config = config
        self.session = boto3.Session(region_name=config.region)
        self.agentcore = self.session.client("bedrock-agentcore-control")
        self.iam = self.session.client("iam")

    def deploy(self) -> Dict[str, Any]:
        logger.info("Starting Bazaar Gateway deployment...")

        lambda_arns = [t.lambda_arn for t in self.config.targets]
        role_arn = self._ensure_role(lambda_arns)

        gateway_id = self._get_existing_gateway()
        if gateway_id:
            logger.info(f"Gateway '{self.config.gateway_name}' exists: {gateway_id}")
            self._update_role_policy(lambda_arns)
        else:
            gateway_id = self._create_gateway(role_arn)

        for target in self.config.targets:
            self._add_target(gateway_id, target)

        info = self.agentcore.get_gateway(gatewayIdentifier=gateway_id)
        logger.info("Gateway deployment complete!")

        return {
            "gateway_id": gateway_id,
            "gateway_url": info.get("gatewayUrl"),
            "targets": [t.server_type for t in self.config.targets],
            "region": self.config.region,
        }

    def _get_existing_gateway(self) -> str | None:
        try:
            for gw in self.agentcore.list_gateways().get("items", []):
                if gw.get("name") == self.config.gateway_name:
                    return gw["gatewayId"]
        except Exception:
            pass
        return None

    def _ensure_role(self, lambda_arns: List[str]) -> str:
        role_name = self.config.role_name
        trust = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole"}
            ],
        }
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["lambda:InvokeFunction"], "Resource": lambda_arns},
                {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], "Resource": "*"},
            ],
        }
        try:
            resp = self.iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust))
            role_arn = resp["Role"]["Arn"]
            logger.info(f"Created IAM role: {role_arn}")
            time.sleep(10)
        except self.iam.exceptions.EntityAlreadyExistsException:
            resp = self.iam.get_role(RoleName=role_name)
            role_arn = resp["Role"]["Arn"]
            logger.info(f"IAM role exists: {role_arn}")

        self.iam.put_role_policy(RoleName=role_name, PolicyName=f"{role_name}-policy", PolicyDocument=json.dumps(policy))
        return role_arn

    def _update_role_policy(self, lambda_arns: List[str]):
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["lambda:InvokeFunction"], "Resource": lambda_arns},
                {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], "Resource": "*"},
            ],
        }
        self.iam.put_role_policy(RoleName=self.config.role_name, PolicyName=f"{self.config.role_name}-policy", PolicyDocument=json.dumps(policy))

    def _create_gateway(self, role_arn: str) -> str:
        params = {
            "name": self.config.gateway_name,
            "roleArn": role_arn,
            "description": "Pellier MCP Gateway — search, pricing, recommendations, experience",
            "protocolType": "MCP",
            "protocolConfiguration": {"mcp": {"searchType": "SEMANTIC", "supportedVersions": ["2025-03-26"]}},
        }
        if self.config.cognito_user_pool_id and self.config.cognito_client_id:
            discovery = f"https://cognito-idp.{self.config.region}.amazonaws.com/{self.config.cognito_user_pool_id}/.well-known/openid-configuration"
            params["authorizerType"] = "CUSTOM_JWT"
            params["authorizerConfiguration"] = {"customJWTAuthorizer": {"discoveryUrl": discovery, "allowedClients": [self.config.cognito_client_id]}}
        else:
            params["authorizerType"] = "NONE"

        resp = self.agentcore.create_gateway(**params)
        gw_id = resp["gatewayId"]
        logger.info(f"Created gateway: {gw_id}")
        self._wait_ready(gw_id)
        return gw_id

    def _wait_ready(self, gateway_id: str, timeout: int = 300):
        logger.info("Waiting for gateway to be ready...")
        start = time.time()
        while time.time() - start < timeout:
            status = self.agentcore.get_gateway(gatewayIdentifier=gateway_id).get("status")
            logger.info(f"  status: {status}")
            if status == "READY":
                return
            if status in ("FAILED", "DELETING", "DELETED"):
                raise RuntimeError(f"Gateway failed: {status}")
            time.sleep(10)
        raise TimeoutError("Gateway not ready within timeout")

    def _add_target(self, gateway_id: str, target: MCPTarget):
        schema = TOOL_SCHEMAS.get(target.server_type)
        if not schema:
            raise ValueError(f"Unknown server type: {target.server_type}")

        target_name = schema["target_name"]
        try:
            existing = self.agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)
            for t in existing.get("items", []):
                if t.get("name") == target_name:
                    logger.info(f"Target '{target_name}' already exists, skipping")
                    return
        except Exception:
            pass

        self.agentcore.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=target_name,
            description=schema["description"],
            targetConfiguration={"mcp": {"lambda": {"lambdaArn": target.lambda_arn, "toolSchema": {"inlinePayload": schema["tools"]}}}},
            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
        )
        logger.info(f"Added target '{target_name}'")


def main():
    parser = argparse.ArgumentParser(description="Deploy Pellier MCP servers to AgentCore Gateway")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--gateway-name", default="pellier-gateway")
    parser.add_argument("--search-lambda-arn", required=True)
    parser.add_argument("--pricing-lambda-arn", required=True)
    parser.add_argument("--recommendation-lambda-arn", required=True)
    parser.add_argument("--experience-lambda-arn", required=True)
    parser.add_argument("--cognito-user-pool-id")
    parser.add_argument("--cognito-client-id")
    args = parser.parse_args()

    config = GatewayConfig(
        region=args.region,
        gateway_name=args.gateway_name,
        targets=[
            MCPTarget(lambda_arn=args.search_lambda_arn, server_type="search"),
            MCPTarget(lambda_arn=args.pricing_lambda_arn, server_type="pricing"),
            MCPTarget(lambda_arn=args.recommendation_lambda_arn, server_type="recommendation"),
            MCPTarget(lambda_arn=args.experience_lambda_arn, server_type="experience"),
        ],
        cognito_user_pool_id=args.cognito_user_pool_id,
        cognito_client_id=args.cognito_client_id,
    )

    result = BazaarGatewayDeployer(config).deploy()

    print("\n" + "=" * 60)
    print("BAZAAR GATEWAY DEPLOYMENT COMPLETE")
    print("=" * 60)
    print(f"Gateway ID:  {result['gateway_id']}")
    print(f"Gateway URL: {result['gateway_url']}")
    print(f"Targets:     {', '.join(result['targets'])}")
    print("=" * 60)

    with open("bazaar_gateway_deployment.json", "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
