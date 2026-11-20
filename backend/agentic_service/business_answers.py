"""Deterministic PLM answer presentation; never substitutes schema terms for instances."""
import json
import re
from html import unescape
from html.parser import HTMLParser


class _BusinessText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, value):
        self.parts.append(value)
    def handle_starttag(self, tag, attrs):
        # Common XML property serialization stores business content in value.
        value = dict(attrs).get('value')
        if value:
            self.parts.append(value)


def business_text(value):
    if isinstance(value, str):
        text = unescape(value)
        if text.strip().startswith(('{', '[')):
            try:
                value = json.loads(text)
            except ValueError:
                return 'Structured source content; inspect its business properties'
        else:
            parser = _BusinessText()
            parser.feed(text)
            return ' '.join(' '.join(parser.parts).split())
    if isinstance(value, dict):
        # Retain actual values, not JSON keys or serialization identifiers.
        return '; '.join(business_text(value[key]) for key in ('name','description','value','unit','units') if key in value)
    if isinstance(value, list):
        return '; '.join(filter(None, (business_text(item) for item in value[:20])))
    return str(value) if value is not None else ''




def cell(value):
    return (business_text(value) or 'Not recorded').replace('|',' / ').replace('\n',' ')[:220]


def instance_details(properties):
    """Render supplied safe instance assertions without discarding zero/false values."""
    from backend.graph_service.search_evidence import BUSINESS_FIELDS
    descriptions = ('description', 'definition', 'comment', 'requirementText')
    parts = []
    seen = set()
    for key in descriptions:
        text = business_text(properties.get(key)).strip()
        if text and text not in seen:
            parts.append(cell(text))
            seen.add(text)
    for key in sorted(BUSINESS_FIELDS - set(descriptions) - {'name', 'title'}):
        text = business_text(properties.get(key)).strip()
        if text:
            label = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', key).replace('_', ' ').capitalize()
            parts.append(label + ': ' + cell(text))
    return '; '.join(parts)


def connection_label(edge):
    if edge.get('business_label'):
        return cell(edge['business_label'])
    # Human-readable recorded type, without pretending a missing vocabulary
    # mapping establishes business semantics or relationship direction.
    raw = edge.get('type') or 'Recorded connection'
    if '://' in raw or '#' in raw:
        return 'Recorded connection'
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw).replace('_',' ').capitalize()


def render_instance_connections(evidence):
    """Preserve directed record identity; separate reference lineage from business links."""
    records = {item['resource_id']: item for item in evidence if item.get('evidence_type') == 'graph_resource'}
    labels = {}
    for ordinal, (identifier, item) in enumerate(records.items(), 1):
        props = item.get('properties') or {}
        details = []
        for key in ('partNumber', 'part_number', 'revision'):
            value = business_text(props.get(key)).strip()
            if value and value not in details:
                details.append(value)
        label = cell(item.get('label'))
        same_name = sum(other.get('label') == item.get('label') for other in records.values()) > 1
        if same_name:
            # Ordinals distinguish retained identities without exposing database IDs.
            label += ' (' + ', '.join([*details, 'source record ' + str(ordinal)]) + ')'
        labels[identifier] = label
    business = []
    references = []
    seen = set()
    for edge in evidence:
        if edge.get('evidence_type') != 'graph_relationship':
            continue
        source, target = edge.get('source_id'), edge.get('target_id')
        if source not in records or target not in records:
            continue
        relation = str(edge.get('relationship') or '')
        alias = re.sub(r'[^A-Za-z0-9]', '', relation).upper()
        reference = alias in {'MASTERREF', 'MASTERREFERENCE', 'TRACETO', 'DERIVEDFROM'}
        normalized = 'MASTER_REFERENCE' if alias in {'MASTERREF', 'MASTERREFERENCE'} else relation
        key = (source, normalized, target)
        if key in seen:
            continue
        seen.add(key)
        if reference:
            meaning = 'References source master record' if normalized == 'MASTER_REFERENCE' else connection_label({'type': normalized})
        else:
            meaning = connection_label({'business_label': edge.get('business_label'), 'type': relation})
            # An unlabelled predicate is retained in evidence, not presented as a business conclusion.
            if meaning == 'Recorded connection':
                continue
        row = '| ' + ' | '.join([labels[source], meaning, labels[target],
              '[evidence:' + source + '] [evidence:' + target + ']']) + ' |'
        (references if reference else business).append(row)
    output = []
    for title, rows in (('Business relationships', business), ('Source-record references', references)):
        if rows:
            output.append(title + ':\n\n| From | Recorded relationship | To | Evidence |\n|---|---|---|---|\n' + '\n'.join(rows))
    return '\n\n'.join(output)


def render(items):
    output=[]
    for item in items:
        citation='[evidence:'+item['resource_id']+']'
        rows=item.get('rows') or []
        if item['intent'] == 'associated_requirements':
            output.append(('Found requirement records connected to the named business objects by recorded graph paths.' if rows else
                'I could not verify requirements associated with that business object in the selected scope. Schema definitions named “Specification” do not establish a product requirement. Check the product identity, published requirement instances and their links.')+' '+citation)
            if rows:
                output.append('| Business object | Requirement / specification | Recorded detail | Connection |\n|---|---|---|---|\n' + '\n'.join(
                    '| ' + ' | '.join([cell(row.get('subject')), cell(row.get('requirement')), cell(row.get('detail')),
                    cell(' → '.join(connection_label(edge) for edge in row.get('path',[])))]) + ' |' for row in rows))
            output.append('Each business-object/requirement pair appears once, with a shortest recorded path of up to three relationships. Connections do not by themselves prove satisfaction or compliance. '+citation)
        elif item['intent']=='parts_with_pmi':
            trace_only=bool(rows) and all(row.get('association_status')=='source_reference' for row in rows)
            output.append(('Only source-reference candidates were returned; part–PMI ownership is unverified.' if trace_only else 'Found recorded part–PMI associations in this bounded view.' if rows else
                'I could not verify which parts have PMI from the retained business links in this scope. PMI annotations alone do not establish which part owns them. Review the source part-to-annotation association and publish its approved mapping.')+' '+citation)
            if rows:
                output.append('| Part | PMI | Recorded values | Association | Source |\n|---|---|---|---|---|\n'+'\n'.join('| '+' | '.join(cell('Published model; see evidence' if k=='source' else row.get(k)) for k in ('part','pmi','characteristic','association','source'))+' |' for row in rows))
        else:
            output.append(('These are the retained product and assembly records in the selected scope.' if rows else 'No product or assembly instances were returned in this bounded scope. Ontology class definitions are not product records.')+' '+citation)
            if rows:
                output.append('| Product / assembly | Type | Source |\n|---|---|---|\n'+'\n'.join('| '+' | '.join(cell('Published model; see evidence' if k=='source' else row.get(k)) for k in ('name','kind','source'))+' |' for row in rows))
        output.append('Coverage: up to 20 rows; source references are not verified semantic ownership. Open evidence for retained identities and paths. '+citation)
    return '\n\n'.join(output)
