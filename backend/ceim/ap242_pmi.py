"""Conservative Part-21 PMI association rules using declared attribute positions."""
import re

TOLERANCES = frozenset({
    'GEOMETRIC_TOLERANCE', 'ANGULARITY_TOLERANCE', 'CIRCULAR_RUNOUT_TOLERANCE',
    'COAXIALITY_TOLERANCE', 'CONCENTRICITY_TOLERANCE', 'CYLINDRICITY_TOLERANCE',
    'FLATNESS_TOLERANCE', 'LINE_PROFILE_TOLERANCE', 'PARALLELISM_TOLERANCE',
    'PERPENDICULARITY_TOLERANCE', 'POSITION_TOLERANCE', 'ROUNDNESS_TOLERANCE',
    'STRAIGHTNESS_TOLERANCE', 'SURFACE_PROFILE_TOLERANCE', 'SYMMETRY_TOLERANCE',
    'TOTAL_RUNOUT_TOLERANCE',
})
SHAPE_ASPECTS = frozenset({'SHAPE_ASPECT', 'COMPOSITE_SHAPE_ASPECT', 'COMPOSITE_GROUP_SHAPE_ASPECT'})


def arguments(text):
    """Split STEP attributes without splitting aggregates or quoted commas."""
    parts, start, depth, quoted, index = [], 0, 0, False, 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if quoted and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif not quoted:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth < 0:
                    return []
            elif char == ',' and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 1
        index += 1
    return [] if quoted or depth else parts + [text[start:].strip()]


def reference(value):
    return int(value[1:]) if re.fullmatch(r'#[0-9]+', value) else None


def owner_paths(row, entity_map, emitted):
    """Return complete unambiguous characteristic-to-product-definition paths."""
    if row.compound_entity_types:
        return []
    attrs = arguments(row.raw_args)
    if row.entity_type in {'DIMENSIONAL_SIZE', 'ANGULAR_SIZE', 'DIMENSIONAL_SIZE_WITH_PATH'}:
        positions = [0] if len(attrs) >= 2 else []
    elif row.entity_type in {'DIMENSIONAL_LOCATION', 'ANGULAR_LOCATION', 'DIMENSIONAL_LOCATION_WITH_PATH'}:
        positions = [2, 3] if len(attrs) >= 4 else []
    elif row.entity_type in TOLERANCES:
        positions = [3] if len(attrs) == 4 else []
    else:
        return []
    paths = []
    for position in positions:
        feature = entity_map.get(reference(attrs[position]))
        if not feature or feature.compound_entity_types or feature.entity_type not in SHAPE_ASPECTS:
            return []
        feature_attrs = arguments(feature.raw_args)
        if len(feature_attrs) != 4:
            return []
        shape = entity_map.get(reference(feature_attrs[2]))
        if not shape or shape.compound_entity_types or shape.entity_type != 'PRODUCT_DEFINITION_SHAPE':
            return []
        shape_attrs = arguments(shape.raw_args)
        if len(shape_attrs) != 3:
            return []
        product = entity_map.get(reference(shape_attrs[2]))
        if not product or product.compound_entity_types or product.entity_type != 'PRODUCT_DEFINITION' or str(product.step_id) not in emitted:
            return []
        paths.append((product.step_id, feature.step_id, shape.step_id))
    return sorted(set(paths)) if len({path[0] for path in paths}) == 1 else []
