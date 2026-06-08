"""
Generic 3DEXPERIENCE Ontology Extraction Service

Supports multiple ontology source formats:
- 3DXML (XML-based product structures)
- SPLM Schema (Excel-based schema definitions)
- OWL/RDF (RDF-based ontologies)
- Custom formats via adapter pattern

Builds connected graph representations with proper entity relationships.
"""

import os
import json
import logging
import csv
from typing import Dict, List, Set, Tuple, Any, Optional, Protocol
from pathlib import Path
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from abc import ABC, abstractmethod
from enum import Enum

logger = logging.getLogger(__name__)


class OntologyFormat(Enum):
    """Supported ontology source formats"""
    SPLM_SCHEMA = "splm_schema"  # Excel-based
    THREEDXML = "3dxml"  # XML-based CAD
    OWL_RDF = "owl_rdf"  # RDF-based
    CUSTOM = "custom"


@dataclass
class Attribute:
    """Represents an entity attribute/property"""
    name: str
    data_type: str = "string"
    required: bool = False
    description: str = ""
    cardinality: str = "1..1"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Entity:
    """Represents a business/domain entity (BO, class, type)"""
    name: str
    entity_type: str  # e.g., "BusinessObject", "Class", "Part"
    namespace: str = ""  # e.g., "com.dassault.plm.product"
    description: str = ""
    parent: str = ""
    attributes: Dict[str, Attribute] = field(default_factory=dict)
    relationships: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_attribute(self, attr: Attribute) -> None:
        self.attributes[attr.name] = attr
    
    def add_relationship(self, target: str, relation_type: str = "connects") -> None:
        """Add a relationship to another entity"""
        if target not in self.relationships:
            self.relationships.append(target)
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "entity_type": self.entity_type,
            "namespace": self.namespace,
            "description": self.description,
            "parent": self.parent,
            "attributes": {k: v.to_dict() for k, v in self.attributes.items()},
            "relationships": self.relationships,
            "metadata": self.metadata
        }


@dataclass
class RelationshipDef:
    """Represents a relationship between entities"""
    name: str
    source: str
    target: str
    relation_type: str = "connects"  # e.g., "contains", "references", "inherits"
    cardinality: str = "1..N"
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)


