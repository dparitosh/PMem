"""Bounded credential redaction and reproducible prompt identity."""
import json
import hashlib
import os
import re

SECRET_KEYS = {'authorization', 'api_key', 'admin_api_key', 'password', 'secret', 'access_token', 'approval_token', 'subscription_key', 'ocp_apim_subscription_key', 'depo_database_url', 'database_url', 'neo4j_pass'}
SECRET_KEYS |= {'refresh_token', 'client_secret', 'connection_string'}
SECRET_KEYS |= {'token', 'private_key', 'credential', 'credentials'}
SECRET_COMPACT_KEYS = {key.replace('_', '') for key in SECRET_KEYS}


def secret_key(key):
    key = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(key)).lower().replace('-', '_')
    return key.replace('_', '') in SECRET_COMPACT_KEYS or key.endswith(('_token', '_api_key', '_password', '_secret', '_connection_string', '_pass'))


def protect(value):
    """Redact named credentials and known configured secrets before inference/storage."""
    secrets = sorted({item for key, item in os.environ.items() if secret_key(key) and len(item) >= 8}, key=len, reverse=True)
    def walk(item):
        if isinstance(item, dict):
            return {key: '[REDACTED]' if secret_key(key) else walk(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [walk(child) for child in item]
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, '[REDACTED]')
            item = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*', 'Bearer [REDACTED]', item)
            item = re.sub(r'''(["'])([A-Za-z][A-Za-z0-9_-]*)\1(\s*:\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''',
                          lambda match: match[1] + match[2] + match[1] + match[3] + '"[REDACTED]"'
                          if secret_key(match[2]) else match[0], item)
            item = re.sub(r'(?i)(\b(?:[a-z0-9_]*(?:api_key|password|secret|token)|authorization)\s*[:=]\s*)([^\s,;]+)', r'\1[REDACTED]', item)
            item = re.sub(r'\b([A-Za-z][A-Za-z0-9_-]*)(\s*[:=]\s*)([^\s,;]+)',
                          lambda match: match[1] + match[2] + '[REDACTED]' if secret_key(match[1]) else match[0], item)
            item = re.sub(r'(\w+://[^:/\s]+:)([^@/\s]+)(@)', r'\1[REDACTED]\3', item)
            return item
        return item
    return walk(value)


def protect_schema(schema, sensitive=False):
    """Keep schema keywords/property names intact; redact annotation values.

    The original schema remains the execution validator's authority, never this
    model-visible projection. A property called password must remain a schema.
    """
    if isinstance(schema, dict):
        result = {}
        for key, value in schema.items():
            if sensitive and key in {'default', 'examples', 'example', 'enum', 'const', 'description', 'title'}:
                continue
            if key == 'properties' and isinstance(value, dict):
                result[key] = {name: protect_schema(definition, secret_key(name)) for name, definition in value.items()}
            else:
                result[key] = protect(value) if key in {'default', 'examples', 'example'} else protect_schema(value, sensitive)
        return result
    if isinstance(schema, list):
        return [protect_schema(value, sensitive) for value in schema]
    return protect(schema)


def citation_targets(item):
    """Citation aliases of one projected record, never arbitrary nested IDs."""
    if not isinstance(item, dict):
        return []
    properties = item.get('properties') or {}
    values = [item.get('resource_id'), item.get('elementId'), item.get('iri'),
              properties.get('iri') if isinstance(properties, dict) else None, item.get('source_id')]
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and 0 < len(value) <= 2000))


def prompt_identity(system):
    return {'system_prompt_sha256': hashlib.sha256(system.encode('utf-8')).hexdigest()}


def evidence_ids(evidence):
    if isinstance(evidence, list):
        records = evidence
    elif isinstance(evidence, dict):
        records = [evidence] + [item for key in ('nodes', 'evidence')
                                for item in (evidence[key] if isinstance(evidence.get(key), list) else [])]
    else:
        records = []
    targets = [citation_targets(item) for item in records]
    # Reserve the owning record of every retained item before optional aliases.
    primary = [values[0] for values in targets if values]
    aliases = [value for values in targets for value in values[1:]]
    return list(dict.fromkeys(primary + aliases))[:200]


