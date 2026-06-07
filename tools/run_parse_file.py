#!/usr/bin/env python3
"""Generic runner: parse XSD, write source TTL, generate OWL, run SHACL validation."""
from pathlib import Path
import sys
import json


BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

try:
    from backend.Services.unified_data_import import FileFormatDetector
    from backend.Services.owl_generation_service import OWLGenerationService
except Exception as e:
    print(f"Imports failed: {e}")
    raise


def run_for(xsd_path: Path):
    if not xsd_path.exists():
        print(f"XSD file not found: {xsd_path}")
        return 2

    print(f"Parsing: {xsd_path}")
    content = xsd_path.read_bytes()
    rows, stats = FileFormatDetector.parse_xsd(content)

    out_dir = BASE / 'data' / 'parser_outputs'
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = xsd_path.stem
    ttl_path = out_dir / f'{base_name}_source.ttl'

    ttl = stats.get('source_ttl') or ''
    if ttl:
        ttl_path.write_text(ttl, encoding='utf-8')

    summary = {
        'rows_returned': len(rows),
        'stats_keys': {k: stats.get(k) for k in ['type_count', 'element_count', 'attribute_count', 'enum_count', 'import_count']},
        'ttl_written': str(ttl_path) if ttl else None,
    }

    # Generate full OWL and run SHACL
    try:
        print('Generating full OWL...')
        owl_ttl, owl_meta = OWLGenerationService.generate_owl_from_xsd(content, xsd_path.name)
        owl_path = out_dir / f'{base_name}_ontology.ttl'
        owl_path.write_text(owl_ttl, encoding='utf-8')
        summary['owl_ttl_written'] = str(owl_path)
        summary['owl_meta'] = {k: owl_meta.get(k) for k in ('ttl_lines', 'schema_name') if k in owl_meta}
        print('OWL generation complete.')

        print('Running SHACL validation...')
        shacl_report = OWLGenerationService.validate_with_shacl(owl_ttl)
        shacl_path = out_dir / f'{base_name}_shacl_report.json'
        shacl_path.write_text(json.dumps(shacl_report, indent=2), encoding='utf-8')
        summary['shacl_report'] = str(shacl_path)
        summary['shacl_conforms'] = shacl_report.get('conforms')
        print('SHACL validation complete.')
    except Exception as e:
        print(f'OWL/SHACL step failed: {e}')

    print(json.dumps(summary, indent=2))
    return 0


def main():
    if len(sys.argv) < 2:
        print('Usage: run_parse_file.py <path/to/file.xsd>')
        sys.exit(2)
    inp = Path(sys.argv[1])
    if not inp.is_absolute():
        inp = BASE / inp
    rc = run_for(inp)
    sys.exit(rc)


if __name__ == '__main__':
    main()
