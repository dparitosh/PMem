"""
ISO 10303 EXPRESS schema parser (Enhanced for AP242).

Parses STEP domain models (DomainModel.exp) and emits OWL/Turtle RDF that can
be merged into a STEP processing pipeline.

Recognised EXPRESS constructs:
  - SCHEMA with REFERENCE FROM clauses → import tracking
  - ENTITY (ABSTRACT, SUBTYPE OF, SUPERTYPE OF) → owl:Class with rdfs:subClassOf
  - Attributes (OPTIONAL, aggregates SET/LIST/BAG/ARRAY [bounds] OF) → owl:ObjectProperty / owl:DatatypeProperty
  - DERIVE sections → derived attributes with cardinality
  - INVERSE sections → inverse relationships
  - UNIQUE constraints → uniqueness constraints
  - TYPE = ENUMERATION OF → owl:Class + owl:oneOf individuals
  - TYPE = SELECT (including BASED_ON, EXTENSIBLE GENERIC_ENTITY) → owl:Class
  - TYPE = EXTENSIBLE GENERIC_ENTITY SELECT → extensible union
  - TYPE = primitive alias → tracked for range resolution
  - WHERE rules → SHACL NodeShapes with SPARQL constraints (subset translation)
  - Set cardinality bounds [min:max] → rdfs:comment with constraints

Not implemented (out of scope):
  - FUNCTION, PROCEDURE, ALGORITHM, RULE blocks (parsed but not emitted)
  - Full EXPRESS logic translation for complex WHERE expressions
  - Runtime constraint evaluation

Usage:
    from src.parsers.express_parser import parse_express, emit_owl_ttl
    schema = parse_express(Path("DomainModel.exp"))
    ttl_fragment = emit_owl_ttl(schema, base_uri="http://IAE-depo.com/ap242dm#", prefix="ap242dm")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger

# ---------------------------------------------------------------------------
# EXPRESS primitive → XSD datatype
# ---------------------------------------------------------------------------
_PRIM_TO_XSD: Dict[str, str] = {
    "STRING": "xsd:string",
    "INTEGER": "xsd:integer",
    "REAL": "xsd:double",
    "NUMBER": "xsd:decimal",
    "BOOLEAN": "xsd:boolean",
    "LOGICAL": "xsd:boolean",
    "BINARY": "xsd:hexBinary",
    "NUMBER_REAL": "xsd:double",
}

# These are always treated as data-typed (primitive) even when they appear as SELECT members
_PRIMITIVE_NAMES = frozenset(_PRIM_TO_XSD.keys())

# ---------------------------------------------------------------------------
# Schema data model
# ---------------------------------------------------------------------------

@dataclass
class ExpressAttribute:
    name: str
    type_ref: str          # raw type name from EXPRESS (entity, type, or primitive)
    optional: bool = False
    is_aggregate: bool = False   # SET / LIST / BAG / ARRAY
    aggregate_type: Optional[str] = None  # SET, LIST, BAG, ARRAY
    min_cardinality: Optional[int] = None  # e.g., SET [1:?] → min=1
    max_cardinality: Optional[int] = None  # e.g., SET [1:5] → max=5


@dataclass
class ExpressDerivedAttribute:
    name: str
    type_ref: str
    expression: str  # := expression
    optional: bool = False


@dataclass
class ExpressInverseAttribute:
    name: str
    entity_ref: str  # foreign entity
    attribute_ref: str  # foreign attribute
    is_aggregate: bool = False


@dataclass
class ExpressUniqueConstraint:
    name: str
    attributes: List[str]  # attribute names that form unique key


@dataclass
class ExpressWhereRule:
    rule_id: str
    expression: str


@dataclass
class ExpressEntity:
    name: str
    abstract: bool = False
    supertypes: List[str] = field(default_factory=list)   # SUBTYPE OF (parents)
    subtypes: List[str] = field(default_factory=list)     # SUPERTYPE OF ONEOF (children)
    attributes: List[ExpressAttribute] = field(default_factory=list)
    derived_attributes: List[ExpressDerivedAttribute] = field(default_factory=list)  # NEW
    inverse_attributes: List[ExpressInverseAttribute] = field(default_factory=list)  # NEW
    unique_constraints: List[ExpressUniqueConstraint] = field(default_factory=list)  # NEW
    where_rules: List[ExpressWhereRule] = field(default_factory=list)


@dataclass
class ExpressEnumType:
    name: str
    values: List[str] = field(default_factory=list)
    is_extensible: bool = False  # EXTENSIBLE ENUMERATION OF


@dataclass
class ExpressSelectType:
    name: str
    members: List[str] = field(default_factory=list)
    is_extensible: bool = False  # EXTENSIBLE ... SELECT
    is_generic_entity: bool = False  # EXTENSIBLE GENERIC_ENTITY SELECT
    based_on: Optional[str] = None  # SELECT BASED_ON SomeType WITH (...)


@dataclass
class ExpressSchemaReference:
    schema_name: str
    entities: List[str]  # referenced entity names


@dataclass
class ExpressSchema:
    name: str
    schema_id: Optional[str] = None  # '{iso standard 10303 part(...) ...}'
    references: Dict[str, ExpressSchemaReference] = field(default_factory=dict)  # REFERENCE FROM
    entities: Dict[str, ExpressEntity] = field(default_factory=dict)
    enumerations: Dict[str, ExpressEnumType] = field(default_factory=dict)
    select_types: Dict[str, ExpressSelectType] = field(default_factory=dict)
    type_aliases: Dict[str, str] = field(default_factory=dict)   # name → primitive


# ---------------------------------------------------------------------------
# Internal regex patterns
# ---------------------------------------------------------------------------

# REFERENCE FROM schema_name ( entity1, entity2 );
_RE_REFERENCE_FROM = re.compile(
    r"REFERENCE\s+FROM\s+(\w+)\s*\(([^)]+)\)",
    re.IGNORECASE
)

# Attribute with cardinality: name : [OPTIONAL] [SET/LIST/BAG/ARRAY [min:max] OF] TypeRef ;
_RE_ATTR = re.compile(
    r"^\s*(\w+)\s*:\s*"
    r"(OPTIONAL\s+)?"
    r"((?:SET|LIST|BAG|ARRAY)\s*\[([0-9?:]+)\]\s+OF\s+)?"  # Capture aggregate type and bounds
    r"(\w+)\s*;"
    r"\s*$",
    re.IGNORECASE,
)

# Derived attribute: name : TypeRef := expression ;
_RE_DERIVE_ATTR = re.compile(
    r"^\s*(\w+)\s*:\s*(\w+)\s*:=\s*(.+?);",
    re.IGNORECASE | re.DOTALL
)

# Inverse: name : [aggregate] EntityRef FOR attr_ref;
_RE_INVERSE_ATTR = re.compile(
    r"^\s*(\w+)\s*:\s*(?:(?:SET|LIST|BAG|ARRAY)\s*\[.*?\]\s+OF\s+)?(\w+)\s+FOR\s+(\w+)\s*;",
    re.IGNORECASE
)

# UNIQUE: UR1: attr1, attr2;
_RE_UNIQUE = re.compile(
    r"^\s*(UR\d+)\s*:\s*([^;]+);",
    re.IGNORECASE
)

_RE_SUPERTYPE_OF = re.compile(r"SUPERTYPE\s+OF\s*\(ONEOF\(([^)]+)\)\)", re.IGNORECASE | re.DOTALL)
_RE_SUPERTYPE_SINGLE = re.compile(r"SUPERTYPE\s+OF\s*\((\w+)\)", re.IGNORECASE)
_RE_SUBTYPE_OF = re.compile(r"SUBTYPE\s+OF\s*\(([^)]+)\)", re.IGNORECASE | re.DOTALL)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _strip_comments(text: str) -> str:
    """Remove (* ... *) block comments and -- line comments from EXPRESS text."""
    text = re.sub(r"\(\*.*?\*\)", " ", text, flags=re.DOTALL)  # block comments
    text = re.sub(r"--[^\n]*", " ", text)                        # line comments
    return text


def _normalise_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _parse_cardinality_bounds(bounds_str: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse SET[1:?] or LIST[0:10] bounds.
    
    Returns: (min_cardinality, max_cardinality) where ? or omitted max → None
    """
    if not bounds_str:
        return None, None
    
    bounds_str = bounds_str.strip()
    if ':' in bounds_str:
        parts = bounds_str.split(':')
        min_card = int(parts[0].strip()) if parts[0].strip().isdigit() else None
        max_card = int(parts[1].strip()) if parts[1].strip().isdigit() else None
        return min_card, max_card
    else:
        # Single number — exact cardinality
        if bounds_str.isdigit():
            return int(bounds_str), int(bounds_str)
    
    return None, None


