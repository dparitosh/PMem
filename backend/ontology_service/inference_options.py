"""Strict input contract for non-mutating inference previews."""
RULES={'transitive_subclass','domain_range_typing','equivalence','disjointness','individual_type_closure'}
def validate_options(options):
    if options is None: options={}
    if not isinstance(options,dict):raise ValueError('Inference options must be an object')
    rules=options.get('rules',{})
    if not isinstance(rules,dict) or set(rules)-RULES or any(not isinstance(value,bool) for value in rules.values()):
        raise ValueError('Inference rules must contain supported boolean flags')
    limit=options.get('limit',250)
    if isinstance(limit,bool) or not isinstance(limit,int) or not 25<=limit<=1000:
        raise ValueError('Inference limit must be an integer between 25 and 1000')
    return rules,limit
