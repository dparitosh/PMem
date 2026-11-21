"""Assess versioned SWRL-subset rules against their retained ontology instances.

No caller-supplied facts, remote imports, model-generated measurements, graph
writes or approval transitions. The owning agent retains this typed observation.
"""
import hashlib
from collections import deque
from rdflib import URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL
from backend.Services.swrl_reasoning_service import SwrlAtom, SwrlRule, SwrlRuleService, SemanticFact, ApplicationRuleExecutor
from backend.depo_platform.ontology_semantics import subclass_type_resolver
from backend.depo_platform.shacl_core import check_shacl_core

SWRL='http://www.w3.org/2003/11/swrl#'
SWRLB='http://www.w3.org/2003/11/swrlb#'
VERSION='retained-inspection-rules-v1'


def digest(triple):
    return 'rdf:'+hashlib.sha256(' '.join(term.n3() for term in triple).encode()).hexdigest()


def rdf_list(graph,head,limit=32):
    result=[];seen=set()
    while head!=RDF.nil:
        if head in seen or len(result)>=limit:raise ValueError('Rule list is cyclic or exceeds its atom budget')
        seen.add(head)
        first=list(graph.objects(head,RDF.first));rest=list(graph.objects(head,RDF.rest))
        if len(first)!=1 or len(rest)!=1:raise ValueError('Rule list must have one first and rest')
        result.append(first[0]);head=rest[0]
    return result


def exactly_one(graph,subject,predicate):
    values=list(graph.objects(subject,URIRef(predicate)))
    if len(values)!=1:raise ValueError('Rule declaration requires exactly one '+predicate.rsplit('#',1)[-1])
    return values[0]


def retained_rule(graph,identity):
    def argument(term):
        if (term,RDF.type,URIRef(SWRL+'Variable')) in graph:
            return '?v'+hashlib.sha256(str(term).encode()).hexdigest()[:16]
        if not isinstance(term,(URIRef,Literal)):raise ValueError('Rule constants must be named IRIs or literals')
        return str(term)
    def atom(identity):
        kinds=set(graph.objects(identity,RDF.type))
        atom_kinds={kind for kind in kinds if str(kind).startswith(SWRL) and str(kind).endswith('Atom')}
        if len(atom_kinds)!=1:raise ValueError('Each retained atom requires exactly one SWRL atom kind')
        if URIRef(SWRL+'ClassAtom') in kinds:
            predicate=exactly_one(graph,identity,SWRL+'classPredicate')
            terms=[exactly_one(graph,identity,SWRL+'argument1')]
        elif kinds.intersection({URIRef(SWRL+'DatavaluedPropertyAtom'),URIRef(SWRL+'IndividualPropertyAtom')}):
            predicate=exactly_one(graph,identity,SWRL+'propertyPredicate')
            terms=[exactly_one(graph,identity,SWRL+'argument1'),exactly_one(graph,identity,SWRL+'argument2')]
        elif URIRef(SWRL+'BuiltinAtom') in kinds:
            predicate=exactly_one(graph,identity,SWRL+'builtin')
            terms=rdf_list(graph,exactly_one(graph,identity,SWRL+'arguments'),limit=3)
            if not isinstance(predicate,URIRef) or not str(predicate).startswith(SWRLB):raise ValueError('Only supported SWRL built-ins are allowed')
            predicate='swrlb:'+str(predicate)[len(SWRLB):]
        else:raise ValueError('Unsupported SWRL atom type')
        if not isinstance(predicate,URIRef) and not (isinstance(predicate,str) and predicate.startswith('swrlb:')):raise ValueError('A named predicate is required')
        return SwrlAtom(str(predicate),tuple(argument(term) for term in terms),tuple(i for i,term in enumerate(terms) if isinstance(term,Literal)))
    name=str(next(graph.objects(identity,RDFS.label),identity))
    version=exactly_one(graph,identity,str(OWL.versionInfo))
    if not isinstance(version,Literal) or not 1<=len(str(version).strip())<=80:raise ValueError('Rule requires a nonempty version literal up to 80 characters')
    rule=SwrlRule(str(identity),name,tuple(atom(item) for item in rdf_list(graph,exactly_one(graph,identity,SWRL+'body'))),
        tuple(atom(item) for item in rdf_list(graph,exactly_one(graph,identity,SWRL+'head'))),version=str(version))
    validation=SwrlRuleService.validate(rule)
    if not validation['supported']:raise ValueError('Retained rule uses unsupported or unsafe SWRL syntax')
    return rule


