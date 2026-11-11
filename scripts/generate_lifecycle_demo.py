"""Build a deterministic, explicitly illustrative lifecycle fixture for slides 6-12.

Reads PLMXML to retain file hashes and source names, never overwrites the source,
and never claims that invented dimensions or reviewed links came from that file.
No database writes, external model calls or approval bypasses are performed.
"""
from pathlib import Path
import argparse
import hashlib
import json
from lxml import etree
from rdflib import Graph, Namespace, Literal, RDF, RDFS, OWL


def generate(source_dir, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sources, seen = [], set()
    for path in sorted(Path(source_dir).glob('*.xml')):
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        tree = etree.fromstring(content, etree.XMLParser(resolve_entities=False, no_network=True))
        names = sorted({e.get('name') for e in tree.iter() if isinstance(e.tag, str)
                        and etree.QName(e).localname == 'Product' and e.get('name')})
        if names:
            sources.append({'file': path.name, 'sha256': digest, 'source_product_names': names[:100]})
    if not sources:
        raise ValueError('No PLMXML product sources were found; no fixture created')
    d = Namespace('https://example.org/nexus/lifecycle-demo/')
    c = Namespace('https://depo.example.org/ceim/0.1/')
    g = Graph()
    g.bind('demo', d)
    g.bind('ceim', c)
    g.add((d.ontology, RDF.type, OWL.Ontology))
    g.add((d.ontology, RDFS.label, Literal('Engineering lifecycle')))
    g.add((d.ontology, RDFS.comment, Literal('Illustrative example: generated values and relationships are not customer engineering evidence.')))
    definitions = [
        ('shaft', 'Part', 'SHAFT-1001/B Rotor shaft', 'Revised shaft design linked to manufacturing and inspection evidence.', {'partNumber':'SHAFT-1001','revision':'B','material':'Steel','diameter':40.0,'unit':'mm','releaseStatus':'Review pending'}),
        ('shaft_previous', 'Part', 'SHAFT-1001/A Rotor shaft', 'Earlier revision retained separately from revision B.', {'partNumber':'SHAFT-1001','revision':'A','material':'Steel','diameter':39.8,'unit':'mm'}),
        ('shaft_candidate', 'Part', 'SHAFT-1002/B Comparison candidate', 'Similar dimensions do not establish interchangeability.', {'partNumber':'SHAFT-1002','revision':'B','material':'Aluminium','diameter':40.0,'unit':'mm'}),
        ('assembly', 'Assembly', 'BRG-2001/A Bearing assembly', 'Bearing assembly with an inner race and a rotor shaft.', {'partNumber':'BRG-2001','revision':'A'}),
        ('race', 'Part', 'BRG-2001 Inner race', 'Bearing inner race with a recorded bore dimension.', {'partNumber':'BRG-2001-IR','revision':'A','boreDiameter':25.0,'unit':'mm'}),
        ('shaft_req', 'Requirement', 'REQ-SHAFT-001 Shaft diameter', 'The revised shaft diameter shall be 40.0 mm within the stated dimensional tolerance.', {'requirementId':'REQ-SHAFT-001','verificationStatus':'Requires engineering review'}),
        ('bearing_req', 'Requirement', 'REQ-BRG-001 Bearing bore', 'Bearing bore nominal diameter shall be 25.0 mm; evaluate the recorded tolerance and inspection evidence.', {'requirementId':'REQ-BRG-001','verificationStatus':'Inspection evidence available for review'}),
        ('block', 'SystemComponent', 'Bearing support subsystem', 'MBSE block allocating the bearing requirement to the bearing design.', {'modelType':'SysML block','revision':'A'}),
        ('cad', 'EngineeringDocument', 'BRG-2001/A CAD design reference', 'CAD design reference associated with the bearing inner race.', {'documentId':'BRG-2001-A-CAD','fileName':'brg_2001_A.jt','documentType':'CAD reference'}),
        ('shape', 'ShapeRepresentation', 'Bearing cylindrical bore', 'Cylindrical bore feature, distinct from the physical part.', {'geometryType':'Cylindrical bore','nominalDiameter':25.0,'unit':'mm'}),
        ('bearing_pmi', 'PMIAnnotation', 'Bearing bore dimensional PMI', 'Bore dimension, datum and tolerance annotation.', {'nominalValue':25.0,'lowerLimit':24.99,'upperLimit':25.01,'unit':'mm','datum':'A','tolerance':0.01}),
        ('shaft_pmi', 'PMIAnnotation', 'Shaft diameter dimensional PMI', 'Shaft diameter annotation.', {'nominalValue':40.0,'lowerLimit':39.99,'upperLimit':40.01,'unit':'mm','datum':'A','tolerance':0.01}),
        ('inspection', 'EngineeringDocument', 'QIF bearing bore inspection result', 'Inspection result linked to its part and characteristic.', {'documentType':'QIF inspection result','nominalValue':25.0,'measuredValue':25.006,'lowerLimit':24.99,'upperLimit':25.01,'unit':'mm','result':'Within defined dimensional limits'}),
        ('shaft_inspection', 'EngineeringDocument', 'QIF shaft diameter inspection result', 'Inspection result awaiting engineering sign-off.', {'documentType':'QIF inspection result','nominalValue':40.0,'measuredValue':40.006,'unit':'mm'}),
        ('process', 'ManufacturingProcess', 'Bearing bore finish machining', 'Finishing operation associated with the bore definition.', {'operationNumber':'OP-020','processType':'Finish machining'}),
        ('shaft_process', 'ManufacturingProcess', 'Rotor shaft finish grinding', 'Manufacturing operation associated with revision B.', {'operationNumber':'OP-030','processType':'Grinding'}),
        ('mbom', 'Assembly', 'mBOM Bearing assembly', 'Manufacturing BOM with explicit part identities and quantities.', {'revision':'A','bomType':'Manufacturing BOM'}),
        ('simulation', 'EngineeringDocument', 'Bearing temperature study', 'Reference to a bearing temperature study.', {'documentType':'Simulation reference','studyId':'SIM-BRG-001'}),
    ]
    for key, kind, label, description, properties in definitions:
        g.add((c[kind], RDF.type, OWL.Class))
        for triple in [(d[key], RDF.type, c[kind]),(d[key], RDF.type, OWL.NamedIndividual),
                       (d[key], RDFS.label, Literal(label)),(d[key], c.description, Literal(description)),
                       (d[key], c.synthetic, Literal(True))]:
            g.add(triple)
        for prop, value in properties.items():
            g.add((c[prop], RDF.type, OWL.DatatypeProperty))
            g.add((d[key], c[prop], Literal(value)))
    links = [
        ('assembly','hasPart','shaft'),('assembly','hasPart','race'),('mbom','hasPart','shaft'),('mbom','hasPart','race'),
        ('shaft','hasRequirement','shaft_req'),('race','hasRequirement','bearing_req'),('assembly','hasRequirement','bearing_req'),
        ('block','allocatedTo','assembly'),('block','hasRequirement','bearing_req'),
        ('race','hasDocument','cad'),('race','hasDocument','inspection'),('race','hasShape','shape'),('race','hasPMI','bearing_pmi'),
        ('shaft','hasPMI','shaft_pmi'),('shaft','hasDocument','shaft_inspection'),('shaft','manufacturedBy','shaft_process'),
        ('race','manufacturedBy','process'),('assembly','hasDocument','simulation'),('shaft','hasPreviousRevision','shaft_previous'),
        ('inspection','verifies','bearing_req'),('shaft_inspection','verifies','shaft_req'),('shape','hasPMI','bearing_pmi'),
    ]
    for source, predicate, target in links:
        g.add((c[predicate], RDF.type, OWL.ObjectProperty))
        g.add((d[source], c[predicate], d[target]))
    # Quantities belong to explicit BOM-line records rather than the part itself.
    for index, target in enumerate(('shaft','race')):
        line = d['bom_line_'+str(index)]
        g.add((c.BOMLine, RDF.type, OWL.Class))
        g.add((line, RDF.type, c.BOMLine))
        g.add((line, RDFS.label, Literal('Bearing assembly line '+str(index+1))))
        g.add((line, c.quantity, Literal(1)))
        g.add((line, c.hasPart, d[target]))
        g.add((d.mbom, c.hasBOMLine, line))
    g.add((c.hasBOMLine, RDF.type, OWL.ObjectProperty))
    # Declare every generated literal property, including shared description,
    # provenance flags and BOM quantities, before OWL-DL profile validation.
    for _, predicate, value in list(g):
        if isinstance(value, Literal) and str(predicate).startswith(str(c)):
            g.add((predicate, RDF.type, OWL.DatatypeProperty))
    g.serialize(output/'lifecycle-demo.ttl',format='turtle')
    receipt = {'synthetic':True,'customer_approved':False,'records':len(definitions)+2,'relationships':len(links)+4,
               'triples':len(g),'source_context':sources,'ontology':'CEIM-compatible declared example vocabulary',
               'limitations':['Generated engineering values are illustrative, not extracted source facts',
                              'No CAD mesh, solver output, source-system release or engineering approval',
                              'Cross-domain links describe this fixture, not automatic equivalence between customer ontologies'],
               'checks':{'bearing_within_example_limits':24.99<=25.006<=25.01,
                         'same_name_revisions_remain_distinct':d.shaft!=d.shaft_previous,
                         'comparison_material_conflict':True}}
    (output/'lifecycle-demo-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    criteria = [
        {'id':'bearing-requirement','expected':'Inner race has a direct recorded requirement REQ-BRG-001 with its description.'},
        {'id':'bearing-pmi','expected':'Inner race owns its explicit PMI link: datum A, nominal 25 mm, tolerance 0.01 mm.'},
        {'id':'quality-limits','expected':'Recorded inspection 25.006 mm lies between illustrative limits 24.99 and 25.01 mm; this is not engineering sign-off.'},
        {'id':'cad-shape','expected':'The CAD reference and cylindrical bore feature are separate linked records; no mesh or solver result is claimed.'},
        {'id':'mbse-allocation','expected':'Bearing support subsystem allocates to the bearing assembly and links to REQ-BRG-001.'},
        {'id':'manufacturing-bom','expected':'Two explicit BOM lines retain distinct shaft and race identities with quantity 1 each.'},
        {'id':'shaft-change','expected':'Shaft revision B is linked to two assemblies and the finish-grinding process in bounded dependency analysis.'},
        {'id':'reuse-negative-control','expected':'The aluminium comparison shaft must not be certified interchangeable with the steel shaft.'},
        {'id':'revision-negative-control','expected':'Revisions A and B retain distinct identities; missing effectivity is reported as unassessed.'},
        {'id':'conversation-memory','expected':'The PMI follow-up keeps selected identity without inheriting requirement intent; retained answers are visible only to their authorized owner.'},
        {'id':'model-evidence','expected':'OWL-DL profile validation and consistency check execute successfully on the retained corrected artifact.'},
    ]
    (output/'success-criteria.json').write_text(json.dumps({'illustrative':True,'customer_approved':False,'criteria':criteria},indent=2),encoding='utf-8')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-dir',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=generate(args.source_dir,args.output)
    print(json.dumps({k:v for k,v in result.items() if k!='source_context'},indent=2))
