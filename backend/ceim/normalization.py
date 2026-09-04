"""Deterministic source-value normalization with retained change evidence."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_SPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NUMBER_KEYS = {"amount", "count", "length", "width", "height", "weight", "quantity", "value", "tolerance", "number"}


def _string(value: str, key: str) -> tuple[Any, str | None]:
    cleaned = _SPACE.sub(" ", _CONTROL.sub("", unicodedata.normalize("NFC", value).replace("\ufeff", ""))).strip()
    if not cleaned:
        return "", "empty_after_text_cleanup" if value else None
    key_lower = key.casefold()
    if any(token in key_lower for token in ("date", "time", "timestamp")):
        candidate = cleaned.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
            normalized = parsed.isoformat()
            return normalized, "iso8601_datetime" if normalized != value else None
        except ValueError:
            pass
    if any(token in key_lower for token in _NUMBER_KEYS):
        candidate = cleaned.replace(",", "")
        try:
            number = Decimal(candidate)
            normalized = format(number.normalize(), "f")
            return normalized, "decimal" if normalized != value else None
        except InvalidOperation:
            pass
    return cleaned, "unicode_text" if cleaned != value else None


def normalize_value(value: Any, *, key: str = "") -> tuple[Any, list[dict[str, str]]]:
    """Return canonical JSON-safe value plus non-sensitive transformation evidence."""
    if isinstance(value, str):
        normalized, rule = _string(value, key)
        return normalized, ([{"field": key, "rule": rule}] if rule else [])
    if isinstance(value, dict):
        result, evidence = {}, []
        for child_key, child_value in value.items():
            normalized, changes = normalize_value(child_value, key=str(child_key))
            result[str(child_key)] = normalized; evidence.extend(changes)
        return result, evidence
    if isinstance(value, list):
        result, evidence = [], []
        for child in value:
            normalized, changes = normalize_value(child, key=key)
            result.append(normalized); evidence.extend(changes)
        return result, evidence
    return value, []


def normalize_record(record: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if not isinstance(record, dict):
        raise ValueError("Source record must be an object")
    normalized, evidence = normalize_value(record)
    return dict(normalized), evidence
