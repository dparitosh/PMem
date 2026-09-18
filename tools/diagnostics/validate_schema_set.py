"""Read-only local multi-XSD/instance audit; never loads remote schemas."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname
from lxml import etree


def audit(directory: Path, instance: Path):
    directory = directory.resolve()
    files = sorted(directory.glob("*.xsd"))
    allowed = {path.resolve() for path in files}
    class LocalResolver(etree.Resolver):
        def resolve(self, url, public_id, context):
            parts = urlsplit(url)
            if parts.scheme == "file" and parts.netloc:
                raise ValueError("Remote file authorities are not allowed")
            path = Path(url2pathname(parts.path)) if parts.scheme == "file" else Path(url)
            if not path.is_absolute():
                path = directory / path
            if path.resolve() not in allowed:
                raise ValueError("Schema dependency is outside the supplied schema set")
            return self.resolve_filename(str(path.resolve()), context)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    parser.resolvers.add(LocalResolver())
    source = etree.fromstring(instance.read_bytes(), parser=etree.XMLParser(resolve_entities=False, no_network=True))
    if source.getroottree().docinfo.doctype:
        raise ValueError("Instance DOCTYPE is not allowed")
    results = []
    for path in files:
        item = {"schema": path.name}
        try:
            document = etree.parse(str(path), parser)
            if document.docinfo.doctype:
                raise ValueError("Schema DOCTYPE is not allowed")
            item["namespace"] = document.getroot().get("targetNamespace")
            schema = etree.XMLSchema(document)
            item["compiled"] = True
            item["instance_valid"] = schema.validate(source)
            item["errors"] = [str(error) for error in list(schema.error_log)[:5]]
        except (etree.Error, ValueError) as exc:
            item.update(compiled=False, error=str(exc))
        results.append(item)
    namespace = etree.QName(source).namespace
    xs = "http://www.w3.org/2001/XMLSchema"
    wrapper = etree.Element(f"{{{xs}}}schema", targetNamespace=namespace, nsmap={"xs": xs})
    for item in results:
        tag = "include" if item.get("namespace") == namespace else "import"
        attributes = {"schemaLocation": item["schema"]}
        if tag == "import" and item.get("namespace"):
            attributes["namespace"] = item["namespace"]
        etree.SubElement(wrapper, f"{{{xs}}}{tag}", **attributes)
    try:
        combined = etree.XMLSchema(etree.fromstring(etree.tostring(wrapper), parser,
                                   base_url=str(directory / "__schema_set__.xsd")))
        aggregate = {"compiled": True, "instance_valid": combined.validate(source),
                     "errors": [str(error) for error in list(combined.error_log)[:10]]}
    except (etree.Error, ValueError) as exc:
        aggregate = {"compiled": False, "error": str(exc)}
    return {"instance": instance.name, "schema_count": len(files), "schemas": results, "combined": aggregate,
            "semantic_mapping_validation": "not_performed", "publication": "not_performed"}


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("schema_directory", type=Path)
    args.add_argument("instance", type=Path)
    options = args.parse_args()
    print(json.dumps(audit(options.schema_directory, options.instance), indent=2))
