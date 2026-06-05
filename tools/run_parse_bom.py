#!/usr/bin/env python3
"""Run the enhanced parse_xsd on the BOM XSD and write source TTL."""
from pathlib import Path
import sys
import json


BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

try:
    from backend.Services.unified_data_import import FileFormatDetector
    from backend.Services.owl_generation_service import OWLGenerationService
except Exception as e:
    print(f"Failed to import parse_xsd: {e}")
    raise


def main():
    xsd_rel = Path("data/business_object_models/managed_model_based_3d_engineering/bom.xsd")
    xsd_path = BASE / xsd_rel
    if not xsd_path.exists():
        print(f"XSD file not found: {xsd_path}")
        sys.exit(2)

    print(f"Parsing: {xsd_path}")
    content = xsd_path.read_bytes()
    rows, stats = FileFormatDetector.parse_xsd(content)

    out_dir = BASE / 'data' / 'parser_outputs'
    out_dir.mkdir(parents=True, exist_ok=True)
    ttl_path = out_dir / 'bom_source.ttl'

    ttl = stats.get('source_ttl') or ''
    if ttl:
        ttl_path.write_text(ttl, encoding='utf-8')

    summary = {
        'rows_returned': len(rows),
        'stats_keys': {k: stats.get(k) for k in ['type_count', 'element_count', 'attribute_count', 'enum_count', 'import_count']},
        'ttl_written': str(ttl_path) if ttl else None,
    }

    # Also generate full OWL via OWLGenerationService using the original XSD
    try:
        print('\nGenerating full OWL via OWLGenerationService.generate_owl_from_xsd...')
        owl_ttl, owl_meta = OWLGenerationService.generate_owl_from_xsd(content, xsd_path.name)
        owl_path = out_dir / 'bom_ontology.ttl'
        owl_path.write_text(owl_ttl, encoding='utf-8')
        summary['owl_ttl_written'] = str(owl_path)
        summary['owl_meta'] = {k: owl_meta.get(k) for k in ('ttl_lines', 'schema_name') if k in owl_meta}
        print('OWL generation complete.')
        # Run SHACL validation on the generated OWL TTL
        try:
            print('Running SHACL validation on generated ontology...')
            shacl_report = OWLGenerationService.validate_with_shacl(owl_ttl)
            shacl_path = out_dir / 'bom_shacl_report.json'
            shacl_path.write_text(json.dumps(shacl_report, indent=2), encoding='utf-8')
            summary['shacl_report'] = str(shacl_path)
            summary['shacl_conforms'] = shacl_report.get('conforms')
            print('SHACL validation complete.')
        except Exception as se:
            print(f'SHACL validation failed: {se}')
    except Exception as e:
        print(f'OWL generation failed: {e}')

    summary = {
        'rows_returned': len(rows),
        'stats_keys': {k: stats.get(k) for k in ['type_count', 'element_count', 'attribute_count', 'enum_count', 'import_count']},
        'ttl_written': str(ttl_path) if ttl else None,
    }

    print(json.dumps(summary, indent=2))
    print('\nFirst 10 rows:')
    for r in rows[:10]:
        print(r)


if __name__ == '__main__':
    main()
