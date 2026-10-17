"""Retired direct-write ontology CLI; use the governed engineering workflow API."""
RETIRED_MESSAGE = (
    'Direct ontology writes from this CLI are retired. Use POST '
    '/api/v1/engineering-workflows for conversion/registration, then review and '
    'publish through the Ontology Service. See INSTALLATION.md.'
)


def create_ontology_in_neo4j(class_props):
    raise RuntimeError(RETIRED_MESSAGE)


def step_0_generate_ontology(plmxml_path):
    raise RuntimeError(RETIRED_MESSAGE)


if __name__ == '__main__':
    raise SystemExit(RETIRED_MESSAGE)
