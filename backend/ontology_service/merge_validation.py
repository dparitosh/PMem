"""Conservative checks of explicit RDF declarations; no reasoner or IRI rewriting."""
RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
OWL = 'http://www.w3.org/2002/07/owl#'


def explicit_conflicts(triples):
    types, disjoint, equal, different = {}, set(), set(), set()
    for subject, predicate, obj in triples:
        subject, predicate, obj = str(subject), str(predicate), str(obj)
        if predicate == RDF+'type': types.setdefault(subject, set()).add(obj)
        elif predicate == OWL+'disjointWith': disjoint.add(tuple(sorted((subject, obj))))
        elif predicate == OWL+'sameAs': equal.add(tuple(sorted((subject, obj))))
        elif predicate == OWL+'differentFrom': different.add(tuple(sorted((subject, obj))))
    disjoint_index = {}
    for left, right in disjoint:
        disjoint_index.setdefault(left, set()).add(right)
        disjoint_index.setdefault(right, set()).add(left)
    issues=[]
    for subject, declared in sorted(types.items()):
        if {OWL+'ObjectProperty', OWL+'DatatypeProperty'} <= declared:
            issues.append({'kind':'incompatible_property_kinds','subject':subject,
                           'values':[OWL+'ObjectProperty', OWL+'DatatypeProperty']})
        if OWL+'Nothing' in declared:
            issues.append({'kind':'instance_of_nothing','subject':subject,'values':[OWL+'Nothing']})
        conflicts = {tuple(sorted((left, right))) for left in declared
                     for right in disjoint_index.get(left, set()) & declared}
        for left, right in sorted(conflicts):
            issues.append({'kind':'explicit_disjoint_membership','subject':subject,'values':[left,right]})
    for left,right in sorted(equal & different):
        issues.append({'kind':'explicit_identity_contradiction','subject':left,'values':[right]})
    for left,right in sorted(different):
        if left==right:
            issues.append({'kind':'self_difference','subject':left,'values':[right]})
    return issues
