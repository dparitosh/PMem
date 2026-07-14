"""
Minimal OSLC Query helpers for read-only interoperability.

This module intentionally implements a conservative subset of OSLC Query 3.0:
- oslc.where with simple AND-connected comparisons
- oslc.select
- oslc.orderBy
- oslc.searchTerms
- paging

The goal is to provide a stable query surface on top of the current Neo4j data
model without introducing a second query stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Tuple


class OSLCQueryValidationError(ValueError):
    """Raised when an OSLC query parameter cannot be parsed safely."""


_SAFE_PROPERTY = re.compile(r"^[A-Za-z_][A-Za-z0-9_:-]*$")


@dataclass
class OSLCCondition:
    property_name: str
    operator: str
    value: Any


@dataclass
class OSLCQueryParameters:
    where: List[OSLCCondition] = field(default_factory=list)
    select: List[str] = field(default_factory=list)
    order_by: List[Tuple[str, str]] = field(default_factory=list)
    search_terms: List[str] = field(default_factory=list)
    page_size: int = 50
    page_num: int = 1


class OSLCQueryService:
    """Parse and normalize a conservative OSLC query subset."""

    _OPERATORS = [">=", "<=", "!=", ">", "<", "="]

    @classmethod
    def parse(cls, raw: Dict[str, Any], *, max_page_size: int = 200) -> OSLCQueryParameters:
        params = OSLCQueryParameters()

        if raw.get("oslc.where"):
            params.where = cls._parse_where(str(raw["oslc.where"]))
        if raw.get("oslc.select"):
            params.select = cls._parse_property_list(str(raw["oslc.select"]))
        if raw.get("oslc.orderBy"):
            params.order_by = cls._parse_order_by(str(raw["oslc.orderBy"]))
        if raw.get("oslc.searchTerms"):
            params.search_terms = cls._parse_search_terms(str(raw["oslc.searchTerms"]))

        paging_enabled = str(raw.get("oslc.paging", "")).lower() == "true"
        if paging_enabled:
            params.page_size = cls._bounded_int(raw.get("oslc.pageSize", 50), minimum=1, maximum=max_page_size)
            params.page_num = cls._bounded_int(raw.get("oslc.pageNum", 1), minimum=1, maximum=10_000)
        else:
            params.page_size = cls._bounded_int(raw.get("oslc.pageSize", 50), minimum=1, maximum=max_page_size)
            params.page_num = 1

        return params

    @classmethod
    def _parse_where(cls, raw_where: str) -> List[OSLCCondition]:
        expression = raw_where.strip()
        if not expression:
            return []
        parts = cls._split_boolean_expression(expression)
        conditions: List[OSLCCondition] = []
        for part in parts:
            token = part.strip()
            if not token:
                continue
            conditions.append(cls._parse_condition(token))
        return conditions

    @classmethod
    def _split_boolean_expression(cls, expression: str) -> List[str]:
        """Split AND clauses without treating quoted words as operators."""
        parts: List[str] = []
        start = 0
        quote = ""
        escaped = False
        index = 0
        while index < len(expression):
            char = expression[index]
            if escaped:
                escaped = False
                index += 1
                continue
            if char == "\\" and quote:
                escaped = True
                index += 1
                continue
            if char in {"'", '"'}:
                if not quote:
                    quote = char
                elif quote == char:
                    quote = ""
                index += 1
                continue
            if not quote:
                match = re.match(r"\s+(and|or)\s+", expression[index:], flags=re.IGNORECASE)
                if match:
                    operator = match.group(1).lower()
                    if operator == "or":
                        raise OSLCQueryValidationError("oslc.where currently supports AND-connected clauses only.")
                    parts.append(expression[start:index].strip())
                    index += match.end()
                    start = index
                    continue
            index += 1
        if quote:
            raise OSLCQueryValidationError("Unterminated quoted value in oslc.where.")
        parts.append(expression[start:].strip())
        return [part for part in parts if part]

    @classmethod
    def _parse_search_terms(cls, raw_terms: str) -> List[str]:
        """Parse the OSLC comma-separated quoted search-term form."""
        value = raw_terms.strip()
        if not value:
            return []
        terms: List[str] = []
        current: List[str] = []
        quote = ""
        escaped = False
        for char in value:
            if escaped:
                current.append(char)
                escaped = False
                continue
            if char == "\\" and quote:
                escaped = True
                continue
            if char in {"'", '"'}:
                if not quote:
                    quote = char
                    continue
                if quote == char:
                    quote = ""
                    continue
            if char == "," and not quote:
                term = "".join(current).strip()
                if term:
                    terms.append(term)
                current = []
                continue
            current.append(char)
        if quote:
            raise OSLCQueryValidationError("Unterminated quoted value in oslc.searchTerms.")
        term = "".join(current).strip()
        if term:
            terms.append(term)
        return terms

    @classmethod
    def _parse_condition(cls, token: str) -> OSLCCondition:
        for operator in cls._OPERATORS:
            if operator in token:
                left, right = token.split(operator, 1)
                property_name = cls._sanitize_property(left.strip())
                value = cls._parse_value(right.strip())
                return OSLCCondition(property_name=property_name, operator=operator, value=value)
        raise OSLCQueryValidationError(f"Unsupported oslc.where clause: {token}")

    @classmethod
    def _parse_property_list(cls, raw_list: str) -> List[str]:
        items = [item.strip() for item in raw_list.split(",")]
        return [cls._sanitize_property(item) for item in items if item]

    @classmethod
    def _parse_order_by(cls, raw_order_by: str) -> List[Tuple[str, str]]:
        items = [item.strip() for item in raw_order_by.split(",") if item.strip()]
        order_items: List[Tuple[str, str]] = []
        for item in items:
            direction = "asc"
            field_name = item
            lowered = item.lower()
            if lowered.endswith(" desc"):
                direction = "desc"
                field_name = item[:-5].strip()
            elif lowered.endswith(" asc"):
                field_name = item[:-4].strip()
            order_items.append((cls._sanitize_property(field_name), direction))
        return order_items

    @staticmethod
    def _parse_value(raw_value: str) -> Any:
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        if re.fullmatch(r"-?\d+\.\d+", value):
            return float(value)
        return value

    @staticmethod
    def _sanitize_property(property_name: str) -> str:
        if not property_name:
            raise OSLCQueryValidationError("Property name cannot be empty.")
        if not _SAFE_PROPERTY.fullmatch(property_name):
            raise OSLCQueryValidationError(f"Unsafe property name: {property_name}")
        return property_name

    @staticmethod
    def _bounded_int(raw_value: Any, *, minimum: int, maximum: int) -> int:
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise OSLCQueryValidationError(f"Invalid integer value: {raw_value}") from exc
        return max(minimum, min(maximum, value))
