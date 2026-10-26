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


def connection_label(edge):
    if edge.get('business_label'):
        return cell(edge['business_label'])
    # Human-readable recorded type, without pretending a missing vocabulary
    # mapping establishes business semantics or relationship direction.
    raw = edge.get('type') or 'Recorded connection'
    if '://' in raw or '#' in raw:
        return 'Recorded connection'
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw).replace('_',' ').capitalize()


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
            output.append('Connections show recorded paths of up to three relationships; they do not by themselves prove satisfaction or compliance. '+citation)
        elif item['intent']=='parts_with_pmi':
            trace_only=bool(rows) and all(row.get('association_status')=='source_reference' for row in rows)
            output.append(('Only source-reference candidates were returned; part–PMI ownership is unverified.' if trace_only else 'Found recorded part–PMI associations in this bounded view.' if rows else
                'I could not verify which parts have PMI from the retained business links in this scope. PMI annotations alone do not establish which part owns them. Review the source part-to-annotation association and publish its approved mapping.')+' '+citation)
            if rows:
                output.append('| Part | PMI | Association | Source |\n|---|---|---|---|\n'+'\n'.join('| '+' | '.join(cell('Published model; see evidence' if k=='source' else row.get(k)) for k in ('part','pmi','association','source'))+' |' for row in rows))
        else:
            output.append(('These are the retained product and assembly records in the selected scope.' if rows else 'No product or assembly instances were returned in this bounded scope. Ontology class definitions are not product records.')+' '+citation)
            if rows:
                output.append('| Product / assembly | Type | Source |\n|---|---|---|\n'+'\n'.join('| '+' | '.join(cell('Published model; see evidence' if k=='source' else row.get(k)) for k in ('name','kind','source'))+' |' for row in rows))
        output.append('Coverage: up to 20 rows; source references are not verified semantic ownership. Open evidence for retained identities and paths. '+citation)
    return '\n\n'.join(output)