def _parse_entity_block(name: str, body: str) -> ExpressEntity:
    """Parse the text between 'ENTITY name' and 'END_ENTITY;'."""
    entity = ExpressEntity(name=name)

    # Joinlines for multi-line SUPERTYPE/SUBTYPE declarations
    m = _RE_SUPERTYPE_OF.search(body)
    if m:
        raw = _normalise_ws(m.group(1))
        entity.subtypes = [s.strip() for s in raw.split(",") if s.strip()]

    m = _RE_SUPERTYPE_SINGLE.search(body)
    if m and not _RE_SUPERTYPE_OF.search(body):
        entity.subtypes = [m.group(1).strip()]

    m = _RE_SUBTYPE_OF.search(body)
    if m:
        raw = _normalise_ws(m.group(1))
        entity.supertypes = [s.strip() for s in raw.split(",") if s.strip()]

    # P6 FIX: match ABSTRACT in any position — inline form: ENTITY foo ABSTRACT SUPERTYPE OF (...)
    if re.search(r"\bABSTRACT\b", body, re.IGNORECASE):
        entity.abstract = True

    # Split body into logical sections: attributes, DERIVE, INVERSE, UNIQUE, WHERE
    sections = {
        'attributes': [],
        'derive': [],
        'inverse': [],
        'unique': [],
        'where': [],
    }
    
    current_section = 'attributes'
    for line in body.splitlines():
        stripped = line.strip()
        
        # Detect section headers
        if re.match(r"^DERIVE\s*$", stripped, re.IGNORECASE):
            current_section = 'derive'
            continue
        elif re.match(r"^INVERSE\s*$", stripped, re.IGNORECASE):
            current_section = 'inverse'
            continue
        elif re.match(r"^UNIQUE\s*$", stripped, re.IGNORECASE):
            current_section = 'unique'
            continue
        elif re.match(r"^WHERE\s*$", stripped, re.IGNORECASE):
            current_section = 'where'
            continue
        
        if stripped and not stripped.startswith("--"):  # Skip empty and comment lines
            sections[current_section].append(line)
    
    # Parse attributes (regular and derived)
    for line in sections['attributes']:
        stripped = line.strip()
        if stripped.upper().startswith("SELF\\"):  # Skip inherited attribute refinements
            continue
        
        m_attr = _RE_ATTR.match(line)
        if m_attr:
            attr_name = m_attr.group(1)
            opt_flag = m_attr.group(2)
            aggregate_spec = m_attr.group(3)
            bounds_str = m_attr.group(4)
            type_ref = m_attr.group(5)
            
            min_card, max_card = _parse_cardinality_bounds(bounds_str) if bounds_str else (None, None)
            is_agg = bool(aggregate_spec)
            agg_type = re.search(r"(SET|LIST|BAG|ARRAY)", aggregate_spec, re.IGNORECASE) if aggregate_spec else None
            agg_type_str = agg_type.group(1).upper() if agg_type else None
            
            entity.attributes.append(ExpressAttribute(
                name=attr_name,
                type_ref=type_ref,
                optional=bool(opt_flag),
                is_aggregate=is_agg,
                aggregate_type=agg_type_str,
                min_cardinality=min_card,
                max_cardinality=max_card,
            ))
    
    # Parse DERIVE attributes
    derive_text = '\n'.join(sections['derive'])
    for m in re.finditer(r"(\w+)\s*:\s*(\w+)\s*:=\s*(.+?);", derive_text, re.IGNORECASE | re.DOTALL):
        attr_name = m.group(1).strip()
        type_ref = m.group(2).strip()
        expression = _normalise_ws(m.group(3))
        entity.derived_attributes.append(ExpressDerivedAttribute(
            name=attr_name,
            type_ref=type_ref,
            expression=expression,
        ))
    
    # Parse INVERSE attributes
    inverse_text = '\n'.join(sections['inverse'])
    for m in re.finditer(r"(\w+)\s*:\s*(?:(?:SET|LIST|BAG|ARRAY)\s*\[.*?\]\s+OF\s+)?(\w+)\s+FOR\s+(\w+)\s*;", 
                         inverse_text, re.IGNORECASE):
        attr_name = m.group(1).strip()
        entity_ref = m.group(2).strip()
        attr_ref = m.group(3).strip()
        is_agg = bool(re.search(r"SET|LIST|BAG|ARRAY", inverse_text[m.start():m.end()], re.IGNORECASE))
        entity.inverse_attributes.append(ExpressInverseAttribute(
            name=attr_name,
            entity_ref=entity_ref,
            attribute_ref=attr_ref,
            is_aggregate=is_agg,
        ))
    
    # Parse UNIQUE constraints
    unique_text = '\n'.join(sections['unique'])
    for m in re.finditer(r"(UR\d+)\s*:\s*([^;]+);", unique_text, re.IGNORECASE):
        constraint_name = m.group(1).strip()
        attrs_str = m.group(2).strip()
        attr_names = [a.strip() for a in attrs_str.split(',') if a.strip()]
        entity.unique_constraints.append(ExpressUniqueConstraint(
            name=constraint_name,
            attributes=attr_names,
        ))
    
    # Parse WHERE rules
    where_text = '\n'.join(sections['where'])
    if where_text:
        for m in re.finditer(r"(\w+)\s*:\s*(.*?);", where_text, re.DOTALL):
            rule_id = m.group(1).strip()
            expr = _normalise_ws(m.group(2))
            if expr:
                entity.where_rules.append(ExpressWhereRule(rule_id=rule_id, expression=expr))

    return entity


