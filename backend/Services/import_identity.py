"""Preserve source identities separately from task-scoped generated identity."""
import json
import uuid
from defusedxml import ElementTree as ET

def attach_plmxml_identities(content, rows):
    root=ET.fromstring(content)
    by_id={row['id']:row for row in rows if row.get('id')}
    records=[]
    for owner in root.iter():
        for child in owner:
            if child.tag.split('}')[-1]=='ApplicationRef':
                records.append({'owner_xml_id':owner.get('id'), 'owner_element':owner.tag, 'retained_instance':owner.get('id') in by_id, 'attributes':dict(child.attrib)})
    for node in root.iter():
        row=by_id.get(node.get('id'))
        if row is None:continue
        row['source_xml_id']=node.get('id')
        row['source_element_name']=node.tag.split('}')[-1]
        row['source_element_namespace']=node.tag[1:].split('}')[0] if node.tag.startswith('{') else ''
        refs=[dict(child.attrib) for child in node if child.tag.split('}')[-1]=='ApplicationRef']
        if refs:
            row['source_application_refs_json']=json.dumps(refs,sort_keys=True,ensure_ascii=True)
        for key,value in node.attrib.items():
            local=key.split('}')[-1].lower()
            if local in {'uid','uuid','iri'}:row['source_'+local]=value
    return records

def stamp_instance_identity(row, task_id):
    if not row.get('import_row_key'):
        raise ValueError('Cannot assign instance identity without a retained row key')
    value=str(uuid.uuid5(uuid.NAMESPACE_URL,json.dumps([task_id,str(row['import_row_key'])],separators=(',',':'))))
    row['uuid']=value
    row['iri']='urn:pmem:instance:'+value
    row['identity_origin']='generated:task-and-row-key:uuid5'
