"""Read-only examples; prompts request evidence rather than assert data exists."""
HOME_PROMPTS = [
    'Find product and assembly information with source references.',
    'Find requirement-to-model links and identify missing traceability evidence.',
    'Find MBSE functions, system components and their recorded relationships.',
    'Find quality and measurement evidence, and explain what is missing.',
    'Summarize saved AP242–QIF mapping reviews and distinguish proposals from published mappings.',
    'Find source provenance and lineage for ingested engineering data.',
]
PAGE_PROMPTS = {
    'catalog': [
        'Which data products are listed in the catalog, and what status is recorded?',
        'Show source and lineage evidence available for cataloged data.',
        'What catalog information is missing or cannot be verified?',
    ],
    'data-products': [
        'Summarize retained data products and their recorded publication status.',
        'What evidence is available for product versions and source provenance?',
        'Are analytics schemas, dimensions or KPIs documented in the available evidence?',
    ],
    'data-flow': [
        'Summarize retained processing jobs and their recorded status.',
        'Which returned jobs need attention, and what failure evidence is available?',
        'What validation or quality evidence is available from processing jobs?',
    ],
    'ontology': [
        'Explain the selected ontology’s classes, subclasses and properties using source evidence.',
        'Summarize saved mapping reviews, confidence evidence and unresolved conflicts.',
        'What evidence distinguishes proposed mappings from approved or published results?',
    ],
    'modeling': [
        'Find MBSE functions, system components and their recorded relationships.',
        'Find requirement-to-model links and identify missing traceability evidence.',
        'What provenance supports the available model relationships?',
    ],
    'requirements': [
        'Find requirements and their recorded links to models or product objects.',
        'What verification or satisfaction evidence is recorded for requirements?',
        'Identify missing traceability evidence without assuming a requirement is satisfied.',
    ],
    'qif': [
        'Find QIF measurement and inspection evidence with source references.',
        'Summarize saved AP242–QIF mapping reviews and unresolved mappings.',
        'What evidence connects measurements to product features?',
    ],
    'whereused': [
        'Find recorded assembly and component usage relationships.',
        'Show source evidence for available dependency links.',
        'Which dependency or impact questions cannot be answered from the retained evidence?',
    ],
    'data-quality': [
        'Find quality and measurement evidence, and explain what is missing.',
        'What recorded validation findings need review?',
        'Which source references support the available quality findings?',
    ],
}


def sample_queries(page='home'):
    page={'data-catalog':'catalog','recommendations':'quality'}.get(page,page)
    return {'queries':list(PAGE_PROMPTS.get(page, HOME_PROMPTS)),
            'data_available':None,'mode':'evidence-grounded','page':page}
