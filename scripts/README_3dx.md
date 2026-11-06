3DExperience schema -> OWL/Turtle conversion

Run the converter to generate a Turtle ontology from the spreadsheets in the shared schema folder.

Install dependencies (if needed):

```bash
pip install -r scripts/requirements_3dx.txt
```

Example run:

```bash
python scripts/convert_3dx_schema.py --src "D:\path\to\Schema - Shared" --out outputs/3dx_ontology.ttl --prefix 3dx --base http://example.org/3dx#
```

The generator creates one OWL class per spreadsheet filename and a datatype property per column.
Refine the produced Turtle manually to add object properties, cardinalities, and richer typing.
