"""
Ontology Mapping Service
Maps and aligns EXPRESS schemas to target ontologies
Handles entity deduplication, namespace mapping, and constraint merging
"""

import logging
import re
from copy import deepcopy
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class EntityMapping:
    """Maps source entity to target entity with confidence"""
    source_entity: str
    target_entity: str
    confidence: float  # 0-1
    reason: str
    property_mappings: Dict[str, str] = field(default_factory=dict)  # source_prop -> target_prop
    constraint_mappings: Dict[str, str] = field(default_factory=dict)  # source_constraint -> target_constraint


@dataclass
class OntologyAlignmentResult:
    """Result of ontology alignment operation"""
    source_namespace: str
    target_namespace: str
    entity_mappings: List[EntityMapping]
    unmapped_entities: List[str]
    aligned_owl_ttl: str
    mapping_metadata: Dict[str, Any]
    confidence_score: float  # Overall confidence 0-1


class OntologyMappingService:
    """Service for mapping and aligning ontologies"""
    
    # Common entity name transformations for matching
    ENTITY_NAME_VARIATIONS = {
        'product': ['product_definition', 'product_item', 'product_type'],
        'part': ['part_definition', 'part_design', 'component'],
        'assembly': ['assembly_definition', 'assembly_item', 'assembly_structure'],
        'representation': ['product_representation', 'geometric_representation', 'representation_item'],
        'property': ['property_definition', 'property_value', 'attribute'],
        'relation': ['relationship', 'relationship_definition', 'connection'],
        'context': ['application_context', 'geometric_representation_context'],
    }
    
    @staticmethod
    def string_similarity(s1: str, s2: str) -> float:
        """Calculate similarity between two strings (0-1)"""
        s1_lower = s1.lower()
        s2_lower = s2.lower()
        
        # Exact match
        if s1_lower == s2_lower:
            return 1.0
        
        # Substring match
        if s1_lower in s2_lower or s2_lower in s1_lower:
            return 0.85
        
        # Levenshtein-based sequence matching
        matcher = SequenceMatcher(None, s1_lower, s2_lower)
        return matcher.ratio()
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize entity name for comparison"""
        # Remove prefixes/suffixes
        name = name.lower()
        name = re.sub(r'^(source_|target_|impl_|abstract_)', '', name)
        name = re.sub(r'(_definition|_item|_type|_value)$', '', name)
        return name
    
    @staticmethod
    def extract_properties_from_owl(owl_ttl: str, entity_name: str) -> Dict[str, str]:
        """Extract properties for an entity from OWL"""
        properties = {}
        
        # Pattern: ex:entity_propertyName a owl:DatatypeProperty ;
        pattern = rf"ex:{entity_name}_(\w+)\s+a\s+owl:(?:Datatype|Object)Property"
        matches = re.findall(pattern, owl_ttl, re.IGNORECASE)
        
        for prop in matches:
            properties[prop.lower()] = prop
        
        return properties
    
    @staticmethod
    def find_similar_entities(
        source_entities: List[str],
        target_entities: List[str],
        threshold: float = 0.6
    ) -> List[Tuple[str, str, float]]:
        """
        Find similar entities between source and target
        
        Returns:
            List of (source_entity, target_entity, confidence) tuples
        """
        similarities = []
        
        for source in source_entities:
            source_norm = OntologyMappingService.normalize_name(source)
            best_match = None
            best_score = 0
            
            for target in target_entities:
                target_norm = OntologyMappingService.normalize_name(target)
                
                # Direct similarity
                score = OntologyMappingService.string_similarity(source_norm, target_norm)
                
                # Check name variations
                if source_norm in OntologyMappingService.ENTITY_NAME_VARIATIONS:
                    variations = OntologyMappingService.ENTITY_NAME_VARIATIONS[source_norm]
                    if any(var in target_norm for var in variations):
                        score = max(score, 0.8)
                
                if score > best_score:
                    best_score = score
                    best_match = target
            
            if best_match and best_score >= threshold:
                similarities.append((source, best_match, best_score))
        
        return similarities
    
    @staticmethod
    def map_properties(
        source_properties: Dict[str, str],
        target_properties: Dict[str, str]
    ) -> Dict[str, str]:
        """Map properties from source to target"""
        mapping = {}
        
        for src_prop, src_canonical in source_properties.items():
            src_norm = OntologyMappingService.normalize_name(src_prop)
            best_match = None
            best_score = 0
            
            for tgt_prop, tgt_canonical in target_properties.items():
                tgt_norm = OntologyMappingService.normalize_name(tgt_prop)
                score = OntologyMappingService.string_similarity(src_norm, tgt_norm)
                
                if score > best_score:
                    best_score = score
                    best_match = tgt_canonical
            
            if best_match and best_score >= 0.7:
                mapping[src_canonical] = best_match
        
        return mapping
    
    @staticmethod
    def generate_mapping_report(
        mappings: List[EntityMapping],
        unmapped: List[str]
    ) -> Dict[str, Any]:
        """Generate human-readable mapping report"""
        report = {
            'total_entities': len(mappings) + len(unmapped),
            'mapped_entities': len(mappings),
            'unmapped_entities': len(unmapped),
            'coverage': len(mappings) / (len(mappings) + len(unmapped)) if (len(mappings) + len(unmapped)) > 0 else 0,
            'average_confidence': sum(m.confidence for m in mappings) / len(mappings) if mappings else 0,
            'high_confidence_mappings': len([m for m in mappings if m.confidence >= 0.9]),
            'medium_confidence_mappings': len([m for m in mappings if 0.7 <= m.confidence < 0.9]),
            'low_confidence_mappings': len([m for m in mappings if m.confidence < 0.7]),
            'mappings': [
                {
                    'source': m.source_entity,
                    'target': m.target_entity,
                    'confidence': round(m.confidence, 2),
                    'reason': m.reason,
                    'property_count': len(m.property_mappings),
                }
                for m in sorted(mappings, key=lambda x: x.confidence, reverse=True)
            ],
            'unmapped': unmapped,
        }
        return report
    
    @staticmethod
    def align_owl_namespaces(
        source_owl_ttl: str,
        source_namespace: str,
        target_namespace: str,
        entity_mappings: List[EntityMapping]
    ) -> str:
        """
        Generate aligned OWL with target namespace
        
        Transforms source OWL to target namespace and applies entity mappings
        """
        from rdflib import Graph, URIRef
        source = Graph().parse(data=source_owl_ttl, format='turtle')
        replacements = {}
        for mapping in entity_mappings:
            replacements[URIRef(source_namespace + mapping.source_entity)] = URIRef(target_namespace + mapping.target_entity)
            for src_prop, tgt_prop in mapping.property_mappings.items():
                replacements[URIRef(source_namespace + mapping.source_entity + '_' + src_prop)] = URIRef(target_namespace + mapping.target_entity + '_' + tgt_prop)
        result = Graph()
        for prefix, namespace in source.namespaces():
            result.bind(prefix, namespace)
        result.bind('target', target_namespace)
        for triple in source:
            result.add(tuple(replacements.get(term, term) for term in triple))
        # Name similarity alone does not justify owl:equivalentClass assertions.
        return result.serialize(format='turtle')
    
    @staticmethod
    def merge_constraints(
        source_mappings: Dict[str, Any],
        target_entity_constraints: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge constraints from source mapping to target entity"""
        merged = deepcopy(target_entity_constraints)
        
        # Add UNIQUE constraints
        if 'unique_constraints' in source_mappings:
            merged.setdefault('unique_constraints', [])
            merged['unique_constraints'].extend(deepcopy(source_mappings['unique_constraints']))
        
        # Add cardinality constraints
        if 'cardinality_bounds' in source_mappings:
            merged.setdefault('cardinality_bounds', {})
            for key, bounds in source_mappings['cardinality_bounds'].items():
                existing = merged['cardinality_bounds'].get(key)
                if existing is not None and existing != bounds:
                    raise ValueError(f'Conflicting cardinality constraints for {key}; review is required')
                merged['cardinality_bounds'][key] = deepcopy(bounds)
        
        # Add WHERE rules (as rdfs:comments for now)
        if 'where_rules' in source_mappings:
            merged.setdefault('business_rules', [])
            merged['business_rules'].extend(deepcopy(source_mappings['where_rules']))
        
        return merged


