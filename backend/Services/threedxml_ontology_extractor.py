"""
3DXML Ontology Extraction Service

Extracts ontology from 3DXML files (XML-based CAD product structures).
Parses products, parts, components, and assembly relationships.

3DXML Structure:
- VPMRepReference: Main product/assembly container
- VPMRepInstance: Instance of a referenced product/part
- VPMPort: Connection points between components
- VPMCXParameter: Properties and attributes
"""

import os
import xml.etree.ElementTree as ET
import logging
from typing import Dict, List, Set, Tuple, Any
from pathlib import Path
from collections import defaultdict

from Services.splm_ontology_extractor import (
    OntologyExtractor, OntologyFormat, Entity, Attribute, RelationshipDef
)

logger = logging.getLogger(__name__)


class ThreeDXMLExtractor(OntologyExtractor):
    """Extract ontology from 3DXML CAD files"""
    
    def __init__(self, source_path: str):
        super().__init__(source_path, OntologyFormat.THREEDXML)
        self.xml_namespace = {
            'ns': 'http://www.3ds.com/xsd/3DXML'
        }
        self.parts_by_id = {}  # Map of part IDs to part objects
        self.assemblies = defaultdict(list)  # Map of assembly ID to contained parts
    
    def extract(self) -> Dict[str, Any]:
        """Extract all ontology data from 3DXML files"""
        logger.info(f"Starting 3DXML extraction from {self.source_path}")
        
        try:
            # Find all 3DXML files
            xml_files = list(Path(self.source_path).glob("*.3dxml"))
            logger.info(f"Found {len(xml_files)} 3DXML files")
            
            if not xml_files:
                logger.warning(f"No .3dxml files found in {self.source_path}")
                return self.to_dict()
            
            # Parse each 3DXML file
            for xml_file in xml_files:
                try:
                    self._parse_3dxml_file(xml_file)
                except Exception as e:
                    logger.warning(f"Error parsing {xml_file.name}: {e}")
            
            # Build relationships from assembly structure
            self._build_assembly_relationships()
            
            # Build graph connections
            self._build_graph_connections()
            
            logger.info(f"3DXML extraction complete: {len(self.entities)} entities, "
                       f"{len(self.relationships)} relationships")
            return self.to_dict()
            
        except Exception as e:
            logger.error(f"Error extracting 3DXML ontology: {e}", exc_info=True)
            raise
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate 3DXML ontology structure"""
        errors = []
        
        if not self.entities:
            errors.append("No entities extracted from 3DXML files")
        
        if len(self.entities) < 2:
            errors.append("Minimum 2 entities required for valid ontology")
        
        return len(errors) == 0, errors
    
    def _parse_3dxml_file(self, file_path: Path) -> None:
        """Parse a single 3DXML file"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            logger.debug(f"Parsing 3DXML file: {file_path.name}")
            
            # Register XML namespaces
            namespaces = {
                'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                '': 'http://www.3ds.com/xsd/3DXML'
            }
            
            # Extract products (root references)
            products = root.findall('.//{http://www.3ds.com/xsd/3DXML}VPMRepReference')
            logger.debug(f"Found {len(products)} VPMRepReference elements")
            
            for product in products:
                self._parse_product(product, file_path.name)
            
            # Extract parts (instances)
            parts = root.findall('.//{http://www.3ds.com/xsd/3DXML}VPMRepInstance')
            logger.debug(f"Found {len(parts)} VPMRepInstance elements")
            
            for part in parts:
                self._parse_part(part, file_path.name)
            
            # Extract connections
            connections = root.findall('.//{http://www.3ds.com/xsd/3DXML}VPMPort')
            logger.debug(f"Found {len(connections)} VPMPort connection elements")
            
        except ET.ParseError as e:
            logger.error(f"XML parse error in {file_path.name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error parsing 3DXML file {file_path.name}: {e}")
            raise
    
    def _parse_product(self, product_elem, source_file: str) -> None:
        """Parse VPMRepReference (product/assembly definition)"""
        try:
            # Get product attributes
            product_id = product_elem.get('id', '')
            product_name = product_elem.get('name', 'Unknown Product')
            product_ref = product_elem.get('ref', '')
            
            if not product_name or product_name in self.entities:
                return
            
            # Get product description from children
            description = self._extract_element_text(product_elem, 'description', '')
            
            # Create entity for this product
            entity = Entity(
                name=product_name,
                entity_type='Product',  # Product/Assembly type
                namespace='com.dassault.3dxml.product',
                description=description,
                metadata={
                    'source_file': source_file,
                    'xml_id': product_id,
                    'xml_ref': product_ref,
                    'element_type': 'VPMRepReference'
                }
            )
            
            # Extract product properties as attributes
            properties = product_elem.findall('.//{http://www.3ds.com/xsd/3DXML}VPMCXParameter')
            for prop in properties:
                attr_name = prop.get('name', '')
                attr_value = prop.get('value', '')
                if attr_name:
                    entity.add_attribute(Attribute(
                        name=attr_name,
                        data_type='string',
                        description=attr_value
                    ))
                    self.all_attributes.add(attr_name)
            
            self.entities[product_name] = entity
            self.entity_types.add('Product')
            self.parts_by_id[product_id] = product_name
            
            # Track assembly (contains parts)
            instance_refs = product_elem.findall('.//{http://www.3ds.com/xsd/3DXML}VPMRepInstance')
            for inst_ref in instance_refs:
                inst_name = inst_ref.get('name', '')
                if inst_name:
                    self.assemblies[product_name].append(inst_name)
                    
        except Exception as e:
            logger.debug(f"Error parsing product element: {e}")
    
    def _parse_part(self, part_elem, source_file: str) -> None:
        """Parse VPMRepInstance (part/component instance)"""
        try:
            part_id = part_elem.get('id', '')
            part_name = part_elem.get('name', 'Unknown Part')
            part_ref = part_elem.get('ref', '')
            
            if not part_name or part_name in self.entities:
                return
            
            description = self._extract_element_text(part_elem, 'description', '')
            
            # Create entity for this part
            entity = Entity(
                name=part_name,
                entity_type='Part',  # Component/Part type
                namespace='com.dassault.3dxml.part',
                description=description,
                metadata={
                    'source_file': source_file,
                    'xml_id': part_id,
                    'xml_ref': part_ref,
                    'element_type': 'VPMRepInstance'
                }
            )
            
            # Extract part properties
            properties = part_elem.findall('.//{http://www.3ds.com/xsd/3DXML}VPMCXParameter')
            for prop in properties:
                attr_name = prop.get('name', '')
                attr_value = prop.get('value', '')
                if attr_name:
                    entity.add_attribute(Attribute(
                        name=attr_name,
                        data_type='string',
                        description=attr_value
                    ))
                    self.all_attributes.add(attr_name)
            
            self.entities[part_name] = entity
            self.entity_types.add('Part')
            self.parts_by_id[part_id] = part_name
            
        except Exception as e:
            logger.debug(f"Error parsing part element: {e}")
    
    def _extract_element_text(self, element, tag_name: str, default: str = '') -> str:
        """Extract text content from a child element"""
        try:
            child = element.find(f'.//{tag_name}')
            if child is not None and child.text:
                return child.text.strip()
        except Exception:
            pass
        return default
    
    def _build_assembly_relationships(self) -> None:
        """Build relationships from assembly structure (product contains parts)"""
        logger.debug(f"Building assembly relationships from {len(self.assemblies)} assemblies")
        
        for product_name, contained_parts in self.assemblies.items():
            if product_name not in self.entities:
                continue
            
            for part_name in contained_parts:
                if part_name in self.entities:
                    # Create 'contains' relationship
                    rel = RelationshipDef(
                        name=f"{product_name}_contains_{part_name}",
                        source=product_name,
                        target=part_name,
                        relation_type='contains',
                        cardinality='1..N',
                        description=f"{product_name} assembly contains {part_name} component"
                    )
                    self.relationships.append(rel)
    
    def _build_graph_connections(self) -> None:
        """Build explicit and implicit graph connections"""
        logger.info("Building graph connections...")
        
        # Add explicit relationships from assembly structure
        for rel in self.relationships:
            if rel.source in self.entities and rel.target in self.entities:
                source_entity = self.entities[rel.source]
                if rel.target not in source_entity.relationships:
                    source_entity.add_relationship(rel.target, rel.relation_type)
        
        # Build implicit connections from shared attributes
        attr_to_entities = defaultdict(list)
        for entity_name, entity in self.entities.items():
            for attr_name in entity.attributes:
                attr_to_entities[attr_name].append(entity_name)
        
        # Connect entities that share attributes
        for attr_name, entity_list in attr_to_entities.items():
            if len(entity_list) > 1:
                for entity_name in entity_list:
                    if entity_name in self.entities:
                        entity = self.entities[entity_name]
                        for other_entity in entity_list:
                            if other_entity != entity_name and other_entity not in entity.relationships:
                                entity.add_relationship(other_entity, "shares_attribute")
        
        logger.info(f"Built connections: {sum(len(e.relationships) for e in self.entities.values())} total")