def source_facts(graph,rule):
    predicates={atom.predicate for atom in rule.body if not atom.is_builtin and len(atom.arguments)==2}
    classes={atom.predicate for atom in rule.body if not atom.is_builtin and len(atom.arguments)==1}
    resolve=subclass_type_resolver(graph)
    facts=[];evidence={}
    for triple in graph:
        subject,predicate,value=triple
        if str(predicate) in predicates or (predicate==RDF.type and str(value) in classes):
            identity=digest(triple)
            facts.append(SemanticFact(str(subject),str(predicate),str(value),identity,properties={'datatype':str(value.datatype or '') if isinstance(value,Literal) else ''}))
            evidence[identity]={'subject':str(subject),'predicate':str(predicate),'value':str(value),'asserted':True,
                'datatype':str(value.datatype or '') if isinstance(value,Literal) else None}
        if len(facts)>10000:raise ValueError('Rule fact scope exceeds 10000 statements; partition the source')
    # Entailed class facts retain the asserted type and exact hierarchy support.
    parents={}
    for child,parent in graph.subject_objects(RDFS.subClassOf):
        if isinstance(child,URIRef) and isinstance(parent,URIRef):parents.setdefault(child,[]).append(parent)
    path_cache={}
    def path(start,target):
        key=(start,target)
        if key not in path_cache:
            todo=deque([(start,[])]);seen={start};result=None
            while todo:
                current,trail=todo.popleft()
                if current==target:result=trail;break
                for parent in sorted(parents.get(current,[]),key=str):
                    if parent not in seen:seen.add(parent);todo.append((parent,[*trail,digest((current,RDFS.subClassOf,parent))]))
                if len(seen)>4096:raise ValueError('Rule class support exceeds its hierarchy budget')
            if result is None:raise ValueError('Entailed class support is unavailable')
            path_cache[key]=result
        return path_cache[key]
    inferred_seen=set()
    for subject,declared in graph.subject_objects(RDF.type):
        for ancestor in resolve({declared}):
            if str(ancestor) not in classes or (subject,RDF.type,ancestor) in graph:continue
            key=(subject,ancestor)
            if key in inferred_seen:continue
            inferred_seen.add(key);identity='rdfs:'+hashlib.sha256((str(subject)+'\0'+str(ancestor)).encode()).hexdigest()
            support=[digest((subject,RDF.type,declared)),*path(declared,ancestor)]
            facts.append(SemanticFact(str(subject),str(RDF.type),str(ancestor),identity,asserted=False,properties={'support_facts':support}))
            evidence[identity]={'subject':str(subject),'predicate':str(RDF.type),'value':str(ancestor),'asserted':False,'basis':'retained-rdfs-subclass-v1','support_facts':support}
            if len(facts)>10000:raise ValueError('Rule fact scope exceeds 10000 statements; partition the source')
    return facts,evidence


def assess(catalog,ontology_id,limit=50):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=200:raise ValueError('Assessment display limit must be between 1 and 200')
    metadata,content=catalog.read_artifact(ontology_id)
    if metadata.get('lifecycle_status')!='approved':raise ValueError('Choose an approved retained ontology rule release')
    fingerprint=hashlib.sha256(content).hexdigest()
    if metadata.get('artifact_id')!='sha256:'+fingerprint:raise ValueError('Retained source hash differs from its registered artifact')
    graph=catalog._parse_ontology(content,metadata.get('original_filename','ontology.ttl'),include_graph=True)['graph']
    identities=sorted(set(graph.subjects(RDF.type,URIRef(SWRL+'Imp'))),key=str)
    if len(identities)>16:raise ValueError('Rule release exceeds sixteen rules; partition the release')
    assessment_id='rules-'+hashlib.sha256((VERSION+'\0'+ontology_id+'\0'+fingerprint).encode()).hexdigest()
    result={'assessment_id':assessment_id,'ontology_id':ontology_id,'artifact_sha256':fingerprint,'engine_version':VERSION,
        'status':'no_rules','rules':[],'summary':{'rules':len(identities),'executed':0,'conclusions':0},
        'scope':'Exact retained ontology and named RDFS superclass closure; no external imports or graph writes',
        'publication_authorized':False,'owl_dl_consistency_established':False}
    if not identities:return result
    result['shacl']=check_shacl_core(graph,graph)
    if result['shacl']['status']!='conforms':result['status']='blocked';return result
    # Validate every rule before executing any, so a mixed unsupported release
    # cannot be mistaken for a completely assessed one.
    rules=[retained_rule(graph,identity) for identity in identities]
    for rule in rules:
        facts,evidence=source_facts(graph,rule)
        execution=ApplicationRuleExecutor.execute(rule,facts,assessment_id)
        if execution.get('status')!='success':raise ValueError('Rule execution did not complete; no complete assessment is available')
        conclusions=execution.get('inferred_facts',[])
        if result['summary']['conclusions']+len(conclusions)>10000:raise ValueError('Rule-release conclusions exceed the report budget')
        rows=[]
        for row in conclusions[:limit]:
            rows.append({**row,'subject_label':str(next(graph.objects(URIRef(row['subject']),RDFS.label),row['subject'])),
                'conclusion_label':str(next(graph.objects(URIRef(row['object']),RDFS.label),row['object'])),
                'inputs':[evidence[identity] for identity in row['sourceFacts']]})
        result['rules'].append({'rule_id':rule.rule_id,'name':rule.name,'version':rule.version,'status':execution['status'],
            'source_facts':len(facts),'conclusions':len(conclusions),'rows':rows,'truncated':len(conclusions)>limit})
        result['summary']['executed']+=1;result['summary']['conclusions']+=len(conclusions)
    result['status']='completed';return result
