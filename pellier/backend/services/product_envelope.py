"""Normalize product records observed in tool-result envelopes."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable


def select_products_for_reply(
    reply: str,
    candidates: Iterable[dict],
    *,
    owned_products: Iterable[dict] = (),
) -> list[dict]:
    """Select grounded cards named in the answer, preferring new pieces.

    Retrieval results remain the full candidate set in the tool evidence.
    Cards show the specialist's selections in prose order; prior purchases
    mentioned as context do not displace a new recommendation.
    """
    normalized_reply = (reply or "").casefold()
    product_rows = [product for product in candidates if isinstance(product, dict)]
    if not normalized_reply or not product_rows:
        return product_rows

    def product_name(product: dict) -> str:
        return str(product.get("name") or product.get("product_description") or "").strip()

    def product_identity(product: dict) -> tuple[str, str] | None:
        product_id = product.get("id") or product.get("productId") or product.get("product_id")
        if product_id is not None and str(product_id).strip():
            return ("id", str(product_id).strip())
        name = product_name(product)
        return ("name", name.casefold()) if name else None

    owned_identities = {
        identity
        for product in owned_products
        if isinstance(product, dict)
        and (identity := product_identity(product)) is not None
    }
    # Longer names claim their text first and matches respect word edges, so a
    # "Linen Shirt" candidate is not selected by the words of "Hadley Linen
    # Shirt". Candidates with the same name may share one mention.
    by_length = sorted(
        ((product_name(product).casefold(), index, product)
         for index, product in enumerate(product_rows) if product_name(product)),
        key=lambda item: -len(item[0]),
    )
    claimed: list[tuple[int, int, str]] = []
    mentioned = []
    for name, index, product in by_length:
        for match in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", normalized_reply):
            start, end = match.span()
            if any(start < other_end and other_start < end and other != name
                   for other_start, other_end, other in claimed):
                continue
            claimed.append((start, end, name))
            mentioned.append((start, index, product))
            break

    if not mentioned:
        return product_rows

    mentioned.sort(key=lambda item: (item[0], item[1]))
    selected = [product for _mention_index, _index, product in mentioned]
    novel = [
        product
        for product in selected
        if product_identity(product) not in owned_identities
    ]
    return novel or selected


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class ProductExtractor:
    """Extract products from direct JSON or fenced JSON tool results."""

    @staticmethod
    def extract(tool_result: Any) -> list[dict[str, Any]]:
        candidates: list[Any] = [tool_result]
        if isinstance(tool_result, str):
            candidates.extend(
                match.group(1)
                for match in re.finditer(
                    r"```json\s*(.*?)\s*```",
                    tool_result,
                    re.DOTALL | re.IGNORECASE,
                )
            )

        products: list[Any] = []
        for candidate in candidates:
            data = candidate
            if isinstance(candidate, str):
                try:
                    data = json.loads(candidate)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(data, dict) and isinstance(data.get("products"), list):
                products.extend(data["products"])
            elif isinstance(data, list):
                products.extend(data)

        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for product in products:
            if not isinstance(product, dict):
                continue
            item = ProductExtractor.normalize(product)
            identity = str(item["productId"] or item["name"]).strip().casefold()
            if not identity or identity in seen:
                continue
            seen.add(identity)
            normalized.append(item)
        return normalized

    @staticmethod
    def normalize(product: dict[str, Any]) -> dict[str, Any]:
        """Project known catalog aliases onto the storefront wire contract."""
        return {
            "productId": product.get("productId") or product.get("product_id", ""),
            "name": str(
                product.get("name") or product.get("product_description", "")
            )[:80],
            "brand": product.get("brand", ""),
            "color": product.get("color", ""),
            "price": _safe_float(product.get("price", 0)),
            "rating": _safe_float(product.get("rating") or product.get("stars", 0)),
            "reviews": _safe_int(product.get("reviews", 0)),
            "category": (
                product.get("category") or product.get("category_name", "")
            ),
            "imgUrl": (
                product.get("imgUrl")
                or product.get("img_url")
                or product.get("image_url")
                or product.get("image")
                or ""
            ),
            "badge": product.get("badge"),
            "tags": list(product.get("tags") or []),
        }
