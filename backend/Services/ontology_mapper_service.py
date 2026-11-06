"""
Legacy ontology mapping seed service - provides built-in PLMXML -> AP242, STEP -> AP242, and Windchill -> AP242 templates for compatibility. The primary Semantic Bridge flow is SemanticWorkflowService.instance.link, which aligns imported instances and metadata to loaded ontology classes/properties.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime


class MappingConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RelationType(str, Enum):
    EQUIVALENT_CLASS = "equivalentClass"
    EXACT_MATCH = "exactMatch"
    CLOSE_MATCH = "closeMatch"
    PREDICATE = "predicate"
    LABEL = "label"
    MAPS_TO = "mapsTo"


@dataclass
class MappingEntry:
    """Represents a single mapping between source and target ontology entities"""
    source_entity: str
    target_entity: str
    mapping_confidence: MappingConfidence
    rationale: str
    key_attribute_mappings: Dict[str, str]
    relationship_mappings: Dict[str, str]
    mapping_type: str = "entity"
    
    def to_dict(self) -> Dict:
        return {
            "source_entity": self.source_entity,
            "target_entity": self.target_entity,
            "mapping_confidence": self.mapping_confidence.value,
            "rationale": self.rationale,
            "key_attribute_mappings": self.key_attribute_mappings,
            "relationship_mappings": self.relationship_mappings,
            "mapping_type": self.mapping_type,
        }


@dataclass
class DataDictionaryEntry:
    """Represents a term in the data dictionary"""
    term_id: str
    label: str
    definition: Optional[str] = None
    ontology_prefix: str = ""
    synonyms: List[str] = None
    related_terms: List[str] = None
    
    def __post_init__(self):
        if self.synonyms is None:
            self.synonyms = []
        if self.related_terms is None:
            self.related_terms = []
    
    def to_dict(self) -> Dict:
        return {
            "term_id": self.term_id,
            "label": self.label,
            "definition": self.definition,
            "ontology_prefix": self.ontology_prefix,
            "synonyms": self.synonyms,
            "related_terms": self.related_terms,
        }


@dataclass
class MappingVocabulary:
    """Represents relationship mappings in the vocabulary"""
    source_term: str
    source_label: str
    mapping_type: RelationType
    target_term: str
    target_label: str
    confidence: MappingConfidence = MappingConfidence.HIGH
    
    def to_dict(self) -> Dict:
        return {
            "source_term": self.source_term,
            "source_label": self.source_label,
            "mapping_type": self.mapping_type.value,
            "target_term": self.target_term,
            "target_label": self.target_label,
            "confidence": self.confidence.value,
        }


class PLMXMLtoAP242Mapper:
    """PLMXML to AP242 ontology mappings"""
    
    MAPPINGS: List[MappingEntry] = [
        MappingEntry(
            source_entity="Part",
            target_entity="ap242:Part",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="PLMXML Part/Product carries the engineering identity that aligns directly to AP242 Part.",
            key_attribute_mappings={
                "@id": "Part.uid",
                "@name": "Part.name",
                "@partNumber": "Part.external_id",
                "@description": "Part.description",
            },
            relationship_mappings={
                "@masterRef": "PartVersion.IS_VERSION_OF.Part",
                "UserData[@ref]": "Part.HAS_PROPERTY_SET.UserData",
            },
        ),
        MappingEntry(
            source_entity="ProductRevision",
            target_entity="ap242:PartVersion",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="PLMXML ProductRevision represents versioned lifecycle state equivalent to AP242 PartVersion.",
            key_attribute_mappings={
                "@id": "PartVersion.uid",
                "@name": "PartVersion.name",
                "@revision": "PartVersion.version_id",
                "@masterRef": "PartVersion.part_uid",
            },
            relationship_mappings={
                "@masterRef": "PartVersion.IS_VERSION_OF.Part",
                "ChangeNoticeRef/@ref": "PartVersion.IMPLEMENTS_CHANGE.ChangeNotice",
            },
        ),
        MappingEntry(
            source_entity="ProductView",
            target_entity="ap242:PartView",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="PLMXML ProductView captures design/manufacturing view partitioning that aligns with AP242 PartView.",
            key_attribute_mappings={
                "@id": "PartView.uid",
                "@name": "PartView.name",
                "@viewType": "PartView.view_type",
            },
            relationship_mappings={
                "@rootRefs": "PartView.HAS_ROOT_OCCURRENCE.Occurrence",
                "@productRef": "PartView.REPRESENTS.PartVersion",
            },
        ),
        MappingEntry(
            source_entity="ProductInstance",
            target_entity="ap242:Occurrence",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="PLMXML ProductInstance is an assembly occurrence and maps directly to AP242 Occurrence.",
            key_attribute_mappings={
                "@id": "Occurrence.uid",
                "@name": "Occurrence.name",
                "@quantity": "Occurrence.quantity",
            },
            relationship_mappings={
                "@partRef": "Occurrence.RELATED_VIEW_OR_PART.PartView",
                "ProductInstance": "Occurrence.HAS_CHILD_OCCURRENCE.Occurrence",
            },
        ),
    ]
    
    @staticmethod
    def get_mappings() -> List[Dict]:
        """Return all PLMXML→AP242 mappings"""
        return [m.to_dict() for m in PLMXMLtoAP242Mapper.MAPPINGS]
    
    @staticmethod
    def get_data_dictionary() -> List[Dict]:
        """Generate data dictionary from PLMXML entities"""
        return [
            DataDictionaryEntry(
                term_id="plmxml:Part",
                label="Part",
                definition="A distinct physical or logical entity in PLMXML representing an engineering part",
                ontology_prefix="plmxml",
                synonyms=["Product", "Component"],
                related_terms=["plmxml:PartVersion", "plmxml:ProductRevision"],
            ).to_dict(),
            DataDictionaryEntry(
                term_id="plmxml:ProductRevision",
                label="Product Revision",
                definition="A versioned state of a PLMXML Part or Product",
                ontology_prefix="plmxml",
                synonyms=["PartVersion", "Revision"],
                related_terms=["plmxml:Part", "plmxml:PartView"],
            ).to_dict(),
            DataDictionaryEntry(
                term_id="plmxml:ProductView",
                label="Product View",
                definition="A specific representation context (design, manufacturing, etc.) for a PLMXML Product",
                ontology_prefix="plmxml",
                synonyms=["View", "Context"],
                related_terms=["plmxml:ProductRevision", "plmxml:Occurrence"],
            ).to_dict(),
            DataDictionaryEntry(
                term_id="plmxml:Occurrence",
                label="Occurrence",
                definition="An instance of a Part within an assembly structure",
                ontology_prefix="plmxml",
                synonyms=["Instance", "Usage"],
                related_terms=["plmxml:Part", "plmxml:ProductView"],
            ).to_dict(),
            DataDictionaryEntry(
                term_id="ap242:Part",
                label="AP242 Part",
                definition="An AP242-compliant Part entity representing physical or logical design elements",
                ontology_prefix="ap242",
                related_terms=["ap242:PartVersion", "ap242:PartView"],
            ).to_dict(),
            DataDictionaryEntry(
                term_id="ap242:PartVersion",
                label="AP242 Part Version",
                definition="A versioned representation of an AP242 Part",
                ontology_prefix="ap242",
                related_terms=["ap242:Part", "ap242:PartView"],
            ).to_dict(),
        ]


class STEPtoAP242Mapper:
    """STEP to AP242 ontology mappings"""
    
    MAPPINGS: List[MappingEntry] = [
        MappingEntry(
            source_entity="step:PRODUCT",
            target_entity="ap242:Part",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="STEP PRODUCT carries the engineered item identity and aligns to the AP242 MBD Part business object.",
            key_attribute_mappings={
                "step_id": "Part.uid",
                "external_id": "Part.id",
                "name": "Part.Name",
                "description": "Part.Description",
            },
            relationship_mappings={
                "PRODUCT_DEFINITION_FORMATION": "Part.HAS_VERSION.PartVersion",
            },
        ),
        MappingEntry(
            source_entity="step:PRODUCT_DEFINITION_FORMATION",
            target_entity="ap242:PartVersion",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="PRODUCT_DEFINITION_FORMATION is the revision/version formation for a PRODUCT and aligns to AP242 PartVersion.",
            key_attribute_mappings={
                "step_id": "PartVersion.uid",
                "external_id": "PartVersion.Id",
                "description": "PartVersion.Description",
            },
            relationship_mappings={
                "#product": "PartVersion.IS_VERSION_OF.Part",
                "PRODUCT_DEFINITION": "PartVersion.HAS_VIEW.PartView",
            },
        ),
        MappingEntry(
            source_entity="step:PRODUCT_DEFINITION",
            target_entity="ap242:PartView",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="PRODUCT_DEFINITION captures a design/manufacturing view of a versioned part and aligns to AP242 PartView.",
            key_attribute_mappings={
                "step_id": "PartView.uid",
                "description": "PartView.Description",
            },
            relationship_mappings={
                "#formation": "PartView.IS_VIEW_OF.PartVersion",
                "PRODUCT_DEFINITION_SHAPE": "PartView.ShapeElement",
                "SHAPE_REPRESENTATION": "PartView.GeometricModel",
            },
        ),
        MappingEntry(
            source_entity="step:PRODUCT_DEFINITION_SHAPE",
            target_entity="ap242:PartShapeElement",
            mapping_confidence=MappingConfidence.MEDIUM,
            rationale="PRODUCT_DEFINITION_SHAPE links product definition context to shape semantics and aligns to AP242 PartShapeElement.",
            key_attribute_mappings={
                "step_id": "PartShapeElement.uid",
                "name": "PartShapeElement.Name",
                "description": "PartShapeElement.Description",
            },
            relationship_mappings={
                "#definition": "PartShapeElement.DESCRIBES.PartView",
            },
        ),
        MappingEntry(
            source_entity="step:SHAPE_REPRESENTATION",
            target_entity="ap242:GeometricModel",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="SHAPE_REPRESENTATION carries the geometric model representation associated with a PartView in AP242 MBD.",
            key_attribute_mappings={
                "step_id": "GeometricModel.uid",
                "name": "GeometricModel.Name",
            },
            relationship_mappings={
                "#context": "GeometricModel.HAS_CONTEXT.GeometricContext",
            },
        ),
        MappingEntry(
            source_entity="step:NEXT_ASSEMBLY_USAGE_OCCURRENCE",
            target_entity="ap242:PartViewRelationship",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="NEXT_ASSEMBLY_USAGE_OCCURRENCE represents assembly usage between product definitions and aligns to AP242 PartViewRelationship.",
            key_attribute_mappings={
                "step_id": "PartViewRelationship.uid",
                "name": "PartViewRelationship.Name",
            },
            relationship_mappings={
                "#relating_product_definition": "PartViewRelationship.RELATING.PartView",
                "#related_product_definition": "PartViewRelationship.RELATED.PartView",
            },
        ),
    ]
    
    @staticmethod
    def get_mappings() -> List[Dict]:
        """Return all STEP→AP242 mappings"""
        return [m.to_dict() for m in STEPtoAP242Mapper.MAPPINGS]


class WindchilltoAP242Mapper:
    """Windchill to AP242 ontology mappings"""
    
    MAPPINGS: List[MappingEntry] = [
        MappingEntry(
            source_entity="windchill:PartMaster",
            target_entity="ap242:Part",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="Windchill PartMaster is the primary part entity and maps to AP242 Part",
            key_attribute_mappings={
                "partNumber": "Part.external_id",
                "name": "Part.name",
                "description": "Part.description",
            },
            relationship_mappings={
                "partVersions": "Part.HAS_VERSION.PartVersion",
            },
        ),
        MappingEntry(
            source_entity="windchill:PartVersion",
            target_entity="ap242:PartVersion",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="PartVersion in Windchill represents lifecycle state aligned with AP242 PartVersion",
            key_attribute_mappings={
                "versionId": "PartVersion.version_id",
                "iterationId": "PartVersion.iteration_id",
            },
            relationship_mappings={
                "partMaster": "PartVersion.IS_VERSION_OF.Part",
            },
        ),
        MappingEntry(
            source_entity="windchill:EPMDocument",
            target_entity="ap242:Document",
            mapping_confidence=MappingConfidence.HIGH,
            rationale="EPMDocument represents engineering documents and aligns with AP242 Document",
            key_attribute_mappings={
                "docNumber": "Document.document_number",
                "title": "Document.title",
            },
            relationship_mappings={},
        ),
    ]
    
    @staticmethod
    def get_mappings() -> List[Dict]:
        """Return all Windchill→AP242 mappings"""
        return [m.to_dict() for m in WindchilltoAP242Mapper.MAPPINGS]


class OntologyMapperService:
    """Legacy seed mapper. Prefer SemanticWorkflowService for instance-to-ontology bridge mappings."""
    
    MAPPERS = {
        "plmxml": PLMXMLtoAP242Mapper,
        "step": STEPtoAP242Mapper,
        "windchill": WindchilltoAP242Mapper,
    }
    
    MAPPING_OPTIONS = [
        {"value": "plmxml", "label": "PLMXML → AP242 seed profile", "legacy": True},
        {"value": "step", "label": "STEP → AP242 seed profile", "legacy": True},
        {"value": "windchill", "label": "Windchill → AP242 seed profile", "legacy": True},
    ]
    
    MAPPING_TYPES = [
        "equivalentClass",
        "exactMatch",
        "closeMatch",
        "predicate",
        "label",
        "mapsTo",
    ]
    
    @staticmethod
    def get_mapping_options() -> List[Dict[str, str]]:
        """Get available mapping options"""
        return OntologyMapperService.MAPPING_OPTIONS
    
    @staticmethod
    def get_mappings(mapping_type: str) -> List[Dict]:
        """Get mappings for a specific mapping type"""
        mapper = OntologyMapperService.MAPPERS.get(mapping_type.lower())
        if not mapper:
            return []
        return mapper.get_mappings()
    
    @staticmethod
    def get_data_dictionary(mapping_type: str) -> List[Dict]:
        """Generate data dictionary for a mapping type"""
        if mapping_type.lower() == "plmxml":
            return PLMXMLtoAP242Mapper.get_data_dictionary()
        elif mapping_type.lower() == "step":
            return [
                DataDictionaryEntry(
                    term_id="step:PRODUCT",
                    label="PRODUCT",
                    definition="STEP/AP242 product identity entity mapped to AP242 Part",
                    ontology_prefix="step",
                    synonyms=["Product", "Part"],
                    related_terms=["step:PRODUCT_DEFINITION_FORMATION", "ap242:Part"],
                ).to_dict(),
                DataDictionaryEntry(
                    term_id="step:PRODUCT_DEFINITION_FORMATION",
                    label="PRODUCT DEFINITION FORMATION",
                    definition="STEP/AP242 version or formation entity mapped to AP242 PartVersion",
                    ontology_prefix="step",
                    synonyms=["ProductDefinitionFormation", "Revision", "Version"],
                    related_terms=["step:PRODUCT", "step:PRODUCT_DEFINITION", "ap242:PartVersion"],
                ).to_dict(),
                DataDictionaryEntry(
                    term_id="step:PRODUCT_DEFINITION",
                    label="PRODUCT DEFINITION",
                    definition="STEP/AP242 product definition entity mapped to AP242 PartView",
                    ontology_prefix="step",
                    synonyms=["ProductDefinition", "View"],
                    related_terms=["step:PRODUCT_DEFINITION_FORMATION", "step:PRODUCT_DEFINITION_SHAPE", "ap242:PartView"],
                ).to_dict(),
                DataDictionaryEntry(
                    term_id="step:SHAPE_REPRESENTATION",
                    label="SHAPE REPRESENTATION",
                    definition="STEP/AP242 shape representation entity mapped to AP242 GeometricModel",
                    ontology_prefix="step",
                    synonyms=["ShapeRepresentation", "Geometry"],
                    related_terms=["step:PRODUCT_DEFINITION_SHAPE", "ap242:GeometricModel"],
                ).to_dict(),
            ]
        elif mapping_type.lower() == "windchill":
            return [
                DataDictionaryEntry(
                    term_id="windchill:PartMaster",
                    label="Part Master",
                    definition="Windchill PartMaster entity",
                    ontology_prefix="windchill",
                ).to_dict(),
                DataDictionaryEntry(
                    term_id="windchill:PartVersion",
                    label="Part Version",
                    definition="Windchill PartVersion entity",
                    ontology_prefix="windchill",
                ).to_dict(),
            ]
        return []
    
    @staticmethod
    def generate_vocabulary_mappings(mapping_type: str) -> List[Dict]:
        """Generate vocabulary mappings with relation types"""
        mappings = OntologyMapperService.get_mappings(mapping_type)
        vocabulary = []
        
        for mapping in mappings:
            vocabulary.append({
                "source_term": mapping["source_entity"],
                "source_label": mapping["source_entity"].split(":")[-1],
                "mapping_type": "mapsTo",
                "target_term": mapping["target_entity"],
                "target_label": mapping["target_entity"].split(":")[-1],
                "confidence": mapping["mapping_confidence"],
            })
        
        return vocabulary
    
    @staticmethod
    def get_mapping_stats(mapping_type: str) -> Dict[str, Any]:
        """Get statistics about a mapping"""
        mappings = OntologyMapperService.get_mappings(mapping_type)
        data_dict = OntologyMapperService.get_data_dictionary(mapping_type)
        vocabulary = OntologyMapperService.generate_vocabulary_mappings(mapping_type)
        
        return {
            "mapping_type": mapping_type,
            "total_entity_mappings": len(mappings),
            "total_terms": len(data_dict),
            "total_vocabulary_mappings": len(vocabulary),
            "mapping_confidence_breakdown": {
                "high": len([m for m in mappings if m["mapping_confidence"] == "high"]),
                "medium": len([m for m in mappings if m["mapping_confidence"] == "medium"]),
                "low": len([m for m in mappings if m["mapping_confidence"] == "low"]),
            },
            "last_updated": datetime.now().isoformat(),
        }
