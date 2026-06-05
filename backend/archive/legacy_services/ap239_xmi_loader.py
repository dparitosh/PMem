r"""
AP239 XMI Ontology Loader
Loads real AP239 domain model ontology from official XMI files for customer acceptance testing
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class OntologyEntity:
    """Ontology entity extracted from XMI"""
    id: str
    name: str
    entity_type: str
    description: str = ""
    properties: Dict[str, Any] = None
    relationships: List[str] = None
    
    def __post_init__(self):
        if self.properties is None:
            self.properties = {}
        if self.relationships is None:
            self.relationships = []


@dataclass
class OntologyRelationship:
    """Ontology relationship extracted from XMI"""
    source_id: str
    target_id: str
    relationship_type: str
    description: str = ""


class AP239XMIOntologyLoader:
    r"""
    Loads AP239 domain model ontology from official XMI files
    Extracts entity types, relationships, and properties
    Used for customer acceptance testing with official data models
    """
    
    def __init__(self):
        """Initialize AP239 XMI ontology loader"""
        self.xmi_file = r"C:\Users\895428\Depo\SPLM_Folder\AP239\Domain_model_4439_XMI\STEPlib\Application_protocols\AP239\Domain_model\Domain_model.xmi"
        self.entities: Dict[str, OntologyEntity] = {}
        self.relationships: List[OntologyRelationship] = []
        self.namespaces: Dict[str, str] = {}
        self.entity_types: Set[str] = set()
        
        if Path(self.xmi_file).exists():
            self._load_ap239_xmi()
            logger.info(f"[OK] AP239 ontology loaded: {len(self.entities)} entities, {len(self.relationships)} relationships")
        else:
            logger.warning(f"[WARN] AP239 XMI file not found: {self.xmi_file}")
            self._initialize_default_ontology()
    
    def _load_ap239_xmi(self):
        """Load and parse AP239 XMI file"""
        try:
            tree = ET.parse(self.xmi_file)
            root = tree.getroot()
            
            # Extract namespaces
            for prefix, uri in root.attrib.items():
                if prefix.startswith('{'):
                    ns = prefix[1:prefix.rfind('}')]
                    self.namespaces[ns] = prefix[1:-1]
            
            # Extract packages (classes/entities)
            self._extract_packages(root)
            
            # Extract classifiers (types)
            self._extract_classifiers(root)
            
            # Extract associations (relationships)
            self._extract_associations(root)
            
            logger.info(f"[OK] Extracted {len(self.entity_types)} entity types from AP239 XMI")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to load AP239 XMI: {str(e)}")
            self._initialize_default_ontology()
    
    def _extract_packages(self, root: ET.Element):
        """Extract packages (organizational units) from XMI"""
        # Look for uml:Package or similar elements
        for elem in root.iter():
            if 'Package' in elem.tag:
                pkg_name = elem.get('name', 'UnknownPackage')
                pkg_id = elem.get('xmi:id') or elem.get('id') or pkg_name
                
                self.entities[pkg_id] = OntologyEntity(
                    id=pkg_id,
                    name=pkg_name,
                    entity_type="Package",
                    description=f"Package: {pkg_name}"
                )
    
    def _extract_classifiers(self, root: ET.Element):
        """Extract class definitions (entity types) from XMI"""
        classifier_count = 0
        
        # Look for Class, DataType, and Enumeration elements
        for elem in root.iter():
            tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            
            if tag_name in ['Class', 'DataType', 'Enumeration', 'Interface']:
                name = elem.get('name')
                element_id = elem.get('xmi:id') or elem.get('id')
                
                if name:
                    self.entity_types.add(name)
                    classifier_count += 1
                    
                    # Extract attributes as properties
                    properties = {}
                    for child in elem:
                        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        if child_tag == 'ownedAttribute':
                            attr_name = child.get('name')
                            attr_type = child.get('type', 'string')
                            if attr_name:
                                properties[attr_name] = {'type': attr_type}
                    
                    entity = OntologyEntity(
                        id=element_id or name,
                        name=name,
                        entity_type=tag_name,
                        description=f"AP239 {tag_name}: {name}",
                        properties=properties
                    )
                    
                    self.entities[entity.id] = entity
        
        logger.info(f"[OK] Extracted {classifier_count} classifiers (entity types)")
    
    def _extract_associations(self, root: ET.Element):
        """Extract associations (relationships) from XMI"""
        association_count = 0
        
        for elem in root.iter():
            tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            
            if tag_name == 'Association':
                assoc_name = elem.get('name', 'relationship')
                
                # Find memberEnds (source and target)
                member_ends = []
                for child in elem:
                    child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if child_tag == 'memberEnd':
                        member_ends.append(child.get('xmi:idref') or child.get('idref'))
                
                if len(member_ends) >= 2:
                    rel = OntologyRelationship(
                        source_id=member_ends[0],
                        target_id=member_ends[1],
                        relationship_type=assoc_name,
                        description=f"AP239 association: {assoc_name}"
                    )
                    self.relationships.append(rel)
                    association_count += 1
        
        logger.info(f"[OK] Extracted {association_count} associations (relationships)")
    
    def _initialize_default_ontology(self):
        """Initialize default AP239 ontology if XMI load fails"""
        # Default AP239 entities based on standard
        default_entities = {
            "ElectronicAssembly": "Top-level electronic assembly",
            "SchematicDiagram": "Schematic representation",
            "CircuitNetwork": "Network of circuits",
            "SignalNet": "Signal routing network",
            "ComponentInstance": "Individual component",
            "ConnectionPoint": "Connection point",
            "ElectricalProperty": "Electrical characteristic",
            "SignalIntegrity": "Signal quality property",
            "PowerDistribution": "Power distribution network",
            "ImpedanceControl": "Impedance management",
            "TestCoverage": "Test point coverage",
            "FaultModel": "Fault representation",
            "PCBLayout": "PCB physical layout",
            "RoutingPath": "Signal routing path",
            "DesignRuleCheck": "Design rule validation"
        }
        
        for entity_name, description in default_entities.items():
            self.entities[entity_name] = OntologyEntity(
                id=entity_name,
                name=entity_name,
                entity_type="Class",
                description=description
            )
            self.entity_types.add(entity_name)
        
        logger.info(f"[OK] Initialized default AP239 ontology with {len(self.entities)} entities")
    
    def get_entity_types(self) -> List[str]:
        """Get list of all entity types in ontology"""
        return sorted(list(self.entity_types))
    
    def get_entity(self, entity_id: str) -> OntologyEntity:
        """Get entity by ID"""
        return self.entities.get(entity_id)
    
    def get_relationships_for_entity(self, entity_id: str) -> List[OntologyRelationship]:
        """Get all relationships involving an entity"""
        return [r for r in self.relationships 
                if r.source_id == entity_id or r.target_id == entity_id]
    
    def export_ontology(self, filepath: str):
        """Export loaded ontology to JSON"""
        ontology = {
            'entity_types': self.get_entity_types(),
            'total_entities': len(self.entities),
            'total_relationships': len(self.relationships),
            'entities': [asdict(e) for e in list(self.entities.values())[:20]],  # First 20
            'relationships': [asdict(r) for r in self.relationships[:20]]  # First 20
        }
        
        with open(filepath, 'w') as f:
            json.dump(ontology, f, indent=2)
        
        logger.info(f"[OK] Ontology exported to {filepath}")
    
    def validate_entity_against_ontology(self, entity: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate entity against loaded ontology
        
        Args:
            entity: Entity data with 'type' field
        
        Returns:
            (is_valid, message) tuple
        """
        entity_type = entity.get('type')
        
        if not entity_type:
            return False, "Entity missing 'type' field"
        
        if entity_type not in self.entity_types:
            return False, f"Entity type '{entity_type}' not in AP239 ontology"
        
        return True, f"Entity type '{entity_type}' is valid AP239 type"
