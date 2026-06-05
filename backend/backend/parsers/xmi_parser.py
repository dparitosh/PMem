"""
XMI (XML Metadata Interchange) Parser

Parses UML/MOF models stored in XMI format and extracts:
- Packages and Model Elements
- Classes, Attributes, Operations
- Data Types
- Associations and Generalizations
- Tagged Values and Stereotypes
"""

import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class XmiClass:
    """Represents a UML Class in XMI"""
    id: str
    name: str
    package: str = ""
    attributes: List[Dict[str, Any]] = field(default_factory=list)
    operations: List[Dict[str, Any]] = field(default_factory=list)
    generalizations: List[str] = field(default_factory=list)  # Parent class IDs
    tagged_values: Dict[str, str] = field(default_factory=dict)
    stereotype: Optional[str] = None


@dataclass
class XmiAssociation:
    """Represents a UML Association in XMI"""
    id: str
    name: str
    source_id: str
    target_id: str
    source_role: str = ""
    target_role: str = ""
    source_multiplicity: str = ""
    target_multiplicity: str = ""


@dataclass
class XmiDocument:
    """Parsed XMI Document"""
    model_name: str
    classes: Dict[str, XmiClass] = field(default_factory=dict)
    associations: List[XmiAssociation] = field(default_factory=list)
    data_types: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    packages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)


def _local_name(tag: str) -> str:
    """Get local XML tag name without namespace."""
    if not tag:
        return ""
    return tag.split('}', 1)[-1] if '}' in tag else tag


def _get_xmi_attr(element, attr_name: str) -> str:
    """Read xmi namespaced or plain attribute by local attribute name."""
    if element is None:
        return ""
    for key, value in element.attrib.items():
        k_local = key.split('}', 1)[-1] if '}' in key else key
        if k_local == attr_name:
            return value
    return ""


def _find_elements_by_xmi_type(root, xmi_type: str):
    """Find elements where xmi:type equals the requested UML type."""
    matches = []
    for el in root.iter():
        if _get_xmi_attr(el, 'type') == xmi_type:
            matches.append(el)
    return matches


