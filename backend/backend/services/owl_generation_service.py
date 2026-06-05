"""
OWL/Turtle Generation Service for EXPRESS and STEP Schemas
Converts parsed EXPRESS and STEP schemas to RDF Turtle format for ontology alignment
"""

import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Set
import sys
from collections import defaultdict

logger = logging.getLogger(__name__)

# In-memory storage for generated OWL during import session
_owl_storage: Dict[str, str] = {}


class OWLGenerationService:
    """Service for generating OWL/Turtle from EXPRESS schemas"""
    
    @staticmethod
    def generate_owl_from_express(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """
        Generate OWL/Turtle RDF from EXPRESS schema file
        
        Args:
            file_content: Raw .exp file bytes
            filename: Original filename
            
        Returns:
            (owl_ttl: str, metadata: Dict)
            - owl_ttl: RDF Turtle representation of schema
            - metadata: Schema metrics (entities, DERIVE, etc.)
        """
        try:
            import tempfile
            
            # Add import_master to path
            import_master_path = Path(r"C:\Users\895428\Depo\import_master\src")
            if str(import_master_path) not in sys.path:
                sys.path.insert(0, str(import_master_path))
            
            from parsers.express_parser import parse_express, emit_owl_ttl
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(suffix='.exp', delete=False) as f:
                f.write(file_content)
                temp_path = Path(f.name)
            
            try:
                # Parse schema
                schema = parse_express(temp_path)
                
                # Generate OWL/Turtle with required parameters
                base_uri = f"http://depo-onto.local/exp#{schema.name}/"
                owl_ttl = emit_owl_ttl(
                    schema,
                    base_uri=base_uri,
                    prefix="ap242dm",
                    source_path=temp_path
                )
                
                # Extract metadata
                derives = sum(len(e.derived_attributes) for e in schema.entities.values())
                inverses = sum(len(e.inverse_attributes) for e in schema.entities.values())
                unique = sum(len(e.unique_constraints) for e in schema.entities.values())
                
                metadata = {
                    'schema_name': schema.name,
                    'schema_id': schema.schema_id,
                    'entities': list(schema.entities.keys()),
                    'entity_count': len(schema.entities),
                    'enumerations': len(schema.enumerations),
                    'select_types': len(schema.select_types),
                    'derived_attributes': derives,
                    'inverse_attributes': inverses,
                    'unique_constraints': unique,
                    'schema_references': list(schema.references.keys()),
                    'reference_count': len(schema.references),
                    'owl_triple_count': owl_ttl.count('\n'),  # Rough estimate
                }
                
                logger.info(f"OWL generation complete: {metadata['owl_triple_count']} lines")
                
                return owl_ttl, metadata
                
            finally:
                temp_path.unlink()  # Clean up temp file
                
        except Exception as e:
            logger.error(f"OWL generation failed: {e}")
            raise ValueError(f"Failed to generate OWL: {str(e)}")
    
    @staticmethod
    def generate_owl_from_step(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """
        Generate OWL/Turtle RDF from STEP data file (.stp, .step, .stpx)
        
        Args:
            file_content: Raw STEP file bytes
            filename: Original filename
            
        Returns:
            (owl_ttl: str, metadata: Dict)
            - owl_ttl: RDF Turtle representation of STEP entities
            - metadata: STEP metrics (entities, products, representations, etc.)
        """
        try:
            # Add import_master to path
            import_master_path = Path(r"C:\Users\895428\Depo\import_master\src")
            if str(import_master_path) not in sys.path:
                sys.path.insert(0, str(import_master_path))
            
            from parsers.step_parser import parse_step_with_pmi, get_pmi_summary
            
            # Write to temp file
            file_ext = filename.split('.')[-1].lower() if '.' in filename else 'stp'
            temp_suffix = f'.{file_ext}'
            
            with tempfile.NamedTemporaryFile(suffix=temp_suffix, delete=False) as f:
                f.write(file_content)
                temp_path = Path(f.name)
            
            try:
                # Parse STEP file
                doc = parse_step_with_pmi(temp_path)
                summary = get_pmi_summary(doc)
                
                # Generate OWL/Turtle from STEP entities
                base_uri = f"http://depo-onto.local/step#{doc.metadata.file_name.replace(' ', '_')}_"
                prefix = "step"
                
                owl_lines = [
                    f"# STEP Data Ontology - {doc.metadata.file_name}",
                    f"# Format: {doc.metadata.format.upper()}",
                    f"# Schema: {doc.metadata.file_schema or 'AP242/AP203'}",
                    f"# Total Entities: {summary['total_entities']}",
                    f"",
                    f"@prefix {prefix}: <{base_uri}> .",
                    f"@prefix owl: <http://www.w3.org/2002/07/owl#> .",
                    f"@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
                    f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
                    f"@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
                    f"",
                ]
                
                # Track unique entity types found
                entity_types: Set[str] = set()
                entity_relationships: Dict[str, Set[int]] = defaultdict(set)
                
                # Process entities and their relationships
                for entity in doc.entities:
                    entity_types.add(entity.entity_type)
                    # Track references for later relationship generation
                    for ref_id in entity.ref_ids:
                        entity_relationships[entity.entity_type].add(ref_id)
                
                # Define classes for each entity type
                owl_lines.append("# Entity Type Classes")
                for entity_type in sorted(entity_types):
                    safe_type = entity_type.replace(' ', '_').replace('-', '_')
                    owl_lines.append(f"{prefix}:{safe_type}")
                    owl_lines.append(f"    a owl:Class ;")
                    owl_lines.append(f"    rdfs:label \"{entity_type}\" ;")
                    owl_lines.append(f"    rdfs:comment \"STEP entity type from {doc.metadata.format}\" .")
                    owl_lines.append(f"")
                
                # Define individuals for each entity instance
                owl_lines.append("# Entity Instances")
                for entity in doc.entities:
                    safe_type = entity.entity_type.replace(' ', '_').replace('-', '_')
                    safe_id = str(entity.step_id).replace(' ', '_')
                    owl_lines.append(f"{prefix}:entity_{safe_id}")
                    owl_lines.append(f"    a {prefix}:{safe_type} ;")
                    owl_lines.append(f"    rdfs:label \"Entity #{entity.step_id}\" ;")
                    
                    # Add reference relationships
                    if entity.ref_ids:
                        owl_lines.append(f"    {prefix}:references {', '.join(f'{prefix}:entity_{ref}' for ref in sorted(set(entity.ref_ids)))} ;")
                    
                    owl_lines.append(f"    rdfs:comment \"{entity.raw_args[:100]}...\" .")
                    owl_lines.append(f"")
                
                # Add CAD product/representation hierarchy if available
                if doc.cad_products:
                    owl_lines.append("# CAD Product Hierarchy")
                    owl_lines.append(f"{prefix}:CAD_Products a owl:Class ; rdfs:label \"CAD Products\" .")
                    for prod in doc.cad_products:
                        owl_lines.append(f"{prefix}:product_{prod.id} a {prefix}:CAD_Products .")
                    owl_lines.append(f"")
                
                # Add PMI metadata
                if summary['has_pmi']:
                    owl_lines.append("# Product Manufacturing Information (PMI)")
                    if summary['geometric_tolerances'] > 0:
                        owl_lines.append(f"{prefix}:has_geometric_tolerances {summary['geometric_tolerances']} .")
                    if summary['dimensions'] > 0:
                        owl_lines.append(f"{prefix}:has_dimensions {summary['dimensions']} .")
                    if summary['annotations'] > 0:
                        owl_lines.append(f"{prefix}:has_annotations {summary['annotations']} .")
                    owl_lines.append(f"")
                
                owl_ttl = '\n'.join(owl_lines)
                
                # Prepare metadata
                metadata = {
                    'schema_name': f"STEP_{doc.metadata.format}",
                    'schema_id': f"{doc.metadata.file_schema or 'AP242'}_{doc.metadata.file_name}",
                    'entities': [e.entity_type for e in doc.entities[:100]],  # First 100 entity types
                    'entity_count': len(doc.entities),
                    'unique_entity_types': len(entity_types),
                    'entity_types_list': sorted(list(entity_types)),
                    'cad_products': summary['cad_products'],
                    'cad_representations': summary['cad_representations'],
                    'cad_topology': summary['cad_topology'],
                    'cad_geometry': summary['cad_geometry'],
                    'has_pmi': summary['has_pmi'],
                    'geometric_tolerances': summary['geometric_tolerances'],
                    'datums': summary['datums'],
                    'dimensions': summary['dimensions'],
                    'annotations': summary['annotations'],
                    'owl_triple_count': owl_ttl.count('\n'),
                }
                
                logger.info(f"STEP OWL generation complete: {metadata['entity_count']} entities, {metadata['unique_entity_types']} types")
                
                return owl_ttl, metadata
                
            finally:
                temp_path.unlink()  # Clean up temp file
                
        except Exception as e:
            logger.error(f"STEP OWL generation failed: {e}", exc_info=True)
            raise ValueError(f"Failed to generate OWL from STEP: {str(e)}")
    
    @staticmethod
    def store_owl(session_id: str, owl_ttl: str) -> None:
        """Store generated OWL for later retrieval"""
        _owl_storage[session_id] = owl_ttl
        logger.info(f"OWL stored for session {session_id}: {len(owl_ttl)} bytes")
    
    @staticmethod
    def retrieve_owl(session_id: str) -> Optional[str]:
        """Retrieve stored OWL for a session"""
        return _owl_storage.get(session_id)
    
    @staticmethod
    def clear_owl(session_id: str) -> None:
        """Clear stored OWL after use"""
        if session_id in _owl_storage:
            del _owl_storage[session_id]