def validate_summary(text, identifiers):
    allowed = set(identifiers)
    def canonical_citation(match):
        value = match.group(1).strip()
        if value in allowed:
            return '[evidence:' + value + ']'
        values = [item.strip() for item in re.split(r'[,;]', value)]
        if len(values) > 1 and all(item and item in allowed for item in values):
            return ' '.join('[evidence:' + item + ']' for item in values)
        return match.group(0)
    text = re.sub(r'\[evidence:([^\]\n]+)\]', canonical_citation, text)
    if re.search(r'<\/?[A-Za-z_][\w:.-]*(?:\s[^<>]*|\s*)/?>|```\s*(?:xml|json)\b|\b(?:minOccurs|maxOccurs)\s*=', text, re.I) or text.lstrip().startswith(('{','[')) and not text.lstrip().startswith('[evidence:'):
        raise ValueError('Companion business answers must not contain XML, JSON or schema serialization')
    citations = re.findall(r'\[evidence:([^\]\n]+)\]', text)
    if not identifiers or not citations or any(value not in identifiers for value in citations):
        raise ValueError('Companion summary requires citations to supplied evidence identifiers')
    for line in text.splitlines():
        if line.strip().startswith('|') and not re.fullmatch(r'[| :\-]+',line.strip()) and not re.search(r'\[evidence:([^\]\n]+)\]',line):
            # A header is non-factual; data rows must cite their supporting record.
            lines=text.splitlines();index=lines.index(line)
            if index+1>=len(lines) or not re.fullmatch(r'[| :\-]+',lines[index+1].strip()):
                raise ValueError('Every summary table row requires evidence citations')
    # Match the supported UI grammar, including numbered/Unicode list items and
    # separately rendered name:value facts. Tables are checked row by row above.
    for paragraph in re.split(r'\n\s*\n|\n(?=\s*(?:[-*•◦▪]\s|\d+[.)]\s|[A-Za-z][A-Za-z0-9 _/-]{1,36}:\s|#{1,3}\s|\|))',text):
        if not paragraph.strip() or re.fullmatch(r'\s*#{1,3}\s+[^\n]+',paragraph):continue
        if all(line.strip().startswith('|') for line in paragraph.splitlines() if line.strip()):continue
        if re.fullmatch(r'\s*---+\s*', paragraph):continue
        if not re.search(r'\[evidence:([^\]\n]+)\]',paragraph):
            raise ValueError('Every summary paragraph or list item requires evidence citations')
    return text


def compact_evidence_citations(evidence, identifiers):
    """Short model-facing IDs retain a one-to-one link to authoritative citations."""
    prefix = 'C'
    while any(prefix + str(index + 1) in identifiers for index in range(len(identifiers))):
        prefix = 'C_' + prefix
    aliases = {prefix + str(index + 1): value for index, value in enumerate(identifiers)}
    reverse = {value: alias for alias, value in aliases.items()}
    def rewrite(value):
        if isinstance(value, str):
            return reverse.get(value, value)
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        return value
    return rewrite(evidence), aliases


def expand_evidence_citations(text, aliases):
    return re.sub(r'\[evidence:([^\]\n]+)\]', lambda match: '[evidence:' + aliases.get(match.group(1), match.group(1)) + ']', text)


def render_summary_findings(content, identifiers):
    """Render internal model JSON only after checking every finding's source IDs."""
    value = json.loads(content)
    if not isinstance(value, dict) or set(value) != {'findings'}:
        raise ValueError('Invalid companion findings envelope')
    findings = value['findings']
    if not isinstance(findings, list) or not 1 <= len(findings) <= 6:
        raise ValueError('Companion findings must contain one to six records')
    rows = ['| Business finding | Evidence |', '| --- | --- |']
    allowed = set(identifiers)
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {'statement', 'evidence_ids'}:
            raise ValueError('Invalid companion finding')
        statement, sources = finding['statement'], finding['evidence_ids']
        if not isinstance(statement, str) or not statement.strip() or len(statement) > 600 or '\n' in statement or '\r' in statement or '[evidence:' in statement:
            raise ValueError('Invalid companion finding statement')
        if not isinstance(sources, list) or not 1 <= len(sources) <= 8 or any(not isinstance(source, str) or source not in allowed for source in sources):
            raise ValueError('Companion finding requires supplied evidence identifiers')
        citations = ' '.join('[evidence:' + source + ']' for source in dict.fromkeys(sources))
        rows.append('| ' + statement.strip().replace('|', '\\|') + ' | ' + citations + ' |')
    return validate_summary('\n'.join(rows), identifiers)


