"""Negotiate OSLC representations with specific ranges overriding wildcards."""
SUPPORTED = ('application/json', 'text/turtle', 'application/rdf+xml', 'application/ld+json')
def negotiate(header):
    ranges = []
    for part in header.split(','):
        fields = [item.strip().lower() for item in part.split(';')]
        quality = 1.0
        try:
            for field in fields[1:]:
                if field.startswith('q='): quality = float(field[2:])
        except ValueError: continue
        if not 0 <= quality <= 1: continue
        ranges.append((fields[0], quality))
    choices = []
    for order, media in enumerate(SUPPORTED):
        matches = [(2 if pattern == media else 1 if pattern == media.split('/')[0]+'/*' else 0, quality)
                   for pattern, quality in ranges if pattern in {media, media.split('/')[0]+'/*', '*/*'}]
        if matches:
            specificity = max(item[0] for item in matches)
            quality = max(q for specificity_value, q in matches if specificity_value == specificity)
            if quality > 0: choices.append((quality, specificity, -order, media))
    return max(choices)[3] if choices else None