class TargetOntologyRegistry:
    """Registry of known target ontologies for mapping"""
    
    KNOWN_ONTOLOGIES = {
        'windchill': {
            'namespace': 'http://infineon.com/windchill/ontology#',
            'entities': [
                'Product', 'PartDesign', 'Assembly', 'Representation',
                'PartProperty', 'AssemblyStructure', 'Relationship'
            ],
        },
        'ap242_product': {
            'namespace': 'http://iso.org/iso10303/ap242/product#',
            'entities': [
                'product_definition', 'product_structure', 'representation_item',
                'geometric_representation_context', 'cartesian_point',
                'direction', 'axis2_placement_3d'
            ],
        },
        'pifrl': {
            'namespace': 'http://w3id.org/pifrl/ontology#',
            'entities': [
                'Product', 'Component', 'Subcomponent', 'DesignItem',
                'ManufacturingItem', 'InterchangeabilityClass'
            ],
        },
    }
    
    @classmethod
    def get_ontology(cls, ontology_name: str) -> Optional[Dict[str, Any]]:
        """Get ontology definition"""
        return cls.KNOWN_ONTOLOGIES.get(ontology_name.lower())
    
    @classmethod
    def list_ontologies(cls) -> List[str]:
        """List available ontologies"""
        return list(cls.KNOWN_ONTOLOGIES.keys())


