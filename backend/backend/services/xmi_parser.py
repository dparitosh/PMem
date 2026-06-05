"""XMI file parser for ISO 10303 SMRL - Independent Implementation"""

from pathlib import Path
from typing import Any, Dict, List

import logging

logger = logging.getLogger(__name__)


class XMIParser:
    """Parser for XMI files following ISO 10303 SMRL specification"""

    # SysML-stereotyped dependency relationship types
    _SYSML_DEP_STEREOTYPES = {
        "satisfy": "SATISFY",
        "verify": "VERIFY",
        "trace": "TRACE",
        "refine": "REFINE",
        "derivereqt": "DERIVE_REQT",
        "copy": "COPY",
    }

    # SysML node types beyond UML core (SysML 1.x and common profiling)
    _SYSML_NODE_TYPE_FILTERS = [
        "Requirement",
        "UseCase",
        "Actor",
        "Activity",
        "Signal",
        "ConstraintBlock",
        "ValueType",
        "FlowPort",
        "ItemFlow",
        "Block",
        "Interaction",
        "State",
        "Transition",
        "CallBehaviorAction",
        "ObjectNode",
        "Region",
        "Enumeration",
        "DataType",
        "PrimitiveType",
    ]

    def __init__(self):
        """Initialize XMI parser"""
        self.namespaces = {
            "xmi": "http://www.omg.org/XMI",
            "uml": "http://www.omg.org/spec/UML/20131001",
            # SysML 1.6 namespace used by MagicDraw / Cameo 2021x exports
            "sysml": "http://www.omg.org/spec/SysML/20181001/SysML",
            # Older SysML 1.4 namespace kept for backward compatibility
            "sysml14": "http://www.omg.org/spec/SysML/20150301/SysML",
        }
        self._known_xmi_namespaces = {
            "http://www.omg.org/XMI",
            "http://www.omg.org/spec/XMI/20110701",
            "http://www.omg.org/spec/XMI/20131001",
            "http://www.omg.org/spec/XMI/20161101",
        }

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse an XMI file

        Args:
            file_path: Path to the XMI file

        Returns:
            Parsed data structure with nodes and relationships
        """
        logger.info(f"Parsing XMI file: {file_path}")

        try:
            from lxml import etree
            
            tree = etree.parse(str(file_path))
            root = tree.getroot()

            # Extract nodes and relationships
            nodes = self._extract_nodes(root)
            relationships = self._extract_relationships(root)
            provenance = self._extract_provenance(root)

            logger.info(
                f"Extracted {len(nodes)} nodes and {len(relationships)} relationships"
            )

            return {
                "source_file": str(file_path),
                "nodes": nodes,
                "relationships": relationships,
                "provenance": provenance,
            }

        except Exception as e:
            logger.error(f"Failed to parse XMI file {file_path}: {e}")
            raise

    def _extract_nodes(self, root) -> List[Dict[str, Any]]:
        """
        Extract nodes from XMI root element.

        Captures the full SysML 1.6 type vocabulary used by MagicDraw/Cameo exports,
        including requirements, use cases, activities, constraint blocks, value types,
        flow ports, signals, and actors that were previously silently dropped.
        
        Handles both:
        1. Elements with explicit xmi:type attribute
        2. PackagedElements that infer type from child elements or name patterns
        """
        nodes = []
        seen_ids: set = set()

        # Combined UML + SysML node type tokens to match against xmi:type
        _uml_core_types = [
            "Class", "Package", "Property", "Association", "Port",
            "Attribute", "InstanceSpecification", "Component", "DataType", "Interface", "Model",
        ]
        _all_accepted = _uml_core_types + self._SYSML_NODE_TYPE_FILTERS

        # Pass 1: Direct extraction of packagedElement nodes regardless of xmi:type
        # This is the primary source for MagicDraw/Cameo XMI exports
        for element in root.iter():
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag != 'packagedElement':
                continue
            
            # Get xmi:id and xmi:type
            xmi_id = self._attr(element, "id") or element.get("id")
            xmi_type = self._xmi_type(element) or self._infer_type_from_element(element)
            
            if not xmi_id:
                continue
            
            # Only keep elements that match our semantic vocabulary
            if not any(t in xmi_type for t in _all_accepted):
                continue
            
            if xmi_id not in seen_ids:
                node = self._element_to_node(element)
                if node:
                    seen_ids.add(xmi_id)
                    nodes.append(node)

        # Pass 2: elements with an explicit xmi:type attribute (non-packagedElement)
        for element in root.xpath(".//*[@*[local-name()='type']]"):
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag == 'packagedElement':
                continue  # Already handled in Pass 1
            
            xmi_type = self._attr(element, "type")
            if xmi_type and any(t in xmi_type for t in _all_accepted):
                xmi_id = self._attr(element, "id")
                if xmi_id and xmi_id not in seen_ids:
                    node = self._element_to_node(element)
                    if node:
                        seen_ids.add(xmi_id)
                        nodes.append(node)

        # Pass 3: elements by local tag name (elements without xmi:type)
        tag_names = " or ".join(
            f"local-name()='{t}'" for t in ["Class", "Package", "Component", "Model", "Attribute", "Property", "Port"] + self._SYSML_NODE_TYPE_FILTERS
        )
        try:
            for element in root.xpath(f".//*[{tag_names}]"):
                xmi_id = self._attr(element, "id")
                if xmi_id and xmi_id not in seen_ids:
                    node = self._element_to_node(element)
                    if node:
                        seen_ids.add(xmi_id)
                        nodes.append(node)
        except Exception:
            pass

        # Pass 4: extract ownedComment bodies and attach to annotated elements
        self._attach_owned_comments(root, nodes, seen_ids)

        # Pass 5: extract SysML stereotype application elements for tagged values
        self._extract_sysml_stereotype_applications(root, nodes, seen_ids)

        return nodes

    def _infer_type_from_element(self, element) -> str:
        """
        Infer element type from child elements and attributes when xmi:type is missing.
        
        For packagedElements without xmi:type, check:
        1. Child element types and their parents
        2. Owning element type (parent context)
        3. Element attributes (stereotype applications, etc.)
        4. Name patterns
        """
        # Check if parent is ownedParameter, ownedAttribute, etc.
        parent = element.getparent()
        if parent is not None:
            parent_tag = parent.tag.split('}')[-1] if '}' in parent.tag else parent.tag
            
            # If it's owned by a parameter parent, it's a parameter
            if 'ownedParameter' in parent_tag:
                return 'uml:Parameter'
            elif 'ownedAttribute' in parent_tag or 'ownedProperty' in parent_tag:
                return 'uml:Property'
            elif 'ownedPort' in parent_tag:
                return 'uml:Port'
            elif 'ownedConnector' in parent_tag:
                return 'uml:Connector'
            elif 'ownedEnumeration' in parent_tag:
                return 'uml:Enumeration'
        
        # Check for specific child elements that indicate type
        child_tags = set()
        for child in element:
            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            child_tags.add(child_tag)
        
        # Strong indicators
        if 'ownedAttribute' in child_tags:
            return 'uml:Class'
        if 'ownedOperation' in child_tags:
            return 'uml:Class'
        if 'ownedPort' in child_tags:
            return 'uml:Class'
        if 'ownedParameter' in child_tags:
            return 'uml:Operation'
        
        # Check for SysML-specific patterns
        for key, value in element.attrib.items():
            local_name = key.split('}')[-1] if '}' in key else key
            value_lower = (value or '').lower()
            
            # Check stereotype or applied profiles
            if 'stereotype' in local_name.lower() or 'applied' in local_name.lower():
                if 'requirement' in value_lower:
                    return 'uml:Class'  # Will be relabeled to Requirement
                elif 'block' in value_lower:
                    return 'uml:Class'  # Will be relabeled to Block/Component
                elif 'valuetype' in value_lower or 'value' in value_lower:
                    return 'uml:DataType'
                elif 'enumeration' in value_lower:
                    return 'uml:Enumeration'
        
        # Default to Class for packagedElements (most common)
        return 'uml:Class'



    def _attach_owned_comments(
        self,
        root,
        nodes: List[Dict[str, Any]],
        seen_ids: set,
    ) -> None:
        """Extract ownedComment body text and attach it to the annotated element node."""
        id_to_node: Dict[str, Dict[str, Any]] = {
            n["properties"]["id"]: n for n in nodes if n["properties"].get("id")
        }
        for comment in root.xpath(".//*[local-name()='ownedComment']"):
            body = comment.get("body", "").strip()
            if not body:
                # body may be a child text node in some exports
                body_elem = comment.find("{http://www.omg.org/spec/UML/20131001}body")
                if body_elem is None:
                    body_elem = next(
                        (c for c in comment if c.tag.split("}")[-1] == "body"), None
                    )
                if body_elem is not None:
                    body = (body_elem.text or "").strip()
            if not body:
                continue
            # Find which elements are annotated by this comment
            for ann_elem in comment.xpath("./*[local-name()='annotatedElement']"):
                target_id = self._normalize_ref(
                    self._attr(ann_elem, "idref") or ann_elem.get("href", "")
                )
                if target_id and target_id in id_to_node:
                    props = id_to_node[target_id]["properties"]
                    if not props.get("documentation"):
                        props["documentation"] = body
            # Also handle annotatedElement as an attribute on the comment itself
            ann_attr = self._normalize_ref(
                comment.get("annotatedElement", "") or self._attr(comment, "annotatedElement")
            )
            if ann_attr and ann_attr in id_to_node:
                props = id_to_node[ann_attr]["properties"]
                if not props.get("documentation"):
                    props["documentation"] = body

    def _extract_sysml_stereotype_applications(
        self,
        root,
        nodes: List[Dict[str, Any]],
        seen_ids: set,
    ) -> None:
        """
        Extract SysML stereotype application elements (e.g. sysml:Block, sysml:Requirement)
        and their tagged values, merging them into existing nodes or creating new stub nodes.
        """
        id_to_node: Dict[str, Dict[str, Any]] = {
            n["properties"]["id"]: n for n in nodes if n["properties"].get("id")
        }
        sysml_ns_uris = [
            "http://www.omg.org/spec/SysML/20181001/SysML",
            "http://www.omg.org/spec/SysML/20150301/SysML",
        ]
        for element in root.iter():
            ns = ""
            tag_local = element.tag
            if "}" in element.tag:
                ns, tag_local = element.tag[1:].split("}", 1)
            if ns not in sysml_ns_uris:
                continue
            # The base_element attribute links this application to its host element
            base_id = self._normalize_ref(
                element.get("base_Element", "")
                or element.get("base_Class", "")
                or element.get("base_Block", "")
                or element.get("base_NamedElement", "")
                or element.get("base_Requirement", "")
                or element.get("base_Abstraction", "")
                or element.get("base_Port", "")
            )
            if not base_id:
                continue
            # Collect tagged values from the stereotype application attributes
            tagged_values: Dict[str, str] = {}
            for key, value in element.attrib.items():
                local_name = key.split("}", 1)[-1] if "}" in key else key
                if local_name.startswith("base_") or not value:
                    continue
                tagged_values[f"sysml_{local_name}"] = value
            if not tagged_values:
                continue
            if base_id in id_to_node:
                id_to_node[base_id]["properties"].update(tagged_values)
                # Record the applied stereotype name if not already set
                if not id_to_node[base_id]["properties"].get("appliedStereotype"):
                    id_to_node[base_id]["properties"]["appliedStereotype"] = tag_local
            else:
                # Create a lightweight stub node so the stereotype context is not lost
                stub_id = self._attr(element, "id") or f"sysml_{tag_local}_{base_id}"
                if stub_id not in seen_ids:
                    seen_ids.add(stub_id)
                    stub_props = {"id": stub_id, "type": f"sysml:{tag_local}", "name": tag_local, "base_element": base_id}
                    stub_props.update(tagged_values)
                    nodes.append({"label": tag_local, "properties": stub_props})

    def _element_to_node(self, element) -> Dict[str, Any]:
        """
        Convert XML element to node dictionary

        Args:
            element: XML element

        Returns:
            Node dictionary
        """
        # Get element attributes
        xmi_id = self._attr(element, "id") or element.get("id")
        xmi_type = self._xmi_type(element) or element.tag.split("}")[-1]
        name = element.get("name", "")

        # Generate ID if missing
        if not xmi_id:
            # Use a combination of type and name as fallback
            xmi_id = f"{xmi_type}_{name}" if name else f"{xmi_type}_{id(element)}"

        # Determine node label based on type
        label = self._determine_label(xmi_type)

        # Extract properties
        properties = {"id": xmi_id, "type": xmi_type, "name": name}

        owner = element.getparent()
        owner_id = self._attr(owner, "id") if owner is not None else ""
        if owner_id:
            properties["ownerId"] = owner_id

        # Preserve UML typed-element target references when present.
        typed_target = element.get("type")
        if typed_target:
            properties["targetType"] = self._normalize_ref(typed_target)

        # Add additional attributes, including namespaced values.
        for key, value in element.attrib.items():
            if not value:
                continue

            local_name = key.split("}", 1)[-1] if "}" in key else key
            if local_name in ["id", "name"]:
                continue

            # Skip xmi:type because properties["type"] already captures it.
            if "}" in key and local_name == "type" and "omg.org" in key and "XMI" in key.upper():
                continue

            prop_key = local_name
            if prop_key in properties:
                prop_key = f"attr_{prop_key}"
            properties[prop_key] = value

        return {"label": label, "properties": properties}

    def _determine_label(self, xmi_type: str) -> str:
        """
        Determine semantic label from XMI / SysML type string.

        Covers the full SysML 1.6 vocabulary as used by MagicDraw/Cameo 2021x exports
        and common UML profiling patterns.
        """
        if not xmi_type:
            return "Element"
            
        type_lower = xmi_type.lower()

        if "system" in type_lower:
            return "System"
        if "constraintblock" in type_lower or "constraint" in type_lower:
            return "ConstraintBlock"
        if "requirement" in type_lower:
            return "Requirement"
        if "usecase" in type_lower or "use_case" in type_lower:
            return "UseCase"
        if "actor" in type_lower:
            return "Actor"
        if "activity" in type_lower or "callbehavior" in type_lower:
            return "Activity"
        if "signal" in type_lower:
            return "Signal"
        if "valuetype" in type_lower or "value_type" in type_lower:
            return "ValueType"
        if "flowport" in type_lower or "flow_port" in type_lower:
            return "FlowPort"
        if "itemflow" in type_lower or "item_flow" in type_lower:
            return "ItemFlow"
        if "block" in type_lower:
            return "Component"  # SysML Block -> Component
        if "component" in type_lower:
            return "Component"
        if "interface" in type_lower:
            return "Interface"
        if "port" in type_lower:
            return "Interface"  # Ports are interface-like
        if "parameter" in type_lower:
            return "Parameter"
        if "property" in type_lower and "attribute" not in type_lower:
            return "Parameter"  # Non-attribute properties are parameters
        if "state" in type_lower:
            return "State"
        if "region" in type_lower:
            return "Region"
        if "transition" in type_lower:
            return "Transition"
        if "interaction" in type_lower:
            return "Interaction"
        if "enumeration" in type_lower:
            return "Enumeration"
        if "datatype" in type_lower or "primitivetype" in type_lower:
            return "ValueType"
        if "package" in type_lower or "model" in type_lower:
            return "Package"
        if "class" in type_lower:
            return "Class"
        if "operation" in type_lower:
            return "Operation"
        if "attribute" in type_lower:
            return "Parameter"  # Attributes/properties are parameter-like
        if "connector" in type_lower or "association" in type_lower:
            return "Association"
        if "abstraction" in type_lower:
            return "Abstraction"
        return "Element"

    def _extract_relationships(self, root) -> List[Dict[str, Any]]:
        """
        Extract relationships from XMI root element

        Args:
            root: XMI root element

        Returns:
            List of relationship dictionaries
        """
        relationships = []
        seen = set()

        # Find elements with references to other elements
        for element in root.xpath(
            ".//*[@*[local-name()='idref'] or @*[contains(local-name(), 'ref')]]"
        ):
            rels = self._element_to_relationships(element)
            for rel in rels:
                key = (
                    rel.get("from_props", {}).get("id", ""),
                    rel.get("type", ""),
                    rel.get("to_props", {}).get("id", ""),
                )
                if key[0] and key[2] and key not in seen:
                    seen.add(key)
                    relationships.append(rel)

        # UML/SysML-specific semantic extraction.
        for rel in self._extract_semantic_relationships(root):
            key = (
                rel.get("from_props", {}).get("id", ""),
                rel.get("type", ""),
                rel.get("to_props", {}).get("id", ""),
            )
            if key[0] and key[2] and key not in seen:
                seen.add(key)
                relationships.append(rel)

        return relationships

    def _extract_semantic_relationships(self, root) -> List[Dict[str, Any]]:
        """Extract richer UML/SysML semantics from common XMI patterns."""
        rels: List[Dict[str, Any]] = []

        # Generalization: class -> superclass
        for cls in root.xpath(".//*[@*[local-name()='type' and contains(., 'Class')]]"):
            source_id = self._attr(cls, "id")
            if not source_id:
                continue
            for gen in cls.xpath("./*[local-name()='generalization']"):
                target_id = self._normalize_ref(self._attr(gen, "general"))
                if target_id:
                    rels.append(self._make_relationship(source_id, "GENERALIZATION", target_id))

        # Property-based structural relation: owner class -> property type
        for prop in root.xpath(".//*[@*[local-name()='type' and contains(., 'Property')]]"):
            owner = prop.getparent()
            source_id = self._attr(owner, "id") if owner is not None else None
            target_id = self._normalize_ref(prop.get("type"))
            if not source_id or not target_id:
                continue

            aggregation = str(self._attr(prop, "aggregation") or "").lower()
            if "composite" in aggregation:
                rel_type = "COMPOSITION"
            elif "shared" in aggregation:
                rel_type = "AGGREGATION"
            else:
                rel_type = "ASSOCIATION"
            rels.append(self._make_relationship(source_id, rel_type, target_id))

        # Dependency: client -> supplier
        for dep in root.xpath(".//*[@*[local-name()='type' and contains(., 'Dependency')]]"):
            clients = self._split_refs(self._attr(dep, "client"))
            suppliers = self._split_refs(self._attr(dep, "supplier"))
            for c in clients:
                for s in suppliers:
                    rels.append(self._make_relationship(c, "DEPENDENCY", s))

        # Allocation-like abstraction mapping in many SysML tools.
        for abs_elem in root.xpath(".//*[@*[local-name()='type' and contains(., 'Abstraction')]]"):
            clients = self._split_refs(self._attr(abs_elem, "client"))
            suppliers = self._split_refs(self._attr(abs_elem, "supplier"))
            for c in clients:
                for s in suppliers:
                    rels.append(self._make_relationship(c, "ALLOCATION", s))

        # Interface realization: classifier -> interface contract
        for ir in root.xpath(".//*[@*[local-name()='type' and contains(., 'InterfaceRealization')]]"):
            source_id = self._normalize_ref(self._attr(ir, "implementingClassifier") or ir.get("client"))
            target_id = self._normalize_ref(self._attr(ir, "contract") or ir.get("supplier"))
            if source_id and target_id:
                rels.append(self._make_relationship(source_id, "INTERFACE_REALIZATION", target_id))

        # Lightweight XML/XMI fallback: local Attribute/Property/Port elements belong
        # to their owner class, or to the nearest preceding class sibling in flat
        # fixtures and simplified exports.
        for attr in root.xpath(".//*[local-name()='Attribute' or local-name()='Property' or local-name()='Port' or local-name()='ownedAttribute']"):
            target_id = self._attr(attr, "id")
            if not target_id:
                continue

            owner = attr.getparent()
            source_id = self._attr(owner, "id") if owner is not None else ""
            if not source_id and owner is not None:
                for sibling in attr.itersiblings(preceding=True):
                    local_name = sibling.tag.split("}")[-1] if "}" in sibling.tag else sibling.tag
                    sibling_type = self._xmi_type(sibling)
                    if local_name == "Class" or "Class" in sibling_type:
                        source_id = self._attr(sibling, "id")
                        if source_id:
                            break

            if source_id and source_id != target_id:
                rels.append(self._make_relationship(source_id, "HAS_PARAMETER", target_id))

        # Stereotype application patterns: element -> stereotype
        for elem in root.xpath(".//*[@*[contains(local-name(), 'stereotype') or contains(local-name(), 'appliedStereotype')]]"):
            source_id = self._attr(elem, "id")
            if not source_id:
                continue
            for key, value in elem.attrib.items():
                local_name = key.split("}", 1)[-1] if "}" in key else key
                if "stereotype" not in local_name.lower():
                    continue
                for target_id in self._split_refs(value):
                    rels.append(self._make_relationship(source_id, "STEREOTYPE", target_id))

        # SysML stereotyped dependency relationships: satisfy, verify, trace, refine, deriveReqt, copy.
        rels.extend(self._extract_sysml_dep_stereotypes(root))

        return rels

    def _extract_sysml_dep_stereotypes(
        self, root
    ) -> List[Dict[str, Any]]:
        """Extract SysML dependency-stereotype relationships."""
        rels: List[Dict[str, Any]] = []
        sysml_ns_uris = [
            "http://www.omg.org/spec/SysML/20181001/SysML",
            "http://www.omg.org/spec/SysML/20150301/SysML",
        ]
        # Build a lookup of dependency/abstraction ids → (client_ids, supplier_ids)
        dep_map: Dict[str, tuple] = {}
        for dep in root.xpath(
            ".//*[@*[local-name()='type' and (contains(., 'Dependency') or contains(., 'Abstraction'))]]"
        ):
            dep_id = self._attr(dep, "id")
            if not dep_id:
                continue
            clients = self._split_refs(self._attr(dep, "client"))
            suppliers = self._split_refs(self._attr(dep, "supplier"))
            if clients and suppliers:
                dep_map[dep_id] = (clients, suppliers)

        for element in root.iter():
            ns = ""
            tag_local = element.tag
            if "}" in element.tag:
                ns, tag_local = element.tag[1:].split("}", 1)
            if ns not in sysml_ns_uris:
                continue
            rel_key = tag_local.lower()
            rel_type = self._SYSML_DEP_STEREOTYPES.get(rel_key)
            if not rel_type:
                continue
            base_dep_id = self._normalize_ref(
                element.get("base_Abstraction", "")
                or element.get("base_Dependency", "")
                or element.get("base_Realization", "")
            )
            if not base_dep_id:
                continue
            if base_dep_id in dep_map:
                clients, suppliers = dep_map[base_dep_id]
                for c in clients:
                    for s in suppliers:
                        rels.append(self._make_relationship(c, rel_type, s))
        return rels

    def _xmi_type(self, element) -> str:
        """Resolve xmi:type while avoiding collision with plain UML `type` references."""
        for key in (
            "{http://www.omg.org/spec/XMI/20131001}type",
            "{http://www.omg.org/XMI}type",
            "xmi:type",
        ):
            value = element.get(key)
            if value:
                return value

        for key, value in element.attrib.items():
            if not value or "}" not in key:
                continue
            uri, local_name = key[1:].split("}", 1)
            if local_name == "type" and uri in self._known_xmi_namespaces:
                return value
        return ""

    def _element_to_relationships(self, element) -> List[Dict[str, Any]]:
        """
        Convert XML element to relationship dictionaries

        Args:
            element: XML element

        Returns:
            List of relationship dictionaries
        """
        relationships = []
        source_id = self._attr(element, "id")

        if not source_id:
            return relationships

        # Check for idref or other reference attributes
        for key, value in element.attrib.items():
            if "idref" in key.lower() or "ref" in key.lower():
                rel_type = self._determine_relationship_type(key)
                for target_id in self._split_refs(value):
                    relationships.append(self._make_relationship(source_id, rel_type, target_id))

        return relationships

    def _determine_relationship_type(self, attr_name: str) -> str:
        """
        Determine relationship type from attribute name

        Args:
            attr_name: Attribute name

        Returns:
            Relationship type
        """
        attr_lower = attr_name.lower()

        if "general" in attr_lower or "super" in attr_lower or "extends" in attr_lower:
            return "GENERALIZATION"
        elif "composition" in attr_lower or "composite" in attr_lower or "owned" in attr_lower:
            return "COMPOSITION"
        elif "aggregation" in attr_lower or "aggregate" in attr_lower:
            return "AGGREGATION"
        elif "association" in attr_lower or "memberend" in attr_lower:
            return "ASSOCIATION"
        elif "dependency" in attr_lower or "depends" in attr_lower:
            return "DEPENDENCY"
        elif "allocate" in attr_lower or "allocation" in attr_lower:
            return "ALLOCATION"

        if "component" in attr_lower or "part" in attr_lower:
            return "HAS_COMPONENT"
        elif "requirement" in attr_lower:
            return "SATISFIES"
        elif "interface" in attr_lower or "port" in attr_lower:
            return "CONNECTS_TO"
        elif "parameter" in attr_lower or "property" in attr_lower:
            return "HAS_PARAMETER"
        else:
            return "RELATES_TO"

    def _make_relationship(self, source_id: str, rel_type: str, target_id: str) -> Dict[str, Any]:
        return {
            "from_label": "Element",
            "from_props": {"id": source_id},
            "type": rel_type,
            "to_label": "Element",
            "to_props": {"id": target_id},
            "properties": {},
        }

    def _attr(self, element, attr_name: str) -> str:
        """Get attribute value from plain or namespaced xmi forms."""
        if element is None:
            return ""
        for key, value in element.attrib.items():
            local_name = key.split("}", 1)[-1] if "}" in key else key
            if local_name == attr_name and value:
                return value
        for key in (
            attr_name,
            f"{{http://www.omg.org/spec/XMI/20131001}}{attr_name}",
            f"{{http://www.omg.org/XMI}}{attr_name}",
            f"xmi:{attr_name}",
        ):
            value = element.get(key)
            if value:
                return value
        return ""

    def _normalize_ref(self, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if "#" in raw:
            raw = raw.split("#")[-1]
        return raw.strip()

    def _split_refs(self, value: str) -> List[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        refs: List[str] = []
        for token in raw.replace(",", " ").split():
            norm = self._normalize_ref(token)
            if norm:
                refs.append(norm)
        return refs

    def _extract_provenance(self, root) -> Dict[str, Any]:
        """Capture source namespace provenance from the input XMI document."""
        nsmap = root.nsmap or {}
        normalized_nsmap: Dict[str, str] = {}
        for prefix, uri in nsmap.items():
            if not uri:
                continue
            key = prefix if prefix else "default"
            normalized_nsmap[key] = uri

        xmi_namespace = ""
        if "xmi" in normalized_nsmap:
            xmi_namespace = normalized_nsmap["xmi"]
        else:
            for uri in normalized_nsmap.values():
                if "omg.org" in uri and "XMI" in uri.upper():
                    xmi_namespace = uri
                    break

        xmi_namespace_known = xmi_namespace in self._known_xmi_namespaces if xmi_namespace else False

        return {
            "xmi_namespace": xmi_namespace,
            "xmi_namespace_known": xmi_namespace_known,
            "namespaces": normalized_nsmap,
        }