def parse_xmi_file(file_path: str) -> XmiDocument:
    """
    Parse XMI file and extract model information.
    
    Args:
        file_path: Path to XMI file
        
    Returns:
        XmiDocument with extracted model information
    """
    tree = ET.parse(file_path)
    root = tree.getroot()
    
    doc = XmiDocument(model_name="Unknown Model")
    
    # Extract namespaces
    namespaces = {
        'xmi': 'http://schema.omg.org/spec/XMI/2.1',
        'uml': 'http://www.omg.org/spec/UML/20090701',
        'ecore': 'http://www.eclipse.org/emf/2002/Ecore',
    }
    
    # Try to find UML model
    uml_model = root.find('.//uml:Model', namespaces)
    if uml_model is None:
        uml_model = root.find('.//{*}Model')
    if uml_model is None:
        uml_models = _find_elements_by_xmi_type(root, 'uml:Model')
        uml_model = uml_models[0] if uml_models else None
    
    if uml_model is not None:
        doc.model_name = uml_model.get('name', 'Unknown Model')
        doc.metadata['model_name'] = doc.model_name
    
    # Extract packages
    for package in root.findall('.//uml:Package', namespaces):
        pkg_id = package.get('{http://schema.omg.org/spec/XMI/2.1}id', package.get('id', ''))
        pkg_name = package.get('name', 'Unknown Package')
        doc.packages[pkg_id] = {
            'name': pkg_name,
            'id': pkg_id,
        }
    
    # Extract classes
    for cls in root.findall('.//uml:Class', namespaces):
        if cls is None:
            continue
            
        cls_id = cls.get('{http://schema.omg.org/spec/XMI/2.1}id', cls.get('id', ''))
        cls_name = cls.get('name', 'Unknown Class')
        
        xmi_cls = XmiClass(id=cls_id, name=cls_name)
        
        # Extract stereotypes
        stereotype_elem = cls.find('.//uml:Stereotype', namespaces)
        if stereotype_elem is None:
            stereotype_elem = cls.find('.//Stereotype')
        if stereotype_elem is not None:
            xmi_cls.stereotype = stereotype_elem.get('name')
        
        # Extract attributes
        for attr in cls.findall('.//uml:Attribute', namespaces):
            if attr is None:
                continue
            attr_name = attr.get('name', 'unnamed')
            attr_type = attr.get('type', '')
            
            # Try to find type via type reference
            type_ref = attr.find('.//uml:TypedElement', namespaces)
            if type_ref is None:
                type_ref = attr.find('.//TypedElement')
            if type_ref is not None:
                attr_type = type_ref.get('type', attr_type)
            
            # Extract multiplicity
            multiplicity_elem = attr.find('.//uml:MultiplicityElement', namespaces)
            if multiplicity_elem is None:
                multiplicity_elem = attr.find('.//MultiplicityElement')
            
            lower = '0'
            upper = '1'
            if multiplicity_elem is not None:
                lower = multiplicity_elem.get('lower', '0')
                upper = multiplicity_elem.get('upper', '1')
            
            xmi_cls.attributes.append({
                'name': attr_name,
                'type': attr_type,
                'multiplicity': f"[{lower}..{upper}]",
                'visibility': attr.get('visibility', 'public'),
                'is_derived': attr.get('isDerived', 'false'),
                'is_static': attr.get('isStatic', 'false'),
            })
        
        # Extract operations
        for op in cls.findall('.//uml:Operation', namespaces):
            if op is None:
                continue
            op_name = op.get('name', 'unnamed')
            return_type = op.get('type', 'void')
            
            # Extract parameters
            parameters = []
            for param in op.findall('.//uml:Parameter', namespaces):
                if param is None:
                    continue
                param_name = param.get('name', '')
                param_type = param.get('type', '')
                param_direction = param.get('direction', 'in')
                parameters.append({
                    'name': param_name,
                    'type': param_type,
                    'direction': param_direction,
                })
            
            xmi_cls.operations.append({
                'name': op_name,
                'return_type': return_type,
                'parameters': parameters,
                'visibility': op.get('visibility', 'public'),
                'is_abstract': op.get('isAbstract', 'false'),
                'is_static': op.get('isStatic', 'false'),
            })
        
        # Extract generalizations (inheritance)
        for gen in cls.findall('.//uml:Generalization', namespaces):
            if gen is None:
                continue
            general_id = gen.get('general', '')
            if general_id:
                xmi_cls.generalizations.append(general_id)
        
        # Extract tagged values
        for tag in cls.findall('.//uml:TaggedValue', namespaces):
            if tag is None:
                continue
            tag_name = tag.get('name', '')
            tag_value = tag.get('value', '')
            if tag_name:
                xmi_cls.tagged_values[tag_name] = tag_value
        
        doc.classes[cls_id] = xmi_cls
    
    # Extract data types
    for dt in root.findall('.//uml:DataType', namespaces):
        if dt is None:
            continue
        dt_id = dt.get('{http://schema.omg.org/spec/XMI/2.1}id', dt.get('id', ''))
        dt_name = dt.get('name', 'Unknown Type')
        
        doc.data_types[dt_id] = {
            'name': dt_name,
            'id': dt_id,
            'base_type': dt.get('base_type', ''),
        }
    
    # Extract associations
    for assoc in root.findall('.//uml:Association', namespaces):
        if assoc is None:
            continue
        
        assoc_id = assoc.get('{http://schema.omg.org/spec/XMI/2.1}id', assoc.get('id', ''))
        assoc_name = assoc.get('name', '')
        
        # Extract member ends
        member_ends = assoc.findall('.//uml:MemberEnd', namespaces)
        if not member_ends:
            member_ends = assoc.findall('.//MemberEnd')
        
        if len(member_ends) >= 2:
            source_end = member_ends[0]
            target_end = member_ends[1]
            
            source_id = source_end.get('type', '')
            target_id = target_end.get('type', '')
            source_role = source_end.get('name', '')
            target_role = target_end.get('name', '')
            
            # Extract multiplicities
            source_mult = _extract_multiplicity(source_end)
            target_mult = _extract_multiplicity(target_end)
            
            xmi_assoc = XmiAssociation(
                id=assoc_id,
                name=assoc_name,
                source_id=source_id,
                target_id=target_id,
                source_role=source_role,
                target_role=target_role,
                source_multiplicity=source_mult,
                target_multiplicity=target_mult,
            )
            doc.associations.append(xmi_assoc)
    
    # Fallback extraction for newer XMI exports (e.g., MagicDraw/Cameo 2021x)
    # where UML elements are represented as packagedElement xmi:type='uml:Class'
    if not doc.classes:
        for cls in _find_elements_by_xmi_type(root, 'uml:Class'):
            cls_id = _get_xmi_attr(cls, 'id') or cls.get('id', '')
            cls_name = cls.get('name', 'Unknown Class')
            if not cls_id or cls_id in doc.classes:
                continue

            xmi_cls = XmiClass(id=cls_id, name=cls_name)

            # ownedAttribute in packagedElement-style XMI
            for child in list(cls):
                if _local_name(child.tag) != 'ownedAttribute':
                    continue

                attr_name = child.get('name', 'unnamed')
                attr_type = child.get('type', '')
                lower = child.get('lower', '0')
                upper = child.get('upper', '1')

                xmi_cls.attributes.append({
                    'name': attr_name,
                    'type': attr_type,
                    'multiplicity': f"[{lower}..{upper}]",
                    'visibility': child.get('visibility', 'public'),
                    'is_derived': child.get('isDerived', 'false'),
                    'is_static': child.get('isStatic', 'false'),
                })

            # ownedOperation in packagedElement-style XMI
            for child in list(cls):
                if _local_name(child.tag) != 'ownedOperation':
                    continue

                xmi_cls.operations.append({
                    'name': child.get('name', 'unnamed'),
                    'return_type': child.get('type', 'void'),
                    'parameters': [],
                    'visibility': child.get('visibility', 'public'),
                    'is_abstract': child.get('isAbstract', 'false'),
                    'is_static': child.get('isStatic', 'false'),
                })

            # generalization in packagedElement-style XMI
            for child in list(cls):
                if _local_name(child.tag) == 'generalization':
                    parent_id = child.get('general', '')
                    if parent_id:
                        xmi_cls.generalizations.append(parent_id)

            doc.classes[cls_id] = xmi_cls

    if not doc.data_types:
        for dt in _find_elements_by_xmi_type(root, 'uml:DataType'):
            dt_id = _get_xmi_attr(dt, 'id') or dt.get('id', '')
            dt_name = dt.get('name', 'Unknown Type')
            if not dt_id or dt_id in doc.data_types:
                continue
            doc.data_types[dt_id] = {
                'name': dt_name,
                'id': dt_id,
                'base_type': dt.get('base_type', ''),
            }

    if not doc.associations:
        # Build id map for referenced member ends
        id_to_element = {}
        for el in root.iter():
            el_id = _get_xmi_attr(el, 'id') or el.get('id', '')
            if el_id:
                id_to_element[el_id] = el

        for assoc in _find_elements_by_xmi_type(root, 'uml:Association'):
            assoc_id = _get_xmi_attr(assoc, 'id') or assoc.get('id', '')
            assoc_name = assoc.get('name', '')
            if not assoc_id:
                continue

            ends = [c for c in list(assoc) if _local_name(c.tag) in ('ownedEnd', 'memberEnd')]

            # Some exports keep member ends as id refs in "memberEnd" attribute
            if len(ends) < 2:
                member_end_refs = assoc.get('memberEnd', '').split()
                for ref in member_end_refs:
                    if ref in id_to_element:
                        ends.append(id_to_element[ref])

            if len(ends) < 2:
                continue

            source_end = ends[0]
            target_end = ends[1]
            source_id = source_end.get('type', '')
            target_id = target_end.get('type', '')

            if not source_id or not target_id:
                continue

            xmi_assoc = XmiAssociation(
                id=assoc_id,
                name=assoc_name,
                source_id=source_id,
                target_id=target_id,
                source_role=source_end.get('name', ''),
                target_role=target_end.get('name', ''),
                source_multiplicity=_extract_multiplicity(source_end),
                target_multiplicity=_extract_multiplicity(target_end),
            )
            doc.associations.append(xmi_assoc)

    return doc


