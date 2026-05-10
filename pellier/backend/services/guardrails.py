"""
Guardrails Service — Bedrock Guardrails API integration for responsible AI.

Wire It Live: Participants implement check_input() and check_output() using
the Bedrock Guardrails ApplyGuardrail API.
"""
import re
import logging
from typing import Dict, Any

from config import get_settings

logger = logging.getLogger(__name__)


class GuardrailsService:
    """Bedrock Guardrails integration for input/output safety checks."""

    def __init__(self):
        settings = get_settings()
        self.guardrail_id = settings.BEDROCK_GUARDRAIL_ID or ""
        self.guardrail_version = settings.BEDROCK_GUARDRAIL_VERSION
        self._client = None

        if self.guardrail_id:
            try:
                import boto3
                self._client = boto3.client("bedrock-runtime")
                logger.info(f"Guardrails service initialized (ID: {self.guardrail_id})")
            except Exception as e:
                logger.warning(f"Failed to init Bedrock client for guardrails: {e}")
        else:
            logger.info("No BEDROCK_GUARDRAIL_ID set — guardrails in pass-through mode")

    @property
    def is_configured(self) -> bool:
        return bool(self.guardrail_id and self._client)

    def check_input(self, text: str) -> Dict[str, Any]:
        """
        Check user input against Bedrock Guardrails.

        Wire It Live: TODO — call self._client.apply_guardrail(
            guardrailIdentifier=self.guardrail_id,
            guardrailVersion=self.guardrail_version,
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
        Parse the response action: GUARDRAIL_INTERVENED → blocked.

        Returns:
            {allowed: bool, action: str, violations: list}
        """
        if not self.is_configured:
            return {"allowed": True, "action": "NONE", "violations": [], "mode": "pass-through"}

        # === WIRE IT LIVE (Lab 3) ===
        try:
            response = self._client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source="INPUT",
                content=[{"text": {"text": text}}],
            )
            action = response.get("action", "NONE")
            assessments = response.get("assessments", [])
            violations = []
            for assessment in assessments:
                for policy in assessment.get("contentPolicy", {}).get("filters", []):
                    if policy.get("action") == "BLOCKED":
                        violations.append({
                            "type": policy.get("type", "unknown"),
                            "confidence": policy.get("confidence", "NONE"),
                        })
            return {
                "allowed": action != "GUARDRAIL_INTERVENED",
                "action": action,
                "violations": violations,
            }
        except Exception as e:
            logger.warning(f"Guardrail input check failed: {e}")
            return {"allowed": True, "action": "ERROR", "violations": []}
        # === END WIRE IT LIVE ===

    def check_output(self, text: str) -> Dict[str, Any]:
        """
        Check model output against Bedrock Guardrails.

        Wire It Live: TODO — same as check_input but with source="OUTPUT".

        Returns:
            {allowed: bool, action: str, violations: list}
        """
        if not self.is_configured:
            return {"allowed": True, "action": "NONE", "violations": [], "mode": "pass-through"}

        # === WIRE IT LIVE (Lab 3) ===
        try:
            response = self._client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source="OUTPUT",
                content=[{"text": {"text": text}}],
            )
            action = response.get("action", "NONE")
            assessments = response.get("assessments", [])
            violations = []
            for assessment in assessments:
                for policy in assessment.get("contentPolicy", {}).get("filters", []):
                    if policy.get("action") == "BLOCKED":
                        violations.append({
                            "type": policy.get("type", "unknown"),
                            "confidence": policy.get("confidence", "NONE"),
                        })
            return {
                "allowed": action != "GUARDRAIL_INTERVENED",
                "action": action,
                "violations": violations,
            }
        except Exception as e:
            logger.warning(f"Guardrail output check failed: {e}")
            return {"allowed": True, "action": "ERROR", "violations": []}
        # === END WIRE IT LIVE ===

    def detect_pii(self, text: str) -> Dict[str, Any]:
        """Basic regex-based PII detection for demo purposes."""
        findings = []

        # Email
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        if emails:
            findings.append({"type": "EMAIL", "count": len(emails), "examples": [e[:3] + "***" for e in emails[:2]]})

        # Phone numbers (US format)
        phones = re.findall(r'\b(?:\+1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b', text)
        if phones:
            findings.append({"type": "PHONE", "count": len(phones), "examples": ["***-***-" + p[-4:] for p in phones[:2]]})

        # SSN
        ssns = re.findall(r'\b\d{3}-\d{2}-\d{4}\b', text)
        if ssns:
            findings.append({"type": "SSN", "count": len(ssns), "examples": ["***-**-" + s[-4:] for s in ssns[:2]]})

        return {
            "has_pii": len(findings) > 0,
            "findings": findings,
            "text_length": len(text),
        }