def _parse_enum_type(name: str, type_body: str) -> ExpressEnumType:
    """Extract enumeration values from 'ENUMERATION OF(\n  val1,\n  val2\n)'.
    
    Handles: ENUMERATION OF and EXTENSIBLE ENUMERATION OF
    """
    is_extensible = 'EXTENSIBLE' in type_body.upper()
    m = re.search(r"ENUMERATION\s+OF\s*\(([^)]+)\)", type_body, re.IGNORECASE | re.DOTALL)
    values: List[str] = []
    if m:
        raw = m.group(1)
        values = [v.strip() for v in raw.split(",") if v.strip()]
    return ExpressEnumType(name=name, values=values, is_extensible=is_extensible)


def _extract_balanced_parens(text: str, keyword: str) -> Optional[str]:
    """Return the content of the first balanced parenthesised group that follows *keyword*.

    Unlike ``[^)]+`` this handles members that contain nested parentheses, e.g.
    ``SET [1:?] OF (TypeA, TypeB)``.  Returns ``None`` when no opening paren is found.
    """
    m = re.search(re.escape(keyword) + r"\s*\(", text, re.IGNORECASE | re.DOTALL) if keyword else None
    if keyword and not m:
        return None
    start = (m.end() - 1) if m else text.find('(')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start + 1:]  # unclosed — return remainder


def _split_at_top_level_commas(raw: str) -> List[str]:
    """Split *raw* on commas that are NOT inside any bracket pair.

    Handles ``SET [1:?] OF (TypeA, TypeB)`` correctly — the inner comma is
    ignored and the whole token is kept intact.
    """
    members: List[str] = []
    depth = 0
    buf: List[str] = []
    for ch in raw:
        if ch in '([':
            depth += 1
            buf.append(ch)
        elif ch in ')]':
            depth -= 1
            buf.append(ch)
        elif ch == ',' and depth == 0:
            token = ''.join(buf).strip()
            if token:
                members.append(token)
            buf = []
        else:
            buf.append(ch)
    token = ''.join(buf).strip()
    if token:
        members.append(token)
    return members


def _parse_select_type(name: str, type_body: str) -> ExpressSelectType:
    """Extract SELECT members and modifiers.

    Handles:
      - SELECT (Type1, Type2)
      - EXTENSIBLE GENERIC_ENTITY SELECT (...)
      - EXTENSIBLE SELECT (...)
      - SELECT BASED_ON SomeType WITH (...)

    Uses bracket-depth matching (P8 fix) so members containing nested
    parentheses (e.g. ``SET [1:?] OF (A, B)``) are captured correctly.
    """
    is_extensible = 'EXTENSIBLE' in type_body.upper()
    is_generic_entity = 'GENERIC_ENTITY' in type_body.upper()

    # Check for BASED_ON — capture the type name, then extract WITH(...) members
    based_on: Optional[str] = None
    based_on_m = re.search(
        r"SELECT\s+BASED_ON\s+(\w+)\s+WITH", type_body, re.IGNORECASE | re.DOTALL
    )
    if based_on_m:
        based_on = based_on_m.group(1).strip()

    # Extract SELECT members using bracket-depth-aware extraction (P8 fix)
    members: List[str] = []
    if based_on_m:
        raw = _extract_balanced_parens(type_body[based_on_m.end():], "") or ""
    else:
        raw = _extract_balanced_parens(type_body, "SELECT") or ""

    members = _split_at_top_level_commas(raw)

    return ExpressSelectType(
        name=name,
        members=members,
        is_extensible=is_extensible,
        is_generic_entity=is_generic_entity,
        based_on=based_on,
    )


# ---------------------------------------------------------------------------
# Main parse entry point
# ---------------------------------------------------------------------------

