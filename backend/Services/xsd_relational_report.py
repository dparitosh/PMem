"""Namespace-aware structural model and review-only PostgreSQL projection."""
from pathlib import Path
import hashlib
import io
import os
import re
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2001/XMLSchema'
X = '{'+NS+'}'
SQL_TYPES = {'string':'TEXT','normalizedString':'TEXT','token':'TEXT','ID':'TEXT','IDREF':'TEXT','anyURI':'TEXT',
 'boolean':'BOOLEAN','decimal':'NUMERIC','integer':'NUMERIC','nonNegativeInteger':'NUMERIC','positiveInteger':'NUMERIC',
 'int':'INTEGER','long':'BIGINT','short':'SMALLINT','byte':'SMALLINT','float':'REAL','double':'DOUBLE PRECISION',
 'date':'DATE','dateTime':'TIMESTAMPTZ','time':'TIME','base64Binary':'BYTEA','hexBinary':'BYTEA'}

def sql_name(value):
    clean = re.sub('[^a-z0-9_]', '_', value.lower()).strip('_')[:42] or 'entity'
    return clean+'_'+hashlib.sha256(value.encode()).hexdigest()[:12]

def build_xsd_relational_report(xsd_path):
    root_path = Path(xsd_path).resolve()
    boundary = root_path.parent
    contexts, schemas, seen = {}, [], set()
    total = 0
    def load(path, inherited=''):
        nonlocal total
        path = path.resolve()
        if not path.is_relative_to(boundary): raise ValueError('Schema dependency escapes the approved schema-set directory')
        if not path.is_file(): raise ValueError('Missing schema dependency: '+path.name)
        key = (path,inherited)
        if key in seen: return
        seen.add(key)
        if len(seen)>64: raise ValueError('Schema closure exceeds 64 documents')
        if path.stat().st_size > int(os.getenv('ONTOLOGY_AGENT_MAX_BYTES',str(25*1024*1024)))-total: raise ValueError('Schema closure exceeds byte limit')
        content=path.read_bytes();total+=len(content)
        if total>int(os.getenv('ONTOLOGY_AGENT_MAX_BYTES',str(25*1024*1024))): raise ValueError('Schema closure exceeds byte limit')
        if b'<!DOCTYPE' in content.replace(b'\x00',b'').upper() or b'<!ENTITY' in content.replace(b'\x00',b'').upper(): raise ValueError('DOCTYPE/entities are not permitted')
        scopes=[{}];pending={};root=None
        try:
            for event,item in ET.iterparse(io.BytesIO(content), events=('start-ns','start','end')):
                if event=='start-ns': pending[item[0]]=item[1]
                elif event=='start':
                    scope={**scopes[-1],**pending};pending={};scopes.append(scope)
                    if root is None: root=item
                    contexts[id(item)]=(scope,path,root.get('targetNamespace') or inherited)
                else: scopes.pop()
        except ET.ParseError as exc: raise ValueError('Malformed XSD: '+path.name) from exc
        if root is None or root.tag!=X+'schema': raise ValueError('Root must be xs:schema')
        namespace=root.get('targetNamespace') or inherited
        schemas.append((path,root,namespace))
        for child in root:
            if child.tag in {X+'include',X+'import',X+'redefine',X+'override'}:
                if child.tag in {X+'redefine',X+'override'}: raise ValueError('XSD redefine/override needs explicit schema compilation support')
                location=child.get('schemaLocation')
                if not location: raise ValueError('Schema import requires a local schemaLocation')
                if ':' in location or '\\' in location: raise ValueError('Remote/absolute schema dependencies are not permitted')
                load(path.parent/location, namespace if child.tag==X+'include' else '')
    load(root_path)
    formal_validation='not_available'
    try:
        from lxml import etree
    except ImportError:
        diagnostics_compiler=['Formal XSD grammar compilation requires the installed lxml runtime']
    else:
        try:
            parser=etree.XMLParser(resolve_entities=False, no_network=True)
            etree.XMLSchema(etree.parse(str(root_path),parser))
        except (etree.XMLSchemaParseError, etree.XMLSyntaxError) as exc:
            raise ValueError('XSD grammar compilation failed') from exc
        formal_validation='compiled'
        diagnostics_compiler=[]
    definitions={'complexType':{},'simpleType':{},'element':{},'attribute':{}}
    diagnostics=list(diagnostics_compiler);identities=[]
    def expanded(value,node):
        if not value: return ''
        scope,_,namespace=contexts[id(node)]
        if ':' in value:
            prefix,local=value.split(':',1)
            if prefix not in scope: raise ValueError('Unbound QName prefix: '+prefix)
            namespace=scope[prefix]
        else: local=value;namespace=scope.get('',namespace)
        return '{'+namespace+'}'+local
    for path,root,namespace in schemas:
        for node in root:
            kind=node.tag.removeprefix(X)
            if kind in definitions and node.get('name'):
                key='{'+namespace+'}'+node.get('name')
                if key in definitions[kind]: raise ValueError('Duplicate schema declaration: '+key)
                definitions[kind][key]=node
        for node in root.iter():
            if node.tag in {X+'key',X+'keyref',X+'unique'}:
                identities.append({'kind':node.tag.removeprefix(X),'name':expanded(node.get('name',''),node),
                    'selector':node.find(X+'selector').get('xpath','') if node.find(X+'selector') is not None else '',
                    'fields':[field.get('xpath','') for field in node.findall(X+'field')],
                    'refer':expanded(node.get('refer',''),node),'source':path.name,
                    'scope':'requires owner-path resolution before SQL key generation'})
                diagnostics.append('Identity XPath requires reviewed owner/key mapping')
    def datatype(node, trail=()):
        raw=node.get('type','');qname=expanded(raw,node) if raw else ''
        simple=node.find(X+'simpleType')
        if simple is None and qname in definitions['simpleType']: simple=definitions['simpleType'][qname]
        facets={}
        if simple is not None:
            restriction=simple.find(X+'restriction')
            if restriction is None:
                diagnostics.append('Simple list/union requires explicit materialization policy')
                return {'qname':qname,'resolved_type':'unsupported','sql_type':None,'facets':{}}
            base=expanded(restriction.get('base',''),restriction)
            if base in trail: raise ValueError('Circular simple-type inheritance')
            proxy=definitions['simpleType'].get(base)
            if proxy is not None:
                temporary=ET.Element(X+'element',{'type':restriction.get('base','')});contexts[id(temporary)]=contexts[id(restriction)]
                result=datatype(temporary,trail+(base,))
            else: result={'resolved_type':base,'sql_type':SQL_TYPES.get(base.removeprefix('{'+NS+'}')) if base.startswith('{'+NS+'}') else None,'facets':{}}
            for facet in restriction:
                name=facet.tag.removeprefix(X)
                if facet.get('value') is not None: facets.setdefault(name,[]).append(facet.get('value'))
            facets={**result.get('facets',{}),**facets};sql=result['sql_type'];resolved=result['resolved_type']
        else:
            resolved=qname;sql=SQL_TYPES.get(qname.removeprefix('{'+NS+'}')) if qname.startswith('{'+NS+'}') else None
        if sql=='NUMERIC' and 'totalDigits' in facets and 'fractionDigits' in facets:
            precision=int(facets['totalDigits'][0]);scale=int(facets.get('fractionDigits',['0'])[0])
            if not 1<=precision<=1000 or not 0<=scale<=precision: raise ValueError('Invalid decimal precision/scale')
            sql=f'NUMERIC({precision},{scale})'
        if sql is None: diagnostics.append('Unresolved/unsupported datatype: '+(qname or 'anonymous'))
        return {'xsd_type':raw,'qname':qname,'resolved_type':resolved,'sql_type':sql,'facets':facets}
    tables={};mapped=set()
    def table(identifier,source):
        if identifier not in tables:
            tables[identifier]={'name':identifier.rsplit('}',1)[-1], 'entity_id':identifier,'sql_name':sql_name(identifier),
                'source_kind':source,'columns':[],'relationships':[],'particles':[], 'primary_key_candidates':[], 'foreign_key_candidates':[], 'constraints':[]}
        return tables[identifier]
    def occurrences(node, minimum=1, maximum=1, choice=False):
        low=int(node.get('minOccurs','1'));high=node.get('maxOccurs','1')
        high=None if high=='unbounded' else int(high)
        if low<0 or (high is not None and high<low): raise ValueError('Invalid occurrence range')
        effective_min=0 if choice else minimum*low
        effective_max=None if maximum is None or high is None else maximum*high
        return {'min_occurs':effective_min,'max_occurs':'unbounded' if effective_max is None else effective_max,
                'required':effective_min>0,'repeating':effective_max is None or effective_max>1,
                'declared_min_occurs':low,'declared_max_occurs':'unbounded' if high is None else high}
    def map_type(node,identifier,trail=()):
        if identifier in mapped: return
        mapped.add(identifier);owner=table(identifier,'complexType')
        if node.get('mixed') == 'true': diagnostics.append('Mixed content requires text/order materialization policy')
        if identifier in trail: return
        for unsupported in node.iter():
            if unsupported.tag in {X+'any',X+'anyAttribute',X+'group',X+'attributeGroup',X+'assert',X+'alternative'}:
                diagnostics.append('Unsupported structural construct: '+unsupported.tag.removeprefix(X))
        content=node.find(X+'complexContent')
        if content is not None:
            extension=content.find(X+'extension')
            if extension is None: diagnostics.append('Complex-content restriction requires reviewed mapping')
            else:
                base=expanded(extension.get('base',''),extension)
                if base not in definitions['complexType'] or base in trail: raise ValueError('Unresolved/circular complex base: '+base)
                map_type(definitions['complexType'][base],base,trail+(identifier,))
                owner['columns'].extend(dict(column) for column in tables[base]['columns'])
                owner['relationships'].extend(dict(rel) for rel in tables[base]['relationships'])
        if node.find(X+'simpleContent') is not None:
            diagnostics.append('Simple-content value/attribute mapping requires review')
        def walk(parent,minimum=1,maximum=1,choice=False,path=''):
            for index,child in enumerate(parent):
                kind=child.tag.removeprefix(X);particle_path=path+'/'+kind+str(index)
                if kind in {'sequence','all','choice'}:
                    occ=occurrences(child,minimum,maximum,choice)
                    owner['particles'].append({'kind':kind,'path':particle_path,**occ})
                    is_choice=choice or kind=='choice'
                    if kind=='choice': diagnostics.append('Choice requires branch-aware load/constraint review')
                    if occ['repeating']: diagnostics.append('Repeated compositor requires group-instance materialization')
                    walk(child,occ['min_occurs'],None if occ['max_occurs']=='unbounded' else occ['max_occurs'],is_choice,particle_path)
                elif kind in {'complexContent','extension','restriction'}: walk(child,minimum,maximum,choice,particle_path)
                elif kind in {'element','attribute'}:
                    declaration=child
                    if child.get('ref'):
                        reference=expanded(child.get('ref'),child)
                        declaration=definitions[kind].get(reference)
                        if declaration is None: raise ValueError('Unresolved declaration: '+reference)
                    name=declaration.get('name')
                    if not name: raise ValueError('Declaration has no name')
                    occ=occurrences(child,minimum,maximum,choice) if kind=='element' else {'min_occurs':1 if child.get('use')=='required' else 0,'max_occurs':0 if child.get('use')=='prohibited' else 1,'required':child.get('use')=='required','repeating':False}
                    if occ['max_occurs']==0: continue
                    if declaration.get('substitutionGroup') or declaration.get('abstract')=='true': diagnostics.append('Abstract/substitution elements require explicit dispatch mapping')
                    qtype=expanded(declaration.get('type',''),declaration)
                    inline=declaration.find(X+'complexType');target=definitions['complexType'].get(qtype)
                    if inline is not None or target is not None:
                        if declaration.get('nillable') in {'true', '1'}: diagnostics.append('Nillable complex entities require explicit nil-state materialization')
                        target_id=identifier+'/'+name if inline is not None else qtype
                        map_type(inline if inline is not None else target,target_id,trail+(identifier,))
                        scope, origin, namespace=contexts[id(declaration)]
                        schema_root=next(root for path,root,ns in schemas if path==origin)
                        qualified=declaration in list(schema_root) or declaration.get('form',schema_root.get('elementFormDefault','unqualified'))=='qualified'
                        owner['relationships'].append({'name':name,'source_qname':('{'+namespace+'}' if qualified and namespace else '')+name,'target_entity_id':target_id,'target_table':tables[target_id]['name'],'particle_path':particle_path,**occ})
                    else:
                        column={'name':name,'nillable':declaration.get('nillable') in {'true', '1'},'nullable':not occ['required'] or declaration.get('nillable') in {'true', '1'},'default':declaration.get('default'),'fixed':declaration.get('fixed'),'sql_name':sql_name(kind+':'+name),'source_kind':kind,'particle_path':particle_path,'choice_branch':choice,**occ,**datatype(declaration)}
                        scope, origin, namespace=contexts[id(declaration)]
                        schema_root=next(root for path,root,ns in schemas if path==origin)
                        form_key='attributeFormDefault' if kind=='attribute' else 'elementFormDefault'
                        qualified=declaration in list(schema_root) or declaration.get('form',schema_root.get(form_key,'unqualified'))=='qualified'
                        column['source_qname']=('{'+namespace+'}' if qualified and namespace else '')+name
                        if occ['repeating']:
                            child_table=table(identifier+'/'+kind+':'+name,'repeated scalar')
                            child_table['parent_entity_id']=identifier;child_table['columns'].append({**column,'repeating':False,'name':'value'})
                            owner['relationships'].append({'name':name,'source_qname':column['source_qname'],'target_entity_id':child_table['entity_id'],'target_table':child_table['name'],**occ})
                        else: owner['columns'].append(column)
        walk(node)
    for identifier,node in definitions['complexType'].items(): map_type(node,identifier)
    roots=[]
    for identifier,node in definitions['element'].items():
        inline=node.find(X+'complexType');qtype=expanded(node.get('type',''),node)
        if inline is not None: map_type(inline,identifier)
        elif qtype in definitions['complexType']: identifier=qtype
        else:
            owner=table(identifier,'scalar root');owner['columns'].append({'name':'value','sql_name':'value','required':True,'nullable':node.get('nillable') in {'true', '1'},'nillable':node.get('nillable') in {'true', '1'},'default':node.get('default'),'fixed':node.get('fixed'),'repeating':False,**datatype(node)})
        if (inline is not None or qtype in definitions['complexType']) and node.get('nillable') in {'true', '1'}:
            diagnostics.append('Nillable complex entities require explicit nil-state materialization')
        source_qname=expanded(node.get('name'),node)
        roots.append({'name':node.get('name'),'entity_id':identifier,'source_qname':source_qname.removeprefix('{}')})
        if node.get('substitutionGroup') or node.get('abstract')=='true': diagnostics.append('Abstract/substitution roots require explicit dispatch mapping')
    for entity in tables.values():
        names=[column.get('sql_name') for column in entity['columns']]
        if len(names)!=len(set(names)): diagnostics.append('Duplicate inherited/property SQL column in '+entity['entity_id'])
        for column in entity['columns']:
            if column.get('fixed') is not None: diagnostics.append('Fixed values require source validation and SQL constraint review')
            if column.get('resolved_type') in {'{'+NS+'}ID','{'+NS+'}IDREF','{'+NS+'}IDREFS'}: diagnostics.append('Document-scoped XML identity requires explicit key mapping')
            if column.get('resolved_type') in {'{'+NS+'}dateTime','{'+NS+'}date','{'+NS+'}time'}: diagnostics.append('XML timezone/temporal mapping requires explicit policy')
            if column.get('facets'): diagnostics.append('Datatype facets require validated instance loading and constraint review')
    blockers=sorted(set(diagnostics))
    return {'contract':'xsd-structural-model-v2','status':'requires_review' if blockers else 'success',
        'source_file':root_path.name,'tables':list(tables.values()),'columns':[c for t in tables.values() for c in t['columns']],
        'roots':roots,'identity_constraints':identities,'namespaces':{str(p.relative_to(boundary)):ns for p,r,ns in schemas},
        'validation':{'xml_well_formed':True,'closure_resolved':True,'formal_xsd_validation':formal_validation},
        'ddl_blockers':blockers,'summary':{'tables':len(tables),'columns':sum(len(t['columns']) for t in tables.values()),'complex_types':len(definitions['complexType']),'simple_types':len(definitions['simpleType'])},
        'semantics':{'primary_key':'Surrogate instance IDs; source keys require owner-path review','occurrence':'Effective ranges plus particle paths; repeated groups/choices block automatic DDL'}}
