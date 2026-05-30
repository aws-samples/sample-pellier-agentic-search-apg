"""
Guardrails Service — Bedrock Guardrails ApplyGuardrail integration.

The input/output checks are fully implemented. Enforcement activates only
when ``BEDROCK_GUARDRAIL_ID`` is set; otherwise the service runs in
pass-through mode (allow-all) so the boutique works without a provisioned
guardrail. In the Builder's Session this is an inspect-only surface — the
Atelier shows the config and attach point — so we do not make every turn
depend on a live ApplyGuardrail round-trip.
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
        Check user input against Bedrock Guardrails (source="INPUT").

        Calls ApplyGuardrail when a guardrail is configured and parses the
        response action (GUARDRAIL_INTERVENED → blocked). Returns allow-all
        in pass-through mode.

        Returns:
            {allowed: bool, action: str, violations: list}
        """
        if not self.is_configured:
            return {"allowed": True, "action": "NONE", "violations": [], "mode": "pass-through"}

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

    def check_output(self, text: str) -> Dict[str, Any]:
        """
        Check model output against Bedrock Guardrails (source="OUTPUT").

        Same contract as check_input. Returns allow-all in pass-through mode.

        Returns:
            {allowed: bool, action: str, violations: list}
        """
        if not self.is_configured:
            return {"allowed": True, "action": "NONE", "violations": [], "mode": "pass-through"}

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