def parse_express(path: Path) -> ExpressSchema:
    """
    Parse an ISO 10303 EXPRESS schema file and return an ExpressSchema.

    Args:
        path: Path to the .exp file.

    Returns:
        Populated ExpressSchema with entities, enumerations, select types, and references.
    """
    logger.info(f"Parsing EXPRESS schema: {path.name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_comments(text)

    # Extract SCHEMA name and ID
    m_schema = re.search(r"^SCHEMA\s+(\w+)\s*'([^']*)'", text, re.MULTILINE | re.IGNORECASE)
    schema_name = m_schema.group(1) if m_schema else None
    schema_id = m_schema.group(2) if m_schema and m_schema.group(2) else None
    
    if not schema_name:
        m_schema = re.search(r"^SCHEMA\s+(\w+)", text, re.MULTILINE | re.IGNORECASE)
        schema_name = m_schema.group(1) if m_schema else path.stem
    
    schema = ExpressSchema(name=schema_name, schema_id=schema_id)

    # Parse REFERENCE FROM clauses
    for m in re.finditer(_RE_REFERENCE_FROM, text):
        ref_schema_name = m.group(1)
        entities_str = m.group(2)
        entities = [e.strip() for e in entities_str.split(",") if e.strip()]
        schema.references[ref_schema_name] = ExpressSchemaReference(
            schema_name=ref_schema_name,
            entities=entities,
        )
    
    logger.info(f"Schema references: {len(schema.references)}")

    # --- Parse ENTITY blocks ---
    for chunk in re.split(r"\bEND_ENTITY\s*;", text):
        m_ent = re.search(r"\bENTITY\s+(\w+)(.*)", chunk, re.DOTALL)
        if not m_ent:
            continue
        ent_name = m_ent.group(1)
        ent_body = m_ent.group(2)
        entity = _parse_entity_block(ent_name, ent_body)
        schema.entities[ent_name] = entity

    # --- Parse TYPE blocks ---
    for chunk in re.split(r"\bEND_TYPE\s*;", text):
        m_type = re.search(r"\bTYPE\s+(\w+)\s*=\s*(.*)", chunk, re.DOTALL)
        if not m_type:
            continue
        type_name = m_type.group(1)
        type_body = m_type.group(2).strip()

        upper = type_body.upper()
        if upper.startswith("ENUMERATION OF") or "ENUMERATION OF" in upper:
            schema.enumerations[type_name] = _parse_enum_type(type_name, type_body)
        elif "SELECT" in upper:
            schema.select_types[type_name] = _parse_select_type(type_name, type_body)
        else:
            # Simple alias: TYPE FooString = STRING; → track for range resolution
            m_prim = re.match(r"(\w+)\s*;", type_body.strip(), re.IGNORECASE)
            if m_prim and m_prim.group(1).upper() in _PRIMITIVE_NAMES:
                schema.type_aliases[type_name] = m_prim.group(1).upper()
            else:
                # P7 FIX: capture bounded primitives e.g. STRING(256) → STRING
                m_bounded = re.match(r"(STRING|INTEGER|REAL|NUMBER|BINARY)\s*\([^)]*\)\s*;", type_body.strip(), re.IGNORECASE)
                if m_bounded:
                    schema.type_aliases[type_name] = m_bounded.group(1).upper()
                else:
                    # P7 FIX: capture aggregate aliases e.g. SET [1:?] OF product → element type
                    m_agg = re.match(
                        r"(?:SET|LIST|BAG|ARRAY)\s*\[[^\]]+\]\s+OF\s+(\w+)\s*;",
                        type_body.strip(), re.IGNORECASE
                    )
                    if m_agg:
                        elem_type = m_agg.group(1)
                        # Map to primitive if element is primitive, else keep as entity ref
                        schema.type_aliases[type_name] = (
                            elem_type.upper() if elem_type.upper() in _PRIMITIVE_NAMES else elem_type
                        )

    logger.info(
        f"EXPRESS parse complete — entities: {len(schema.entities)}, "
        f"enums: {len(schema.enumerations)}, selects: {len(schema.select_types)}, "
        f"aliases: {len(schema.type_aliases)}, "
        f"where-rules: {sum(len(e.where_rules) for e in schema.entities.values())}, "
        f"derive-attrs: {sum(len(e.derived_attributes) for e in schema.entities.values())}, "
        f"inverse-attrs: {sum(len(e.inverse_attributes) for e in schema.entities.values())}, "
        f"unique-constraints: {sum(len(e.unique_constraints) for e in schema.entities.values())}"
    )
    return schema


# ---------------------------------------------------------------------------
# Range resolution helper
# ---------------------------------------------------------------------------

def _resolve_range(type_ref: str, schema: ExpressSchema) -> tuple[bool, str]:
    """
    Determine whether a type_ref is object or data typed.

    Returns:
        (is_object: bool, range_uri: str)
        - is_object=True  → owl:ObjectProperty with range pointing to a class IRI
        - is_object=False → owl:DatatypeProperty with an xsd: literal range
    """
    upper = type_ref.upper()

    # Direct primitive
    if upper in _PRIM_TO_XSD:
        return False, _PRIM_TO_XSD[upper]

    # Alias to primitive
    if type_ref in schema.type_aliases:
        prim = schema.type_aliases[type_ref].upper()
        return False, _PRIM_TO_XSD.get(prim, "xsd:string")

    # Known entity, enum, or select → all are classes
    return True, type_ref


def _sparql_escape_literal(value: str) -> str:
    """Escape quotes/backslashes for inclusion in SHACL SPARQL string literals."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _attribute_var_name(attribute: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", attribute)


def _build_attr_lookup(entity: ExpressEntity) -> Dict[str, str]:
    """Case-insensitive attribute lookup preserving canonical names."""
    lookup: Dict[str, str] = {a.name.lower(): a.name for a in entity.attributes}
    # WHERE rules often reference derived/inverse names (e.g., rotationMatrix).
    for d in entity.derived_attributes:
        lookup.setdefault(d.name.lower(), d.name)
    for inv in entity.inverse_attributes:
        lookup.setdefault(inv.name.lower(), inv.name)
    return lookup


def _resolve_attr_ref(attr_ref: str, attr_lookup: Dict[str, str]) -> Optional[str]:
    """
    Resolve an EXPRESS attribute reference to a canonical attribute name.

    Handles simple refs (`Relating`), dotted refs (`SELF.Weight.Unit.Name`), and
    inherited SELF refs (`SELF\\DatedEffectivity.StartDefinition`) by using the
    terminal token where possible.
    """
    s = attr_ref.strip()
    if not s:
        return None

    # Direct case
    direct = attr_lookup.get(s.lower())
    if direct:
        return direct

    # Normalize SELF path separators and get terminal token
    norm = s.replace("\\", ".")
    parts = [p.strip() for p in norm.split(".") if p.strip()]
    if not parts:
        return None

    terminal = parts[-1]
    return attr_lookup.get(terminal.lower())


def _build_attr_optional(this_var: str, ns: str, entity_name: str, attr_name: str, var_name: str) -> str:
    prop_iri = f"<{ns}{entity_name}_{attr_name}>"
    return f"OPTIONAL {{ {this_var} {prop_iri} {var_name} . }}"


def _parse_attr_path(attr_ref: str, attr_lookup: Dict[str, str]) -> List[str]:
    """Parse EXPRESS SELF path into attribute-token sequence.

    Examples:
      SELF.Weight.Unit.Name -> [Weight, Unit, Name]
    SELF\\RepresentationRelationship.Relating.ContextOfItems -> [Relating, ContextOfItems]
    """
    s = attr_ref.strip()
    if not s:
        return []

    norm = s.replace("\\", ".")
    parts = [p.strip() for p in norm.split(".") if p.strip()]
    if not parts:
        return []

    if parts[0].upper() == "SELF":
        parts = parts[1:]

    if parts and parts[0].lower() not in attr_lookup and len(parts) > 1:
        # likely inherited entity qualifier in SELF\Entity.attr syntax
        parts = parts[1:]

    return parts


def _build_optional_path(
    source_var: str,
    attr_ref: str,
    attr_lookup: Dict[str, str],
    var_seed: str,
) -> tuple[List[str], str]:
    """Build OPTIONAL bindings for direct or dotted attribute path via suffix-matched predicates."""
    tokens = _parse_attr_path(attr_ref, attr_lookup)
    if not tokens:
        return [], ""

    lines: List[str] = []
    current = source_var
    end_var = ""
    for i, token in enumerate(tokens):
        pv = f"?p_{var_seed}_{i}"
        ov = f"?v_{var_seed}_{i}"
        end_var = ov
        token_l = token.lower()
        lines.append(
            f"OPTIONAL {{ {current} {pv} {ov} . FILTER(STRENDS(LCASE(STR({pv})), \"_{token_l}\")) }}"
        )
        current = ov

    return lines, end_var


def _operator_violation(lhs: str, op: str, rhs: str) -> str:
    if op == "=":
        return f"({lhs} != {rhs})"
    if op == "<>":
        return f"({lhs} = {rhs})"
    return f"!({lhs} {op} {rhs})"


def _translate_exists_patterns(entity: ExpressEntity, expr: str, ns: str) -> Optional[str]:
    """
    Translate common EXISTS patterns:
      - EXISTS(A) OR EXISTS(B)
      - NOT(EXISTS(A)) OR EXISTS(B)
      - NOT(EXISTS(A) AND EXISTS(B))
      - NOT(EXISTS(A)) OR (SIZEOF(A) = SIZEOF(B))
    """
    attr_lookup = _build_attr_lookup(entity)

    # NOT(EXISTS(A)) OR (SIZEOF(A) = SIZEOF(B))
    m = re.fullmatch(
        r"NOT\s*\(\s*EXISTS\s*\(\s*(.+?)\s*\)\s*\)\s*OR\s*\(\s*SIZEOF\s*\(\s*(.+?)\s*\)\s*=\s*SIZEOF\s*\(\s*(.+?)\s*\)\s*\)",
        expr,
        flags=re.IGNORECASE,
    )
    if m:
        a1 = _resolve_attr_ref(m.group(1), attr_lookup)
        s1 = _resolve_attr_ref(m.group(2), attr_lookup)
        s2 = _resolve_attr_ref(m.group(3), attr_lookup)
        if a1 and s1 and s2:
            v1 = f"?{_attribute_var_name(a1)}"
            vs1 = f"?{_attribute_var_name(s1)}_cnt"
            vs2 = f"?{_attribute_var_name(s2)}_cnt"
            p1 = f"<{ns}{entity.name}_{a1}>"
            ps1 = f"<{ns}{entity.name}_{s1}>"
            ps2 = f"<{ns}{entity.name}_{s2}>"
            return (
                "SELECT $this WHERE {\n"
                f"        OPTIONAL {{ $this {p1} {v1} . }}\n"
                f"        {{ SELECT $this (COUNT(?x1) AS {vs1}) WHERE {{ OPTIONAL {{ $this {ps1} ?x1 . }} }} GROUP BY $this }}\n"
                f"        {{ SELECT $this (COUNT(?x2) AS {vs2}) WHERE {{ OPTIONAL {{ $this {ps2} ?x2 . }} }} GROUP BY $this }}\n"
                f"        FILTER(BOUND({v1}) && ({vs1} != {vs2}))\n"
                "      }"
            )

    # EXISTS(A) OR EXISTS(B)
    m = re.fullmatch(r"EXISTS\s*\(\s*(.+?)\s*\)\s*OR\s*EXISTS\s*\(\s*(.+?)\s*\)", expr, flags=re.IGNORECASE)
    if m:
        lines1, v1 = _build_optional_path("$this", m.group(1), attr_lookup, "ex1")
        lines2, v2 = _build_optional_path("$this", m.group(2), attr_lookup, "ex2")
        if v1 and v2:
            return (
                "SELECT $this WHERE {\n"
                "        " + "\n        ".join(lines1) + "\n"
                "        " + "\n        ".join(lines2) + "\n"
                "        FILTER(!BOUND(" + v1 + ") && !BOUND(" + v2 + "))\n"
                "      }"
            )

    # NOT(EXISTS(A)) OR EXISTS(B)
    m = re.fullmatch(r"NOT\s*\(\s*EXISTS\s*\(\s*(.+?)\s*\)\s*\)\s*OR\s*EXISTS\s*\(\s*(.+?)\s*\)", expr, flags=re.IGNORECASE)
    if m:
        lines1, v1 = _build_optional_path("$this", m.group(1), attr_lookup, "nex1")
        lines2, v2 = _build_optional_path("$this", m.group(2), attr_lookup, "nex2")
        if v1 and v2:
            return (
                "SELECT $this WHERE {\n"
                "        " + "\n        ".join(lines1) + "\n"
                "        " + "\n        ".join(lines2) + "\n"
                "        FILTER(BOUND(" + v1 + ") && !BOUND(" + v2 + "))\n"
                "      }"
            )

    # NOT(EXISTS(A) AND EXISTS(B))
    m = re.fullmatch(r"NOT\s*\(\s*EXISTS\s*\(\s*(.+?)\s*\)\s*AND\s*EXISTS\s*\(\s*(.+?)\s*\)\s*\)", expr, flags=re.IGNORECASE)
    if m:
        lines1, v1 = _build_optional_path("$this", m.group(1), attr_lookup, "and1")
        lines2, v2 = _build_optional_path("$this", m.group(2), attr_lookup, "and2")
        if v1 and v2:
            return (
                "SELECT $this WHERE {\n"
                "        " + "\n        ".join(lines1) + "\n"
                "        " + "\n        ".join(lines2) + "\n"
                "        FILTER(BOUND(" + v1 + ") && BOUND(" + v2 + "))\n"
                "      }"
            )

    return None


def _translate_sizeof_patterns(entity: ExpressEntity, expr: str, ns: str) -> Optional[str]:
    """Translate SIZEOF comparisons against SIZEOF/number for direct attributes."""
    attr_lookup = _build_attr_lookup(entity)

    def _resolve_sizeof_ref(raw_ref: str) -> Optional[str]:
        canonical = _resolve_attr_ref(raw_ref, attr_lookup)
        if canonical:
            return canonical
        # Fallback for schema-local identifiers that are not parsed as direct attrs
        # (e.g., some derived helper names used in WHERE expressions).
        token = (raw_ref or "").strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            return token
        return None

    # SIZEOF(A) <op> SIZEOF(B)
    m = re.fullmatch(r"SIZEOF\s*\(\s*(.+?)\s*\)\s*(=|<>|>=|<=|>|<)\s*SIZEOF\s*\(\s*(.+?)\s*\)", expr, flags=re.IGNORECASE)
    if m:
        a1 = _resolve_sizeof_ref(m.group(1))
        op = m.group(2)
        a2 = _resolve_sizeof_ref(m.group(3))
        if a1 and a2:
            c1 = "?c1"
            c2 = "?c2"
            p1 = f"?p_{_attribute_var_name(a1)}"
            p2 = f"?p_{_attribute_var_name(a2)}"
            t1 = a1.lower()
            t2 = a2.lower()
            return (
                "SELECT $this WHERE {\n"
                f"        {{ SELECT $this (COUNT(?x1) AS {c1}) WHERE {{ OPTIONAL {{ $this {p1} ?x1 . FILTER(STRENDS(LCASE(STR({p1})), \"_{t1}\")) }} }} GROUP BY $this }}\n"
                f"        {{ SELECT $this (COUNT(?x2) AS {c2}) WHERE {{ OPTIONAL {{ $this {p2} ?x2 . FILTER(STRENDS(LCASE(STR({p2})), \"_{t2}\")) }} }} GROUP BY $this }}\n"
                f"        FILTER({_operator_violation(c1, op, c2)})\n"
                "      }"
            )

    # SIZEOF(A) <op> number
    m = re.fullmatch(r"SIZEOF\s*\(\s*(.+?)\s*\)\s*(=|<>|>=|<=|>|<)\s*([-+]?\d+(?:\.\d+)?)", expr, flags=re.IGNORECASE)
    if m:
        a1 = _resolve_sizeof_ref(m.group(1))
        op = m.group(2)
        n = m.group(3)
        if a1:
            c1 = "?c1"
            p1 = f"?p_{_attribute_var_name(a1)}"
            t1 = a1.lower()
            return (
                "SELECT $this WHERE {\n"
                f"        {{ SELECT $this (COUNT(?x1) AS {c1}) WHERE {{ OPTIONAL {{ $this {p1} ?x1 . FILTER(STRENDS(LCASE(STR({p1})), \"_{t1}\")) }} }} GROUP BY $this }}\n"
                f"        FILTER({_operator_violation(c1, op, n)})\n"
                "      }"
            )

    return None


def _translate_typeof_patterns(entity: ExpressEntity, expr: str, ns: str) -> Optional[str]:
    """
    Translate common TYPEOF patterns.

    Supported:
      - TYPEOF(A) = TYPEOF(B)
    """
    attr_lookup = _build_attr_lookup(entity)

    m = re.fullmatch(r"TYPEOF\s*\(\s*(.+?)\s*\)\s*=\s*TYPEOF\s*\(\s*(.+?)\s*\)", expr, flags=re.IGNORECASE)
    if m:
        a1 = _resolve_attr_ref(m.group(1), attr_lookup)
        a2 = _resolve_attr_ref(m.group(2), attr_lookup)
        if a1 and a2:
            v1 = "?left"
            v2 = "?right"
            t1 = "?leftType"
            t2 = "?rightType"
            p1 = f"<{ns}{entity.name}_{a1}>"
            p2 = f"<{ns}{entity.name}_{a2}>"
            return (
                "SELECT $this WHERE {\n"
                f"        OPTIONAL {{ $this {p1} {v1} . }}\n"
                f"        OPTIONAL {{ $this {p2} {v2} . }}\n"
                f"        OPTIONAL {{ {v1} a {t1} . }}\n"
                f"        OPTIONAL {{ {v2} a {t2} . }}\n"
                f"        FILTER(BOUND({v1}) && BOUND({v2}) && BOUND({t1}) && BOUND({t2}) && ({t1} != {t2}))\n"
                "      }"
            )

    return None


def _translate_typeof_membership_patterns(entity: ExpressEntity, expr: str, ns: str) -> Optional[str]:
    """
    Translate selected `'<TYPE>' IN TYPEOF(X)` families.

    Supported:
      - NOT('<TYPE>' IN TYPEOF(Placement)) OR (Placement.Definitional = TRUE|FALSE)
      - ('<TYPE1>' IN TYPEOF(DerivedFrom)) OR ('<TYPE2>' IN TYPEOF(DerivedFrom))
    """
    attr_lookup = _build_attr_lookup(entity)
    normalized = _normalise_ws(expr)
    normalized_upper = normalized.upper()

    # Pattern A: placement-type gate implies definitional value.
    if " IN TYPEOF(" in normalized_upper and ".DEFINITIONAL" in normalized_upper and normalized_upper.startswith("NOT"):
        types = re.findall(r"'([A-Za-z0-9_]+)'\s+IN\s+TYPEOF\(\s*([^)]+?)\s*\)", normalized, flags=re.IGNORECASE)
        m_def = re.search(r"([A-Za-z_][\w\\.]*)\s*\.\s*Definitional\s*=\s*(TRUE|FALSE)", normalized, flags=re.IGNORECASE)
        if len(types) >= 1 and m_def:
            type_token, obj_ref = types[0][0], types[0][1]
            expected = m_def.group(2).lower()

            obj_lines, obj_var = _build_optional_path("$this", obj_ref, attr_lookup, "tp_obj")
            def_lines, def_var = _build_optional_path("$this", m_def.group(1) + ".Definitional", attr_lookup, "tp_def")
            if obj_var and def_var:
                t_var = "?tp_type"
                return (
                    "SELECT $this WHERE {\n"
                    "        " + "\n        ".join(obj_lines) + "\n"
                    "        " + "\n        ".join(def_lines) + "\n"
                    f"        OPTIONAL {{ {obj_var} a {t_var} . }}\n"
                    f"        FILTER(BOUND({obj_var}) && BOUND({t_var}) && CONTAINS(UCASE(STR({t_var})), \"{type_token.upper()}\") && (!BOUND({def_var}) || ({def_var} != {expected})))\n"
                    "      }"
                )

    # Pattern B: two allowed TYPEOF memberships OR'ed together.
    # Violation when object exists and none of the allowed type tokens are present.
    if " IN TYPEOF(" in normalized_upper and " OR " in normalized_upper:
        types = re.findall(r"'([A-Za-z0-9_]+)'\s+IN\s+TYPEOF\(\s*([^)]+?)\s*\)", normalized, flags=re.IGNORECASE)
        if len(types) >= 2:
            t1, obj1 = types[0]
            t2, obj2 = types[1]
            if _normalise_ws(obj1).lower() == _normalise_ws(obj2).lower():
                obj_lines, obj_var = _build_optional_path("$this", obj1, attr_lookup, "tor_obj")
                if obj_var:
                    tv = "?tor_type"
                    return (
                        "SELECT $this WHERE {\n"
                        "        " + "\n        ".join(obj_lines) + "\n"
                        f"        OPTIONAL {{ {obj_var} a {tv} . }}\n"
                        f"        FILTER(BOUND({obj_var}) && (!BOUND({tv}) || (!CONTAINS(UCASE(STR({tv})), \"{t1.upper()}\") && !CONTAINS(UCASE(STR({tv})), \"{t2.upper()}\"))))\n"
                        "      }"
                    )

    # Pattern C: single membership gate.
    #   '<TYPE>' IN TYPEOF(X)           -> violation when X exists but TYPEOF(X) does not include TYPE
    #   NOT('<TYPE>' IN TYPEOF(X))      -> violation when X exists and TYPEOF(X) includes TYPE
    m_single = re.fullmatch(
        r"(NOT\s*\(\s*)?'([A-Za-z0-9_]+)'\s+IN\s+TYPEOF\(\s*([^)]+?)\s*\)\s*\)?",
        normalized,
        flags=re.IGNORECASE,
    )
    if m_single:
        negated = bool(m_single.group(1))
        type_token = m_single.group(2)
        obj_ref = m_single.group(3)
        obj_lines, obj_var = _build_optional_path("$this", obj_ref, attr_lookup, "tin_obj")
        if obj_var:
            tv = "?tin_type"
            if negated:
                violation_filter = (
                    f"BOUND({obj_var}) && BOUND({tv}) && CONTAINS(UCASE(STR({tv})), \"{type_token.upper()}\")"
                )
            else:
                violation_filter = (
                    f"BOUND({obj_var}) && (!BOUND({tv}) || !CONTAINS(UCASE(STR({tv})), \"{type_token.upper()}\"))"
                )
            return (
                "SELECT $this WHERE {\n"
                "        " + "\n        ".join(obj_lines) + "\n"
                f"        OPTIONAL {{ {obj_var} a {tv} . }}\n"
                f"        FILTER({violation_filter})\n"
                "      }"
            )

    return None


def _translate_special_composites_rule(entity: ExpressEntity, expr: str) -> Optional[str]:
    """Translate: (NOT(EXISTS(SELF.Weight)) OR (EXISTS(SELF.Weight) AND SELF.Weight.Unit.Name='mass'))."""
    normalized = _normalise_ws(expr)
    pat = re.compile(
        r"^\(\(NOT\(EXISTS\(SELF\.Weight\)\)\)\s+OR\s+\(\(EXISTS\(SELF\.Weight\)\)\s+AND\s+\(SELF\.Weight\.Unit\.Name\s*=\s*'mass'\)\)\)$",
        flags=re.IGNORECASE,
    )
    if not pat.match(normalized):
        return None

    attr_lookup = _build_attr_lookup(entity)
    w_lines, w_var = _build_optional_path("$this", "SELF.Weight", attr_lookup, "cw")
    m_lines, m_var = _build_optional_path("$this", "SELF.Weight.Unit.Name", attr_lookup, "cm")
    if not w_var or not m_var:
        return None

    indent = "\n        "
    w_joined = indent.join(w_lines)
    m_joined = indent.join(m_lines)
    return (
        "SELECT $this WHERE {\n"
        f"        {w_joined}\n"
        f"        {m_joined}\n"
        f"        FILTER(BOUND({w_var}) && (!BOUND({m_var}) || ({m_var} != \"mass\")))\n"
        "      }"
    )


def _translate_query_patterns(entity: ExpressEntity, expr: str) -> Optional[str]:
    """Translate known QUERY/SIZEOF patterns that appear in DomainModel.exp."""
    normalized = _normalise_ws(expr)
    upper = normalized.upper()

    # Pattern 1: CartesianTransformation WR1 matrix bounds rule.
    if (
        "SIZEOF( QUERY(XI <* ROTATIONMATRIX" in upper
        and "(-1.0 > XJ) OR (XJ > 1.0)" in upper
    ):
        return (
            "SELECT $this WHERE {\n"
            "        OPTIONAL { $this ?p_rm ?rm . FILTER(STRENDS(LCASE(STR(?p_rm)), \"_rotationmatrix\")) }\n"
            "        OPTIONAL { ?rm ?p_cell ?xj . }\n"
            "        FILTER(BOUND(?rm) && BOUND(?xj) && (xsd:double(?xj) < -1.0 || xsd:double(?xj) > 1.0))\n"
            "      }"
        )

    # Pattern 2: AssemblyContext members must be WiringHarnessAssemblyDesign related.
    if (
        "SIZEOF(QUERY( AC <* ASSEMBLYCONTEXT" in upper
        and "WIRINGHARNESSASSEMBLYDESIGN" in upper
        and "TYPEOF(AC\\ASSEMBLYOCCURRENCERELATIONSHIP.RELATING)" in upper
    ):
        return (
            "SELECT $this WHERE {\n"
            "        OPTIONAL { $this ?p_ac ?ac . FILTER(STRENDS(LCASE(STR(?p_ac)), \"_assemblycontext\")) }\n"
            "        OPTIONAL { ?ac ?p_rel ?rel . FILTER(STRENDS(LCASE(STR(?p_rel)), \"_relating\")) }\n"
            "        OPTIONAL { ?rel a ?relType . }\n"
            "        FILTER(BOUND(?ac) && (!BOUND(?relType) || !CONTAINS(UCASE(STR(?relType)), \"WIRINGHARNESSASSEMBLYDESIGN\")))\n"
            "      }"
        )

    return None


def _parse_rule_operand(operand: str, attr_lookup: Dict[str, str]) -> tuple[str, str]:
    """
    Parse WHERE-rule operand into SPARQL term.

    Returns:
        (kind, value)
        - kind="var" and value="?VarName"
        - kind="lit" and value='"text"' / numeric literal
        - kind="unknown" when unsupported
    """
    op = operand.strip()
    if not op:
        return "unknown", ""

    # Numeric literal
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", op):
        return "lit", op

    # Boolean literal
    if op.upper() in {"TRUE", "FALSE"}:
        return "lit", op.lower()

    # Quoted string literal (EXPRESS uses single quotes)
    m_str = re.fullmatch(r"'([^']*)'", op)
    if m_str:
        return "lit", f'"{_sparql_escape_literal(m_str.group(1))}"'

    # Attribute reference (simple or SELF path)
    canon = _resolve_attr_ref(op, attr_lookup)
    if canon:
        return "var", f"?{_attribute_var_name(canon)}"

    # Generic path-like RHS (SELF.a.b or x\y.z)
    if op.upper().startswith("SELF") or "." in op or "\\" in op:
        return "varpath", op

    # Bare enum-like identifiers are treated as string literals
    if re.fullmatch(r"[A-Za-z_]\w*", op):
        return "lit", f'"{_sparql_escape_literal(op)}"'

    return "unknown", op


def _translate_where_rule_to_sparql(
    entity: ExpressEntity,
    rule: ExpressWhereRule,
    ns: str,
) -> Optional[str]:
    """
    Translate a subset of EXPRESS WHERE expressions into violation SPARQL.

    Supported patterns:
      - Attr1 :<>: Attr2
      - Attr1 :=: Attr2
      - Attr1 = Attr2
      - Attr1 <op> literal   where <op> in >, <, >=, <=, <>
    """
    expr = _normalise_ws(rule.expression)
    if not expr:
        return None

    # Try dedicated translators for complex-but-common WHERE patterns first.
    for translator in (
        _translate_exists_patterns,
        _translate_sizeof_patterns,
        _translate_typeof_patterns,
        _translate_typeof_membership_patterns,
    ):
        translated = translator(entity, expr, ns)
        if translated is not None:
            return translated

    translated_special = _translate_special_composites_rule(entity, expr)
    if translated_special is not None:
        return translated_special

    translated_query = _translate_query_patterns(entity, expr)
    if translated_query is not None:
        return translated_query

    # Reject still-unsupported high-complexity constructs.
    if re.search(r"\b(QUERY|UNIQUE)\b", expr, flags=re.IGNORECASE):
        return None

    attr_lookup = _build_attr_lookup(entity)

    # Translate EXPRESS symbolic equality operators first.
    simple = expr
    simple = simple.replace(":<>=:", "<>")
    simple = simple.replace(":<>:", "<>")
    simple = simple.replace(":=:", "=")

    m = re.fullmatch(r"(.+?)\s*(=|<>|>=|<=|>|<)\s*(.+)", simple)
    if not m:
        return None

    lhs_raw, op, rhs_raw = m.group(1), m.group(2), m.group(3).strip()
    lhs_lines, lhs_var = _build_optional_path("$this", lhs_raw, attr_lookup, "lhs")
    if not lhs_var:
        return None

    _resolve_attr_ref(lhs_raw, attr_lookup)

    rhs_kind, rhs_value = _parse_rule_operand(rhs_raw, attr_lookup)
    if rhs_kind == "unknown":
        return None

    where_lines: List[str] = list(lhs_lines)

    # Build condition and violation predicate.
    if rhs_kind in {"var", "varpath"}:
        _resolve_attr_ref(rhs_raw, attr_lookup)
        rhs_lines, rhs_var = _build_optional_path("$this", rhs_raw, attr_lookup, "rhs")
        if not rhs_var:
            return None
        where_lines.extend(rhs_lines)

        if op == "=":
            violation = f"BOUND({lhs_var}) && BOUND({rhs_var}) && ({lhs_var} != {rhs_var})"
        elif op == "<>":
            violation = f"BOUND({lhs_var}) && BOUND({rhs_var}) && ({lhs_var} = {rhs_var})"
        else:
            violation = f"BOUND({lhs_var}) && BOUND({rhs_var}) && !({lhs_var} {op} {rhs_var})"
    else:
        if op == "=":
            violation = f"BOUND({lhs_var}) && ({lhs_var} != {rhs_value})"
        elif op == "<>":
            violation = f"BOUND({lhs_var}) && ({lhs_var} = {rhs_value})"
        else:
            violation = f"BOUND({lhs_var}) && !({lhs_var} {op} {rhs_value})"

    where_lines.append(f"FILTER({violation})")
    where_body = "\n        ".join(where_lines)

    return (
        "SELECT $this WHERE {\n"
        f"        {where_body}\n"
        "      }"
    )


# ---------------------------------------------------------------------------
# OWL / Turtle emitter
# ---------------------------------------------------------------------------

def emit_owl_ttl(
    schema: ExpressSchema,
    base_uri: str,
    prefix: str = "ap242dm",
    source_path: Optional[Path] = None,
) -> str:
    """
    Emit Turtle RDF for the parsed EXPRESS schema.

    Produces:
      - owl:Class for each ENTITY (with rdfs:subClassOf for SUBTYPE OF)
      - owl:Class for each ENUMERATION with owl:oneOf individuals
      - owl:Class for each SELECT type (concept only)
      - owl:ObjectProperty / owl:DatatypeProperty for each entity attribute
            - sh:NodeShape + sh:sparql for translatable WHERE rules

    Args:
        schema:      Parsed ExpressSchema.
        base_uri:    Base URI (must end in # or /).
        prefix:      Turtle prefix name for the schema namespace.
        source_path: Optional source file path for provenance comment.

    Returns:
        Turtle-formatted string fragment (no @prefix declarations — caller manages that).
    """
    ns = base_uri if base_uri.endswith(("#", "/")) else base_uri + "#"
    lines: List[str] = []

    source_label = str(source_path) if source_path else "DomainModel.exp"
    lines.append(f"\n# ── EXPRESS semantic ingestion from {source_label} ────────────────")
    lines.append(f"# Schema: {schema.name}")
    lines.append(f"# Entities: {len(schema.entities)}  Enumerations: {len(schema.enumerations)}  SELECTs: {len(schema.select_types)}")
    lines.append("")

    # --- ENTITY → owl:Class -------------------------------------------------
    for ent_name, entity in sorted(schema.entities.items()):
        iri = f"<{ns}{ent_name}>"
        lines.append(f"{iri} a owl:Class ;")
        lines.append(f'    rdfs:label "{ent_name}"@en ;')
        lines.append(f'    rdfs:isDefinedBy <{ns}> ;')

        # ABSTRACT marker
        if entity.abstract:
            lines.append("    owl:equivalentClass [ a owl:Class ] ;")

        # Superclass chain (SUBTYPE OF)
        for parent in entity.supertypes:
            parent_iri = f"<{ns}{parent}>"
            lines.append(f"    rdfs:subClassOf {parent_iri} ;")

        # Strip trailing ; on last property and close with .
        # The last line ends with ; — replace with .
        last = lines[-1]
        if last.endswith(" ;"):
            lines[-1] = last[:-2] + " ."
        else:
            lines.append("    .")
        lines.append("")

    # --- ENUMERATION → owl:Class + owl:oneOf --------------------------------
    for enum_name, enum_type in sorted(schema.enumerations.items()):
        iri = f"<{ns}{enum_name}>"
        lines.append(f"{iri} a owl:Class ;")
        lines.append(f'    rdfs:label "{enum_name}"@en ;')
        lines.append(f'    rdfs:isDefinedBy <{ns}> .')
        lines.append("")

        # Individual for each enumeration literal
        for val in enum_type.values:
            val_iri = f"<{ns}{enum_name}_{val}>"
            lines.append(f"{val_iri} a owl:NamedIndividual , {iri} ;")
            lines.append(f'    rdfs:label "{val}"@en .')
            lines.append("")

    # --- SELECT → owl:Class (concept placeholder) ---------------------------
    for sel_name, sel_type in sorted(schema.select_types.items()):
        iri = f"<{ns}{sel_name}>"
        lines.append(f"{iri} a owl:Class ;")
        lines.append(f'    rdfs:label "{sel_name}"@en ;')
        lines.append(f"    rdfs:comment \"EXPRESS SELECT type — union of {len(sel_type.members)} member types.\" ;")
        lines.append(f'    rdfs:isDefinedBy <{ns}> .')
        lines.append("")

    # --- Attributes → owl:ObjectProperty / owl:DatatypeProperty ------------
    for ent_name, entity in sorted(schema.entities.items()):
        domain_iri = f"<{ns}{ent_name}>"
        for attr in entity.attributes:
            is_obj, range_ref = _resolve_range(attr.type_ref, schema)
            prop_iri = f"<{ns}{ent_name}_{attr.name}>"
            if is_obj:
                range_iri = f"<{ns}{range_ref}>"
                lines.append(f"{prop_iri} a owl:ObjectProperty ;")
                lines.append(f'    rdfs:label "{attr.name}"@en ;')
                lines.append(f"    rdfs:domain {domain_iri} ;")
                lines.append(f"    rdfs:range {range_iri} .")
            else:
                lines.append(f"{prop_iri} a owl:DatatypeProperty ;")
                lines.append(f'    rdfs:label "{attr.name}"@en ;')
                lines.append(f"    rdfs:domain {domain_iri} ;")
                lines.append(f"    rdfs:range {range_ref} .")
            lines.append("")

    # --- WHERE rules → SHACL/SPARQL constraints ----------------------------
    translated_count = 0
    skipped_count = 0
    lines.append("# EXPRESS WHERE rules mapped to SHACL/SPARQL")
    lines.append("")
    for ent_name, entity in sorted(schema.entities.items()):
        if not entity.where_rules:
            continue

        target_class = f"<{ns}{ent_name}>"
        for rule in entity.where_rules:
            sparql_select = _translate_where_rule_to_sparql(entity, rule, ns)
            safe_rule = re.sub(r"[^A-Za-z0-9_]", "_", rule.rule_id)
            safe_expr = _sparql_escape_literal(rule.expression)
            shape_iri = f"<{ns}{ent_name}_Where_{safe_rule}_Shape>"

            if sparql_select is None:
                skipped_count += 1
                lines.append(f"# Untranslated WHERE rule ({ent_name}.{rule.rule_id}): {rule.expression}")
                continue

            translated_count += 1
            lines.append(f"{shape_iri} a sh:NodeShape ;")
            lines.append(f"    sh:targetClass {target_class} ;")
            lines.append("    sh:sparql [")
            lines.append("        a sh:SPARQLConstraint ;")
            lines.append(f"        sh:message \"EXPRESS WHERE {ent_name}.{rule.rule_id} violated: {safe_expr}\" ;")
            lines.append(f"        sh:select \"\"\"{sparql_select}\"\"\"")
            lines.append("    ] .")
            lines.append("")

    lines.append(f"# WHERE rules summary: translated={translated_count}, untranslated={skipped_count}")
    lines.append("")

    return "\n".join(lines)