def business_fact_candidates(evidence):
    """Known resource facts for low-cost model relevance selection, not invention."""
    from backend.agentic_service.business_answers import cell, business_text, connection_label
    facts = []
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict) or item.get('evidence_type') != 'business_answer' or not item.get('resource_id'):
            continue
        for row in (item.get('rows') or [])[:20]:
            if not isinstance(row, dict): continue
            # Deterministic typed findings cannot be freely reinterpreted by
            # a model as an association to a different named product.
            details = [cell(value) for key, value in row.items() if key in {'name','kind','subject','requirement','detail','part','pmi','association'} and value is not None and business_text(value).strip()]
            if details:
                facts.append({'fact_id':'F'+str(len(facts)+1), 'statement':'Recorded business evidence: '+'; '.join(details)[:540]+'.', 'evidence_ids':[item['resource_id']]})
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict) or item.get('evidence_type') != 'graph_resource' or not item.get('label') or not item.get('resource_id'):
            continue
        props = item.get('properties') or {}
        description = props.get('description') or props.get('definition') or props.get('comment')
        details = []
        if business_text(description).strip():
            details.append('Description: ' + cell(description))
        for key, label in {'partNumber':'Part number', 'part_number':'Part number', 'revision':'Revision', 'material':'Material', 'mass':'Mass', 'weight':'Weight', 'diameter':'Diameter', 'length':'Length', 'tolerance':'Tolerance', 'status':'Status', 'quantity':'Quantity', 'datum':'Datum', 'nominal':'Nominal', 'upperTolerance':'Upper tolerance', 'lowerTolerance':'Lower tolerance', 'shape':'Shape', 'geometry':'Geometry', 'representation':'Representation', 'requirementText':'Requirement', 'identifier':'Identifier'}.items():
            if props.get(key) is not None and business_text(props[key]).strip():
                rendered_value = cell(props[key])
                if key in {'mass','weight','diameter','length','tolerance','nominal','upperTolerance','lowerTolerance'} and (props.get('unit') or props.get('units')):
                    rendered_value += ' ' + cell(props.get('unit') or props.get('units'))
                details.append(label + ': ' + rendered_value)
        if not details and item.get('kind'):
            details.append('Recorded type: ' + cell(item['kind']))
        if not details and props.get('value') is None:
            continue
        statement = cell(item['label']) + ' — ' + '; '.join(details) + '.'
        if props.get('value') is not None:
            statement += ' Recorded value: ' + cell(props['value'])
            unit = props.get('unit') or props.get('units')
            if unit: statement += ' ' + cell(unit)
            statement += '.'
        facts.append({'fact_id': 'F' + str(len(facts) + 1), 'statement': statement[:600], 'evidence_ids': [item['resource_id']]})
        if len(facts) == 40: break
    resources = {item['resource_id']:item for item in evidence if isinstance(item, dict) and item.get('evidence_type') == 'graph_resource' and item.get('resource_id') and item.get('label')} if isinstance(evidence, list) else {}
    for edge in evidence if isinstance(evidence, list) else []:
        if not isinstance(edge, dict) or edge.get('evidence_type') != 'graph_relationship' or not edge.get('resource_id'):
            continue
        source, target = resources.get(edge.get('source_id')), resources.get(edge.get('target_id'))
        if not source or not target or len(facts) >= 40:
            continue
        label = connection_label({'business_label':edge.get('business_label'), 'type':edge.get('relationship')})
        statement = cell(source['label']) + ' → ' + label + ' → ' + cell(target['label']) + ' (recorded connection; this alone does not establish ownership, assembly usage or satisfaction).'
        facts.append({'fact_id':'F'+str(len(facts)+1), 'statement':statement[:600], 'evidence_ids':[edge['resource_id'], edge['source_id'], edge['target_id']]})
    return facts


def render_selected_facts(content, facts):
    selected = json.loads(content)
    if not isinstance(selected, dict) or set(selected) != {'fact_ids'} or not isinstance(selected['fact_ids'], list) or not 1 <= len(selected['fact_ids']) <= 6:
        raise ValueError('Invalid companion fact selection')
    known = {fact['fact_id']: fact for fact in facts}
    if any(not isinstance(value, str) or value not in known for value in selected['fact_ids']):
        raise ValueError('Companion selected an unknown fact')
    findings = [{'statement': known[key]['statement'], 'evidence_ids': known[key]['evidence_ids']} for key in dict.fromkeys(selected['fact_ids'])]
    identifiers = list(dict.fromkeys(source for fact in facts for source in fact['evidence_ids']))
    return render_summary_findings(json.dumps({'findings': findings}), identifiers)