def _extract_multiplicity(element) -> str:
    """Extract multiplicity from UML element"""
    lower = element.get('lower', '0')
    upper = element.get('upper', '1')
    return f"[{lower}..{upper}]"


def parse_xmi_to_ontology(file_path: str) -> Dict[str, Any]:
    """
    Parse XMI file and convert to ontology entity/relationship format.
    
    Returns:
        Dictionary with 'entities' and 'relationships' keys
    """
    doc = parse_xmi_file(file_path)
    
    entities = []
    relationships = []
    
    # Convert classes to entities
    for cls_id, xmi_cls in doc.classes.items():
        entity = {
            'type': 'Class',
            'id': f"XMI_{xmi_cls.name}",
            'xmi_id': cls_id,
            'name': xmi_cls.name,
            'attributes': {
                'attributes': xmi_cls.attributes,
                'operations': xmi_cls.operations,
                'stereotype': xmi_cls.stereotype,
                'tagged_values': xmi_cls.tagged_values,
                'attribute_count': len(xmi_cls.attributes),
                'operation_count': len(xmi_cls.operations),
            }
        }
        entities.append(entity)
    
    # Convert data types to entities
    for dt_id, dt_info in doc.data_types.items():
        entity = {
            'type': 'DataType',
            'id': f"XMI_{dt_info['name']}",
            'xmi_id': dt_id,
            'name': dt_info['name'],
            'attributes': dt_info,
        }
        entities.append(entity)
    
    # Create class ID mapping for relationships
    class_map = {cls_id: f"XMI_{xmi_cls.name}" for cls_id, xmi_cls in doc.classes.items()}
    dt_map = {dt_id: f"XMI_{dt_info['name']}" for dt_id, dt_info in doc.data_types.items()}
    all_elements = {**class_map, **dt_map}
    
    # Convert generalizations to inheritance relationships
    for cls_id, xmi_cls in doc.classes.items():
        for parent_id in xmi_cls.generalizations:
            if parent_id in all_elements:
                relationships.append({
                    'source': class_map[cls_id],
                    'target': all_elements[parent_id],
                    'type': 'INHERITS_FROM',
                })
    
    # Convert associations to relationships
    for assoc in doc.associations:
        source_id = assoc.source_id
        target_id = assoc.target_id
        
        if source_id in all_elements and target_id in all_elements:
            rel_type = assoc.name if assoc.name else 'ASSOCIATED_WITH'
            relationships.append({
                'source': all_elements[source_id],
                'target': all_elements[target_id],
                'type': rel_type,
                'source_role': assoc.source_role,
                'target_role': assoc.target_role,
                'source_multiplicity': assoc.source_multiplicity,
                'target_multiplicity': assoc.target_multiplicity,
            })
    
    # Convert attribute types to relationships
    for cls_id, xmi_cls in doc.classes.items():
        for attr in xmi_cls.attributes:
            if attr['type'] and attr['type'] in all_elements:
                relationships.append({
                    'source': class_map[cls_id],
                    'target': all_elements[attr['type']],
                    'type': 'HAS_ATTRIBUTE_TYPE',
                    'attribute_name': attr['name'],
                })
    
    return {
        'entities': entities,
        'relationships': relationships,
        'format': 'xmi',
        'model_name': doc.model_name,
        'total_classes': len(doc.classes),
        'total_datatypes': len(doc.data_types),
        'total_associations': len(doc.associations),
        'total_attributes': sum(len(c.attributes) for c in doc.classes.values()),
        'total_operations': sum(len(c.operations) for c in doc.classes.values()),
    }
