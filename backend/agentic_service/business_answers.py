"""Deterministic PLM answer presentation; never substitutes schema terms for instances."""




def cell(value):
    return str(value or 'Not recorded').replace('|',' / ').replace('\n',' ')[:220]


def render(items):
    output=[]
    for item in items:
        citation='[evidence:'+item['resource_id']+']'
        rows=item.get('rows') or []
        if item['intent']=='parts_with_pmi':
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
