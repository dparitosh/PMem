"""Create deterministic, explicitly synthetic engineering evidence for local demos."""
from pathlib import Path
import argparse, json
from rdflib import Graph, Namespace, Literal, RDF, RDFS, OWL, XSD

def generate(output):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    g=Graph(); d=Namespace('https://example.org/nexus/synthetic-demo/'); c=Namespace('https://depo.example.org/ceim/0.1/')
    g.bind('demo',d); g.bind('ceim',c)
    g.add((d.ontology,RDF.type,OWL.Ontology)); g.add((d.ontology,RDFS.label,Literal('SYNTHETIC Nexus engineering demo — not customer evidence')))
    records=[('assembly','Assembly','SYN Pump Assembly','Synthetic pump assembly, revision B'),('housing','Part','SYN Housing P1001','Machined pump housing, revision B'),('alternative','Part','SYN Housing P1002','Comparison candidate; engineering approval required'),('shaft','Part','SYN Shaft P2001','Synthetic rotor shaft'),('req','Requirement','SYN REQ-001 Continuous operation','Operate continuously for eight hours; verification not demonstrated'),('block','SystemComponent','SYN Pump subsystem','MBSE subsystem allocation'),('cad','EngineeringDocument','SYN Housing CAD model','Synthetic design reference; no actual CAD file supplied'),('shape','ShapeRepresentation','SYN Housing shape','Illustrative cylindrical housing representation'),('pmi','PMIAnnotation','SYN Bore tolerance','Synthetic dimensional annotation'),('process','ManufacturingProcess','SYN Bore machining','Manufacturing activity for housing'),('simulation','EngineeringDocument','SYN Thermal simulation','Illustrative dataset reference; no computed result supplied')]
    for identity,kind,label,description in records:
        g.add((c[kind],RDF.type,OWL.Class)); g.add((d[identity],RDF.type,c[kind]));g.add((d[identity],RDF.type,OWL.NamedIndividual));g.add((d[identity],RDFS.label,Literal(label)));g.add((d[identity],c.description,Literal(description)));g.add((d[identity],c.synthetic,Literal(True)))
    for subject,predicate,target in [('assembly','hasPart','housing'),('assembly','hasPart','shaft'),('housing','hasRequirement','req'),('block','allocatedTo','housing'),('housing','hasDocument','cad'),('housing','hasShape','shape'),('housing','hasPMI','pmi'),('housing','manufacturedBy','process'),('housing','hasDocument','simulation')]:
        g.add((c[predicate],RDF.type,OWL.ObjectProperty));g.add((c[predicate],RDFS.label,Literal({'hasPart':'has component','hasRequirement':'has recorded requirement','hasDocument':'has design evidence','hasShape':'has shape representation','hasPMI':'has PMI','manufacturedBy':'has manufacturing activity','allocatedTo':'allocated to'}[predicate])));g.add((d[subject],c[predicate],d[target]))
    for identity in ('housing','alternative'):
        for key,value in {'partNumber':'SYN-P1001' if identity=='housing' else 'SYN-P1002','revision':'B','material':'Steel','diameter':40,'unit':'mm'}.items():g.add((c[key],RDF.type,OWL.DatatypeProperty));g.add((d[identity],c[key],Literal(value)))
    for key,value in {'value':0.02,'unit':'mm','datum':'A'}.items():g.add((c[key],RDF.type,OWL.DatatypeProperty));g.add((d.pmi,c[key],Literal(value)))
    g.serialize(output/'synthetic-engineering-demo.ttl',format='turtle')
    receipt={'synthetic':True,'customer_approved':False,'records':len(records),'triples':len(g),'business_associations':9,'kpis':[{'name':'Observed parts','formula':'count(Part records)','value':len(set(g.subjects(RDF.type,c.Part))),'unit':'records'},{'name':'Parts with recorded PMI links','formula':'count(distinct Part with hasPMI)','value':len(set(g.subjects(c.hasPMI,None))),'unit':'records'},{'name':'Recorded requirement links','formula':'count(hasRequirement)','value':len(list(g.triples((None,c.hasRequirement,None)))),'unit':'links'}],'limitations':['No real CAD file or simulation output','No requirement satisfaction claim','No effectivity or BOM completeness claim','No customer publication or database materialization performed']}
    (output/'synthetic-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);generate(p.parse_args().output)
