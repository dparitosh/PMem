from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import DataProductBuilder
from .catalog import read_xlsx_catalog
from .models import DataProductSpec


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an isolated engineering data-product package")
    parser.add_argument("--spec", help="JSON product specification")
    parser.add_argument("--catalog-xlsx", help="Excel catalog to include")
    parser.add_argument("--output", default="output", help="Output directory")
    args = parser.parse_args()
    if not args.spec:
        if not args.catalog_xlsx:
            parser.error("provide --spec or --catalog-xlsx")
        catalog = read_xlsx_catalog(args.catalog_xlsx)
        spec = DataProductSpec(
            product_id="catalog-reference",
            name="Engineering Data Product Catalog Reference",
            domain="Product foundation",
            description="Catalog-derived reference package for the application data-product model.",
            catalog_path=args.catalog_xlsx,
        )
        result = DataProductBuilder(args.output).build(spec, catalog_path=args.catalog_xlsx)
        print(json.dumps({"records": len(catalog["records"]), "zip": result["zip"]}, indent=2))
        return 0
    payload = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    result = DataProductBuilder(args.output).build(DataProductSpec.from_dict(payload), catalog_path=args.catalog_xlsx)
    print(json.dumps({"zip": result["zip"], "directory": result["directory"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