def map_express_to_ontology(
    source_owl_ttl: str,
    source_namespace: str,
    source_entities: List[str],
    target_ontology_name: str,
    confidence_threshold: float = 0.6
) -> OntologyAlignmentResult:
    """
    Main function: Map EXPRESS schema to target ontology
    
    Args:
        source_owl_ttl: Generated OWL from Step 2
        source_namespace: Source namespace URI
        source_entities: List of entity names from source
        target_ontology_name: Name of target ontology (windchill, ap242_product, etc.)
        confidence_threshold: Minimum confidence for mappings
        
    Returns:
        OntologyAlignmentResult with aligned OWL and mappings
    """
    # Get target ontology
    target_onto = TargetOntologyRegistry.get_ontology(target_ontology_name)
    if not target_onto:
        raise ValueError(f"Unknown target ontology: {target_ontology_name}")
    
    logger.info(f"Mapping to target ontology: {target_ontology_name}")
    
    # Find similar entities
    similarities = OntologyMappingService.find_similar_entities(
        source_entities,
        target_onto['entities'],
        threshold=confidence_threshold
    )
    
    # Create entity mappings
    entity_mappings = []
    mapped_source_entities = set()
    
    for source_entity, target_entity, confidence in similarities:
        mapped_source_entities.add(source_entity)
        
        # Extract and map properties
        source_props = OntologyMappingService.extract_properties_from_owl(
            source_owl_ttl,
            source_entity
        )
        # This registry contains classes, not property definitions. Do not
        # manufacture property mappings from its class names.
        target_props = {}
        
        prop_mappings = OntologyMappingService.map_properties(
            source_props,
            target_props
        )
        
        reason = f"String similarity: {confidence:.1%}"
        if confidence == 1.0:
            reason = "Exact match"
        elif confidence >= 0.9:
            reason = "Very similar name"
        elif confidence >= 0.75:
            reason = "Similar name with related properties"
        
        mapping = EntityMapping(
            source_entity=source_entity,
            target_entity=target_entity,
            confidence=confidence,
            reason=reason,
            property_mappings=prop_mappings
        )
        entity_mappings.append(mapping)
    
    # Find unmapped entities
    unmapped_entities = [e for e in source_entities if e not in mapped_source_entities]
    
    # Generate aligned OWL
    aligned_owl = OntologyMappingService.align_owl_namespaces(
        source_owl_ttl,
        source_namespace,
        target_onto['namespace'],
        entity_mappings
    )
    
    # Generate mapping metadata
    mapping_metadata = OntologyMappingService.generate_mapping_report(
        entity_mappings,
        unmapped_entities
    )
    
    # Calculate overall confidence
    overall_confidence = mapping_metadata['average_confidence'] * mapping_metadata['coverage']
    
    result = OntologyAlignmentResult(
        source_namespace=source_namespace,
        target_namespace=target_onto['namespace'],
        entity_mappings=entity_mappings,
        unmapped_entities=unmapped_entities,
        aligned_owl_ttl=aligned_owl,
        mapping_metadata=mapping_metadata,
        confidence_score=overall_confidence
    )
    
    logger.info(f"Ontology alignment complete: {mapping_metadata['mapped_entities']}/{mapping_metadata['total_entities']} entities mapped")
    
    return result