class OntologyExtractor(ABC):
    """Abstract base class for ontology extraction from various sources"""
    
    def __init__(self, source_path: str, format_type: OntologyFormat):
        self.source_path = source_path
        self.format_type = format_type
        self.entities: Dict[str, Entity] = {}
        self.relationships: List[RelationshipDef] = []
        self.all_attributes: Set[str] = set()
        self.entity_types: Set[str] = set()
        
    @abstractmethod
    def extract(self) -> Dict[str, Any]:
        """Extract ontology from source"""
        pass
    
    @abstractmethod
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate extracted ontology"""
        pass
    
    def _build_graph_connections(self) -> None:
        """Build explicit and implicit graph connections between entities"""
        logger.info("Building graph connections...")
        
        # Add explicit relationships
        for rel in self.relationships:
            if rel.source in self.entities:
                entity = self.entities[rel.source]
                if rel.target not in entity.relationships:
                    entity.add_relationship(rel.target, rel.relation_type)
        
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ontology to dictionary format"""
        return {
            "metadata": {
                "source_format": self.format_type.value,
                "source_path": self.source_path,
                "stats": {
                    "entities": len(self.entities),
                    "relationships": len(self.relationships),
                    "unique_attributes": len(self.all_attributes),
                    "entity_types": len(self.entity_types)
                }
            },
            "entities": {name: entity.to_dict() for name, entity in self.entities.items()},
            "relationships": [rel.to_dict() for rel in self.relationships],
            "attributes": sorted(list(self.all_attributes)),
            "entity_types": sorted(list(self.entity_types))
        }
    
    def save_json(self, output_path: str) -> None:
        """Save extracted ontology to JSON"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved ontology to {output_path}")


class SPLMSchemaExtractor(OntologyExtractor):
    """Extract ontology from SPLM Excel-based schema"""
    
    def __init__(self, source_path: str):
        super().__init__(source_path, OntologyFormat.SPLM_SCHEMA)
        self.config = {
            "business_folder": "Business",
            "objects_folder": "Objects",
            "relationships_folder": "Relationships",
            "system_folder": "System"
        }
    
    def extract(self) -> Dict[str, Any]:
        """Extract all ontology data from SPLM schema"""
        logger.info(f"Starting SPLM extraction from {self.source_path}")
        
        try:
            # PRIMARY: Extract Objects folder (contains actual Business Object types)
            self._extract_business_types()
            
            # SECONDARY: Extract attributes from Business folder (spinners/enums)
            self._extract_spinners_and_attributes()
            
            # TERTIARY: Extract relationships (if any data exists)
            self._extract_relationships()
            
            self._build_graph_connections()
            
            logger.info(f"SPLM extraction complete: {len(self.entities)} entities, "
                       f"{len(self.relationships)} relationships")
            return self.to_dict()
        except Exception as e:
            logger.error(f"Error extracting SPLM ontology: {e}", exc_info=True)
            raise
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate SPLM ontology structure"""
        errors = []
        
        if not self.entities:
            errors.append("No entities found in ontology")
        
        # Check for orphaned entities
        all_referenced = set()
        for rel in self.relationships:
            all_referenced.add(rel.source)
            all_referenced.add(rel.target)
        
        orphaned = set(self.entities.keys()) - all_referenced
        if orphaned and len(orphaned) < len(self.entities) * 0.3:  # More than 30% orphaned is problematic
            errors.append(f"Found {len(orphaned)} orphaned entities")
        
        return len(errors) == 0, errors
    
    def _extract_business_types(self) -> None:
        """Extract Business Object TYPES from Objects folder (primary entities)"""
        objects_path = os.path.join(self.source_path, self.config["objects_folder"])
        
        if not os.path.isdir(objects_path):
            logger.warning(f"Objects folder not found: {objects_path}")
            return
        
        logger.info(f"Scanning Objects folder...")
        excel_files = list(Path(objects_path).glob("*.xls*"))  # Non-recursive
        logger.info(f"Found {len(excel_files)} Business Object Type files")
        
        for excel_file in excel_files:
            try:
                self._parse_business_types_excel(excel_file)
            except Exception as e:
                logger.debug(f"Error parsing {excel_file.name}: {e}")

    def _parse_business_types_excel(self, file_path: Path) -> None:
        """Parse Objects folder TSV file with Type definitions"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f, delimiter='\t')
                rows = list(reader)
                
                if not rows:
                    return
                
                headers = [h.strip().lower() for h in rows[0]]
                
                # Find column indices for Objects folder structure
                type_col = next((i for i, h in enumerate(headers) if h == 'type'), 0)
                name_col = next((i for i, h in enumerate(headers) if h == 'name' and i != type_col), 1)
                rev_col = next((i for i, h in enumerate(headers) if 'rev' in h), -1)
                
                # Parse data rows
                for row_idx in range(1, len(rows)):
                    row = rows[row_idx]
                    if not row or not row[name_col].strip():
                        continue
                    
                    # Objects folder: Type is the entity category, Name is the specific type
                    entity_type = row[type_col].strip() if type_col >= 0 and type_col < len(row) else "Unknown"
                    entity_name = row[name_col].strip() if name_col >= 0 and name_col < len(row) else ""
                    entity_rev = row[rev_col].strip() if rev_col >= 0 and rev_col < len(row) else ""
                    
                    if entity_name and entity_name not in self.entities:
                        entity = Entity(
                            name=entity_name,
                            entity_type=entity_type,
                            description=f"{entity_type} type definition",
                            metadata={"source_file": file_path.name, "revision": entity_rev}
                        )
                        self.entities[entity_name] = entity
                        self.entity_types.add(entity_type)
                        
        except Exception as e:
            logger.debug(f"Could not parse {file_path.name}: {e}")
    

    def _extract_spinners_and_attributes(self) -> None:
        """Extract spinners and enumerations from Business folder"""
        business_path = os.path.join(self.source_path, self.config["business_folder"])
        
        if not os.path.isdir(business_path):
            logger.debug(f"Business folder not found for spinner extraction")
            return
        
        logger.info("Extracting spinners and enumerations...")
        
        excel_files = list(Path(business_path).glob("*.xls*"))  # Non-recursive
        
        for file_path in excel_files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    reader = csv.reader(f, delimiter='\t')
                    rows = list(reader)
                    if rows:
                        self._extract_spinner_values(rows, file_path.name)
            except Exception as e:
                logger.debug(f"Error parsing spinner file: {e}")

    def _extract_spinner_values(self, rows: List[List[str]], source_file: str) -> None:
        """Extract spinner/enum value definitions from rows"""
        if not rows:
            return
        
        headers = [h.strip().lower() for h in rows[0]]
        
        # Business folder structure: Name, Registry Name, Description, Definition, Hidden
        name_col = next((i for i, h in enumerate(headers) if h == 'name' and 'registry' not in h), 0)
        registry_col = next((i for i, h in enumerate(headers) if 'registry' in h), 1)
        desc_col = next((i for i, h in enumerate(headers) if 'desc' in h), -1)
        
        # Extract spinner values as attributes
        for row in rows[1:]:
            if row and row[name_col].strip():
                spinner_name = row[name_col].strip()
                registry_name = row[registry_col].strip() if registry_col >= 0 and registry_col < len(row) else ""
                spinner_desc = row[desc_col].strip() if desc_col >= 0 and desc_col < len(row) else ""
                
                self.all_attributes.add(spinner_name)
                self.all_attributes.add(registry_name)
    
    def _extract_relationships(self) -> None:
        """Extract relationship definitions"""
        logger.info("Extracting relationships...")
        
        rel_path = os.path.join(self.source_path, self.config["relationships_folder"])
        rel_files = list(Path(rel_path).glob("*.xls*")) if os.path.isdir(rel_path) else []  # Non-recursive
        
        logger.debug(f"Found {len(rel_files)} relationship files")
        
        for file_path in rel_files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    reader = csv.reader(f, delimiter='\t')
                    rows = list(reader)
                    if rows and len(rows) > 1:  # Must have headers and data
                        self._parse_relationships_sheet(rows)
                    elif len(rows) <= 1:
                        logger.debug(f"Relationship file {file_path.name} is empty (only headers or blank)")
            except Exception as e:
                logger.debug(f"Error parsing relationships: {e}")
    
    def _parse_relationships_sheet(self, rows: List[List[str]]) -> None:
        """Parse relationships from rows"""
        if not rows or len(rows) < 2:  # Need header + at least 1 data row
            return
        
        headers = [h.strip().lower() for h in rows[0]]
        
        # Relationships folder structure: Rel Name, from.type, from.name, from.revision, to.type, to.name...
        rel_name_col = next((i for i, h in enumerate(headers) if 'rel' in h and 'name' in h), 0)
        from_type_col = next((i for i, h in enumerate(headers) if 'from' in h and 'type' in h), 1)
        from_name_col = next((i for i, h in enumerate(headers) if 'from' in h and 'name' in h), 2)
        to_type_col = next((i for i, h in enumerate(headers) if 'to' in h and 'type' in h), 3)
        to_name_col = next((i for i, h in enumerate(headers) if 'to' in h and 'name' in h), 4)
        
        for row in rows[1:]:
            if not row or len(row) < 2:
                continue
            
            rel_name = row[rel_name_col].strip() if rel_name_col < len(row) else ""
            from_type = row[from_type_col].strip() if from_type_col < len(row) else ""
            from_name = row[from_name_col].strip() if from_name_col < len(row) else ""
            to_type = row[to_type_col].strip() if to_type_col < len(row) else ""
            to_name = row[to_name_col].strip() if to_name_col < len(row) else ""
            
            if from_name and to_name:
                rel = RelationshipDef(
                    name=rel_name,
                    source=from_name,
                    target=to_name,
                    relation_type=f"{from_type}_to_{to_type}" if from_type and to_type else "relates_to"
                )
                self.relationships.append(rel)
    
    def _extract_system_definitions(self) -> None:
        """System definitions are reference data, skipped during extraction"""
        pass


class OntologyExtractorFactory:
    """Factory for creating appropriate extractor based on source format"""
    
    @staticmethod
    def create(source_path: str, format_type: OntologyFormat = None) -> OntologyExtractor:
        """
        Create appropriate extractor for source
        
        Args:
            source_path: Path to ontology source
            format_type: Format of the source (auto-detect if None)
        
        Returns:
            OntologyExtractor instance
        """
        if format_type is None:
            format_type = OntologyExtractorFactory._detect_format(source_path)
        
        if format_type == OntologyFormat.SPLM_SCHEMA:
            return SPLMSchemaExtractor(source_path)
        elif format_type == OntologyFormat.THREEDXML:
            try:
                from .threedxml_ontology_extractor import ThreeDXMLExtractor
            except Exception:
                from Services.threedxml_ontology_extractor import ThreeDXMLExtractor
            return ThreeDXMLExtractor(source_path)
        elif format_type == OntologyFormat.OWL_RDF:
            # TODO: Implement OWL/RDF extractor
            raise NotImplementedError("OWL/RDF extractor not yet implemented")
        else:
            raise ValueError(f"Unknown format: {format_type}")
    
    @staticmethod
    def _detect_format(source_path: str) -> OntologyFormat:
        """Auto-detect ontology format from source path"""
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source path not found: {source_path}")
        
        # Check for SPLM schema structure
        if all(os.path.isdir(os.path.join(source_path, d)) 
               for d in ["Business", "Objects", "Relationships"]):
            return OntologyFormat.SPLM_SCHEMA
        
        # Check for 3DXML files
        if any(f.endswith('.3dxml') for f in os.listdir(source_path)):
            return OntologyFormat.THREEDXML
        
        # Check for OWL/RDF files
        if any(f.endswith(('.owl', '.rdf', '.ttl')) for f in os.listdir(source_path)):
            return OntologyFormat.OWL_RDF
        
        raise ValueError(f"Cannot detect format for source: {source_path}")


async def extract_ontology(
    source_path: str,
    format_type: OntologyFormat = None,
    output_path: str = None
) -> Dict[str, Any]:
    """
    Main entry point for ontology extraction
    
    Args:
        source_path: Path to ontology source
        format_type: Format of source (auto-detect if None)
        output_path: Optional path to save JSON output
    
    Returns:
        Extracted ontology as dictionary
    """
    extractor = OntologyExtractorFactory.create(source_path, format_type)
    result = extractor.extract()
    
    # Validate
    is_valid, errors = extractor.validate()
    if not is_valid:
        logger.warning(f"Ontology validation warnings: {errors}")
    
    # Save if requested
    if output_path:
        extractor.save_json(output_path)
    
    return result


if __name__ == "__main__":
    import asyncio
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Example: Extract SPLM schema
    SPLM_PATH = r"C:\Users\895428\Depo\SPLM_Folder\Schema - Shared"
    OUTPUT_PATH = r"c:\Users\895428\DEPO_RR\Depo_onto\outputs\3dexperience_ontology.json"
    
    try:
        result = asyncio.run(extract_ontology(
            SPLM_PATH,
            OntologyFormat.SPLM_SCHEMA,
            OUTPUT_PATH
        ))
        
        print(f"\nExtraction Summary:")
        print(f"  Format: {result['metadata']['source_format']}")
        print(f"  Entities: {result['metadata']['stats']['entities']}")
        print(f"  Relationships: {result['metadata']['stats']['relationships']}")
        print(f"  Attributes: {result['metadata']['stats']['unique_attributes']}")
        print(f"  Entity Types: {result['metadata']['stats']['entity_types']}")
        print(f"  Output: {OUTPUT_PATH}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
