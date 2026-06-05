#!/usr/bin/env python3
"""Convert simple 3DExperience schema spreadsheets (.xls/.xlsx) into an OWL/Turtle ontology.

This script creates one OWL class per spreadsheet filename and one datatype
property per column. Run with --help for usage.
"""
import argparse
import os
import re
from pathlib import Path

try:
    import pandas as pd
except Exception:
    print('Missing dependency: pandas')
    raise

try:
    from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, URIRef, Literal
except Exception:
    print('Missing dependency: rdflib')
    raise


def sanitize_identifier(s: str) -> str:
    s = str(s or '')
    s = s.strip()
    s = re.sub(r"[^0-9A-Za-z_]+", '_', s)
    s = re.sub(r'_+', '_', s)
    s = re.sub(r'^([^A-Za-z_])', r'_\1', s)
    return s or 'unnamed'


def infer_column_type(series: pd.Series):
    vals = series.dropna().astype(str).map(lambda s: s.strip()).loc[lambda s: s != '']
    sample = vals.head(50).tolist()
    if not sample:
        return XSD.string
    # boolean
    low = [s.lower() for s in sample]
    if all(s in ('true', 'false', '0', '1') for s in low):
        return XSD.boolean
    # integer
    try:
        if all(re.fullmatch(r'[+-]?\d+', s) for s in sample):
            return XSD.integer
    except Exception:
        pass
    # decimal/float
    try:
        if all(re.fullmatch(r'[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)', s) for s in sample):
            return XSD.decimal
    except Exception:
        pass
    # date/time iso-ish
    iso_count = 0
    for s in sample:
        if re.match(r'\d{4}-\d{2}-\d{2}', s):
            iso_count += 1
    if iso_count >= max(1, len(sample) // 2):
        return XSD.date
    return XSD.string


def sheet_to_class(graph: Graph, ns: Namespace, cls_name: str, df: pd.DataFrame, known_classes: set):
    cls_id = ns[sanitize_identifier(cls_name)]
    graph.add((cls_id, RDF.type, OWL.Class))
    graph.add((cls_id, RDFS.label, Literal(cls_name)))

    for col in df.columns:
        col_clean = str(col or '')
        prop_name = f"{sanitize_identifier(cls_name)}_{sanitize_identifier(col_clean)}"
        prop = ns[prop_name]
        label = Literal(col_clean)
        graph.add((prop, RDFS.label, label))
        graph.add((prop, RDFS.domain, cls_id))

        # Heuristic: treat columns that look like references as ObjectProperty
        col_lower = col_clean.lower()
        is_ref_name = any(x in col_lower for x in ('_id', ' id', 'id_', 'uid', 'ref', 'reference', 'owner', 'parent', 'related', 'link'))

        if is_ref_name:
            graph.add((prop, RDF.type, OWL.ObjectProperty))
            # try to set a range if it matches a known class name
            target = sanitize_identifier(col_clean.replace('_id', '').replace(' id', '').strip())
            if target and target in known_classes:
                graph.add((prop, RDFS.range, ns[target]))
            # otherwise leave range unspecified
            continue

        # Otherwise infer datatype
        try:
            dtype = infer_column_type(df[col])
            graph.add((prop, RDF.type, OWL.DatatypeProperty))
            graph.add((prop, RDFS.range, dtype))
        except Exception:
            graph.add((prop, RDF.type, OWL.DatatypeProperty))
            graph.add((prop, RDFS.range, XSD.string))


def process_folder(src_path: Path, out_path: Path, prefix: str, base_iri: str):
    g = Graph()
    ns = Namespace(base_iri)
    g.bind(prefix, ns)
    g.bind('rdf', RDF)
    g.bind('rdfs', RDFS)
    g.bind('owl', OWL)
    g.bind('xsd', XSD)

    files_processed = 0

    # First pass: collect known class names (file stems)
    candidate_files = []
    known_classes = set()
    for root, dirs, files in os.walk(src_path):
        for fname in files:
            if not fname.lower().endswith(('.xls', '.xlsx', '.csv')):
                continue
            class_base = Path(fname).stem
            known_classes.add(sanitize_identifier(class_base))
            candidate_files.append((Path(root) / fname, fname))

    # Second pass: actually read files and build classes/properties with heuristics
    for fpath, fname in candidate_files:
        try:
            if fname.lower().endswith('.csv'):
                df = pd.read_csv(fpath)
            elif fname.lower().endswith('.xls'):
                df = pd.read_excel(fpath, sheet_name=0, engine='xlrd')
            else:
                df = pd.read_excel(fpath, sheet_name=0, engine='openpyxl')
        except Exception as e:
            try:
                df = pd.read_excel(fpath, sheet_name=0)
            except Exception as e2:
                try:
                    raw = Path(fpath).read_bytes()
                    txt = raw.decode('utf-8', errors='ignore')
                    low = txt.lower()
                    if '<table' in low:
                        dfs = pd.read_html(txt)
                        if len(dfs) > 0:
                            df = dfs[0]
                        else:
                            raise e2
                    else:
                        if '\t' in txt:
                            from io import StringIO
                            df = pd.read_csv(StringIO(txt), sep='\t')
                        elif ',' in txt:
                            from io import StringIO
                            df = pd.read_csv(StringIO(txt))
                        else:
                            raise e2
                except Exception as e3:
                    print(f'Warning: could not read {fpath}: {e3}')
                    continue

        class_base = Path(fname).stem
        print(f'Processing {fpath} -> Class {class_base} ({len(df.columns)} cols)')
        sheet_to_class(g, ns, class_base, df, known_classes)
        files_processed += 1

    if files_processed == 0:
        print('No spreadsheet files processed. Nothing written.')
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(out_path), format='turtle')
    print(f'Wrote ontology to {out_path} ({files_processed} files processed)')
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--src', required=True, help='Source folder containing schema spreadsheets')
    p.add_argument('--out', required=True, help='Output Turtle file')
    p.add_argument('--prefix', default='3dx', help='Prefix to bind for the ontology')
    p.add_argument('--base', default='http://example.org/3dx#', help='Base IRI for the ontology namespace')
    args = p.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    if not src.exists() or not src.is_dir():
        print('Source folder does not exist or is not a directory:', src)
        raise SystemExit(2)

    ok = process_folder(src, out, args.prefix, args.base)
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
