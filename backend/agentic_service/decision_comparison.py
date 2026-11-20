"""Typed checks of explicit numeric criteria against agent-retrieved alternatives."""
import re
from decimal import Decimal, InvalidOperation

OPERATORS={'<=':lambda a,b:a<=b,'>=':lambda a,b:a>=b,'<':lambda a,b:a<b,'>':lambda a,b:a>b,'=':lambda a,b:a==b}
FIELDS={'temperature':'temperature','vibration':'vibration','speed':'speed','outerdiameter':'outerDiameter','leadtime':'leadTime'}
LABELS={'temperature':'temperature','vibration':'vibration','speed':'speed','outerDiameter':'outer diameter','leadTime':'lead time'}
UNITS={'degc':'degC','c':'degC','mm/srms':'mm/s RMS','rpm':'rpm','mm':'mm','day':'day','days':'day'}

def number(value):
    if isinstance(value,bool):raise ValueError('Boolean is not a measurement')
    try:result=Decimal(str(value))
    except (InvalidOperation,TypeError):raise ValueError('Measurement is not numeric')
    if not result.is_finite():raise ValueError('Measurement is not finite')
    return result

def unit(value):return UNITS.get(re.sub(r'\s+','',str(value)).lower())

def evaluate(question,evidence):
    # Require a complete, explicitly stated supported comparison clause. Unknown
    # fields/units/operators hold the result rather than silently ignoring them.
    criteria=[]
    pattern=r'([A-Za-z][A-Za-z ]{0,50}?)\s*(<=|>=|<|>|=)\s*(-?\d+(?:\.\d+)?)\s*([^,;.<>=]+?)(?=\s+and\s+[A-Za-z ]+\s*[<>=]|[,;.]|$)'
    for match in re.finditer(pattern,question):
        name=re.sub(r'^(?:and |require )+','',match[1].strip(),flags=re.I)
        field=FIELDS.get(name.replace(' ','').lower())
        supplied_unit=unit(re.split(r'\band\b',match[4],maxsplit=1,flags=re.I)[0].strip())
        if not field or not supplied_unit:raise ValueError('Use supported numeric property names and explicit units for each criterion')
        if any(row['property']==field for row in criteria):raise ValueError('Supply one unambiguous limit for each property')
        criteria.append({'property':field,'operator':match[2],'limit':str(number(match[3])),'unit':supplied_unit})
    if not criteria or len(criteria)!=len(re.findall(r'<=|>=|(?<![<>=])[<>=](?![=])',question)):
        raise ValueError('State explicit numeric comparison criteria with units')
    rows=evidence.get('comparison_rows')
    if not isinstance(rows,list) or not rows:raise ValueError('No recorded alternatives with linked evaluations were returned')
    outcomes=[]
    for row in rows:
        values=row.get('option_values') or {};tests=row.get('evaluations') or []
        checks=[]
        for criterion in criteria:
            field=criterion['property'];readings=[]
            own=values.get(field)
            if own is not None:readings.append((own,values.get(field+'_unit'),values.get('externalId') or row['option_record_id']))
            readings.extend((test.get('values',{}).get(field),test.get('values',{}).get(field+'_unit'),test.get('values',{}).get('externalId') or test.get('record_id')) for test in tests if test.get('values',{}).get(field) is not None)
            check={**criterion,'status':'unknown','values':[],'sources':[]}
            try:
                if not readings or any(unit(u)!=criterion['unit'] for _,u,_ in readings):raise ValueError('Missing value or incompatible unit')
                distinct={number(v) for v,_,_ in readings}
                if len(distinct)!=1:raise ValueError('Conflicting evaluation values')
                value=next(iter(distinct));check.update(status='met' if OPERATORS[criterion['operator']](value,number(criterion['limit'])) else 'not_met',values=[str(value)],sources=list(dict.fromkeys(source for _,_,source in readings)))
            except ValueError:pass
            checks.append(check)
        try:cost=str(number(values.get('estimatedIncrementalCost')))
        except ValueError:cost=None
        outcomes.append({'name':row.get('option'),'record_id':row['option_record_id'],'external_id':values.get('externalId'),
            'checks':checks,'feasible':all(c['status']=='met' for c in checks),'cost':cost,'cost_unit':values.get('cost_unit'),
            'evaluation_ids':[test.get('values',{}).get('externalId') or test.get('record_id') for test in tests]})
    if any(not any(c['status']=='not_met' for c in row['checks']) and any(c['status']=='unknown' for c in row['checks']) for row in outcomes):
        raise ValueError('A potentially feasible alternative has unresolved criteria')
    eligible=[row for row in outcomes if row['feasible']]
    if not re.search(r'lowest.*(?:cost|incremental)|minimi[sz]e.*cost',question,re.I):raise ValueError('State the lowest-cost objective explicitly')
    if not eligible or any(row['cost'] is None or not row['cost_unit'] for row in eligible) or len({row['cost_unit'] for row in eligible})!=1:
        raise ValueError('No fully evidenced feasible lowest-cost alternative can be established')
    cheapest=min(number(row['cost']) for row in eligible)
    preferred=[row for row in eligible if number(row['cost'])==cheapest]
    chosen='; '.join(row['name'] for row in preferred)
    summary=f'Recommend {chosen} for engineering review. '
    if len(preferred)>1:summary+='These alternatives tie for the lowest recorded incremental cost. '
    best=preferred[0]
    summary+='All '+str(len(criteria))+' stated criteria are met: '+', '.join(LABELS[c['property']]+' '+c['values'][0]+' '+c['unit'] for c in best['checks'])+'. '
    summary+='Incremental cost: '+best['cost']+' '+best['cost_unit']+'. Evidence: '+', '.join([best['external_id'] or best['record_id'],*best['evaluation_ids']])+'. '
    for row in outcomes:
        if row in preferred:continue
        failed=[c for c in row['checks'] if c['status']!='met']
        summary+='\n\n'+row['name']+': '+('; '.join(LABELS[c['property']]+' '+('/'.join(c['values'])+' '+c['unit'] if c['values'] else 'not established')+' against '+c['operator']+' '+c['limit']+' '+c['unit'] for c in failed) if failed else 'meets criteria, with a higher recorded cost')+'. Incremental cost: '+(row['cost']+' '+str(row['cost_unit']) if row['cost'] is not None else 'not established')+'. '
    return {'business_summary':summary.strip(),'comparison':{'criteria':criteria,'alternatives':outcomes,'preferred_record_ids':[row['record_id'] for row in preferred],'method':'typed_numeric_constraints','advisory_only':True}}
