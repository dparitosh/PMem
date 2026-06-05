r"""
SHACL Validator Service
Validates data against SHACL shapes derived from XSD schemas
Supports AP239 domain model validation for customer acceptance testing
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


@dataclass
class SHACLShape:
    """SHACL Shape definition"""
    shape_id: str
    target_class: str
    constraints: Dict[str, Any]
    description: str = ""


@dataclass
class ValidationResult:
    """SHACL Validation Result"""
    valid: bool
    conforms: bool
    result_severity: str  # info, warning, violation
    result_message: str
    focus_node: str
    result_path: str = ""
    shape_id: str = ""


class SHACLValidator:
    r"""
    SHACL Validator for AP239 domain model validation
    Uses XSD schemas as basis for SHACL constraint generation
    """
    
    def __init__(self, xsd_path: str = None):
        """
        Initialize SHACL validator with optional XSD file
        
        Args:
            xsd_path: Path to XSD schema file (AP239 Domain_model.xsd)
        """
        self.xsd_path = xsd_path or r"C:\Users\895428\Depo\SPLM_Folder\AP239\Domain_model.xsd"
        self.shapes: Dict[str, SHACLShape] = {}
        self.validation_results: List[ValidationResult] = []
        
        if Path(self.xsd_path).exists():
            self._load_shapes_from_xsd()
            logger.info(f"[OK] SHACL validator initialized with {len(self.shapes)} shapes from XSD")
        else:
            logger.warning(f"[WARN] XSD file not found: {self.xsd_path}")
            self._initialize_default_shapes()
    
    def _load_shapes_from_xsd(self):
        """Load SHACL shapes from XSD schema"""
        try:
            tree = ET.parse(self.xsd_path)
            root = tree.getroot()
            
            # Extract complex types as SHACL shapes
            namespaces = {'xsd': 'http://www.w3.org/2001/XMLSchema'}
            
            # Count elements and create shapes
            complex_types = root.findall('xsd:complexType', namespaces)
            if not complex_types:
                complex_types = root.findall('{http://www.w3.org/2001/XMLSchema}complexType')
            
            logger.info(f"[OK] Found {len(complex_types)} complex types in XSD")
            
            for ct in complex_types[:10]:  # Sample first 10
                type_name = ct.get('name', 'UnknownType')
                elements = ct.findall('.//{http://www.w3.org/2001/XMLSchema}element')
                
                constraints = {}
                for elem in elements:
                    elem_name = elem.get('name')
                    elem_type = elem.get('type')
                    if elem_name:
                        constraints[elem_name] = {
                            'type': elem_type or 'string',
                            'required': elem.get('minOccurs') != '0'
                        }
                
                self.shapes[type_name] = SHACLShape(
                    shape_id=f"ap239:{type_name}Shape",
                    target_class=f"ap239:{type_name}",
                    constraints=constraints,
                    description=f"SHACL shape for AP239 {type_name}"
                )
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to load XSD: {str(e)}")
            self._initialize_default_shapes()
    
    def _initialize_default_shapes(self):
        """Initialize default SHACL shapes for AP239 entities"""
        default_shapes = {
            "ElectronicAssembly": {
                "properties": ["assembly_id", "description", "voltage_rating"],
                "required": ["assembly_id"]
            },
            "CircuitNetwork": {
                "properties": ["circuit_id", "topology_type", "signal_frequency"],
                "required": ["circuit_id"]
            },
            "ComponentInstance": {
                "properties": ["component_id", "reference_designator", "manufacturer"],
                "required": ["component_id", "reference_designator"]
            },
            "SignalNet": {
                "properties": ["signal_name", "signal_type", "impedance"],
                "required": ["signal_name"]
            },
            "PowerDistribution": {
                "properties": ["voltage", "current_capacity", "distribution_points"],
                "required": ["voltage"]
            }
        }
        
        for entity_type, schema in default_shapes.items():
            self.shapes[entity_type] = SHACLShape(
                shape_id=f"ap239:{entity_type}Shape",
                target_class=f"ap239:{entity_type}",
                constraints={prop: {"required": prop in schema["required"]} 
                           for prop in schema["properties"]},
                description=f"Default SHACL shape for {entity_type}"
            )
    
    def validate_entity(self, entity_data: Dict[str, Any], entity_type: str) -> ValidationResult:
        """
        Validate entity against SHACL shape
        
        Args:
            entity_data: Entity data as dictionary
            entity_type: Type of entity (e.g., 'ElectronicAssembly')
        
        Returns:
            ValidationResult with conforms status
        """
        if entity_type not in self.shapes:
            return ValidationResult(
                valid=False,
                conforms=False,
                result_severity="warning",
                result_message=f"No SHACL shape defined for {entity_type}",
                focus_node=entity_data.get('id', 'unknown'),
                shape_id=f"ap239:{entity_type}Shape"
            )
        
        shape = self.shapes[entity_type]
        violations = []
        
        # Check required properties
        for prop_name, prop_config in shape.constraints.items():
            if prop_config.get("required") and prop_name not in entity_data:
                violations.append(f"Required property '{prop_name}' missing")
        
        # Validate property types if specified
        for prop_name, prop_value in entity_data.items():
            if prop_name in shape.constraints:
                prop_type = shape.constraints[prop_name].get("type")
                if prop_type and not self._validate_type(prop_value, prop_type):
                    violations.append(f"Property '{prop_name}' has invalid type")
        
        is_valid = len(violations) == 0
        result = ValidationResult(
            valid=is_valid,
            conforms=is_valid,
            result_severity="violation" if not is_valid else "info",
            result_message="; ".join(violations) if violations else "Validation passed",
            focus_node=entity_data.get('id', 'unknown'),
            shape_id=shape.shape_id
        )
        
        self.validation_results.append(result)
        return result
    
    def validate_batch(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate batch of entities
        
        Args:
            entities: List of entity dictionaries with 'type' field
        
        Returns:
            Validation report with statistics
        """
        total = len(entities)
        passed = 0
        failed = 0
        warnings = []
        
        for entity in entities:
            entity_type = entity.get('type', 'Unknown')
            result = self.validate_entity(entity, entity_type)
            
            if result.conforms:
                passed += 1
            else:
                failed += 1
                warnings.append({
                    'entity_id': entity.get('id'),
                    'type': entity_type,
                    'message': result.result_message
                })
        
        conforms = failed == 0
        
        return {
            'conforms': conforms,
            'conforms_percent': (passed / total * 100) if total > 0 else 0,
            'total_entities': total,
            'passed': passed,
            'failed': failed,
            'violations': warnings,
            'result_severity': 'info' if conforms else 'violation'
        }
    
    def get_validation_report(self) -> Dict[str, Any]:
        """Get detailed validation report"""
        total_results = len(self.validation_results)
        valid_results = sum(1 for r in self.validation_results if r.valid)
        
        return {
            'total_validations': total_results,
            'passed': valid_results,
            'failed': total_results - valid_results,
            'success_rate': (valid_results / total_results * 100) if total_results > 0 else 0,
            'shapes_available': len(self.shapes),
            'results': [asdict(r) for r in self.validation_results[:20]]  # First 20
        }
    
    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Validate value matches expected type"""
        type_map = {
            'string': str,
            'integer': int,
            'float': float,
            'boolean': bool
        }
        
        expected = type_map.get(expected_type.lower(), str)
        return isinstance(value, expected)
    
    def export_validation_report(self, filepath: str):
        """Export validation report to JSON"""
        report = self.get_validation_report()
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"[OK] Validation report exported to {filepath}")
