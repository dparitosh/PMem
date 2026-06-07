import sys
sys.path.insert(0, 'backend')

# ── 1. Import checks ──────────────────────────────────────────────────────────
from backend.Services.shacl_service import ShaclValidationService
print('ShaclValidationService: OK')
from backend.Services.owl_generation_service import OWLGenerationService
print('OWLGenerationService: OK')

# ── 2. OWL generation from small XMI ─────────────────────────────────────────
xmi = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<xmi:XMI xmlns:xmi="http://www.omg.org/XMI" xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">'
    '  <uml:Model xmi:id="_model" name="TestModel">'
    '    <packagedElement xmi:type="uml:Class" xmi:id="_cls1" name="Wheel"/>'
    '    <packagedElement xmi:type="uml:Class" xmi:id="_cls2" name="Axle"/>'
    '  </uml:Model>'
    '</xmi:XMI>'
).encode('utf-8')

ttl, meta = OWLGenerationService.generate_owl(xmi, 'test.xmi')
print(f'OWL lines  : {ttl.count(chr(10))}')
print(f'OWL format : {meta.get("format")}')
print(f'OWL errors : {meta.get("validation", {}).get("error_count", "n/a")}')

# ── 3. SHACL validation smoke test ───────────────────────────────────────────
import rdflib

data_ttl = """
@prefix ex: <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:Alice a ex:Person ; ex:name "Alice" .
"""

shacl_ttl = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://example.org/> .
ex:PersonShape a sh:NodeShape ;
    sh:targetClass ex:Person ;
    sh:property [ sh:path ex:name ; sh:datatype xsd:string ; sh:minCount 1 ] .
"""

data_graph = rdflib.Graph().parse(data=data_ttl, format='turtle')
svc = ShaclValidationService()
result = svc.validate_graph(data_graph, shacl_graph_str=shacl_ttl)
print(f'SHACL conforms: {result["conforms"]}')
print(f'SHACL violations: {result.get("violation_count", 0)}')
print('ALL OK')
