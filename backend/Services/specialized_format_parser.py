"""Specialized parser entrypoints used by unified data import."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .import_format_helpers import derive_prefix_from_namespace


class SpecializedFormatParser:
    """Non-tabular specialized parser entrypoints."""

    @staticmethod
    def parse_xmi(file_content: bytes) -> tuple[list[dict], dict]:
        from pathlib import Path
        from .xmi_parser import XMIParser
        from .ap239_parser import AP239XMIParser, classify_ap239_concept, AP239_NAMESPACE
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xmi") as tmp:
            tmp.write(file_content)
            tmp_path = Path(tmp.name)

        ap239_stats: Dict[str, Any] = {}
        try:
            parser = XMIParser()
            parsed = parser.parse(tmp_path)
            xmi_snippet = file_content[:4096].decode("utf-8", errors="ignore")
            if AP239_NAMESPACE in xmi_snippet or "AP239" in xmi_snippet.upper():
                ap239_parser = AP239XMIParser()
                model = ap239_parser.parse_xmi_file(tmp_path)
                ap239_stats = {
                    "is_ap239": True,
                    "ap239_parts": len(model.parts),
                    "ap239_activities": len(model.activities),
                    "ap239_requirements": len(model.requirements),
                    "ap239_interfaces": len(model.interface_connectors),
                    "ap239_documents": len(model.documents),
                }
        except Exception as xmi_err:
            logging.error(f"XMI parse error: {xmi_err}")
            return [], {"error": str(xmi_err), "file_format": "XMI"}
        finally:
            tmp_path.unlink(missing_ok=True)

        nodes = parsed.get("nodes", [])
        relationships = parsed.get("relationships", [])
        provenance = parsed.get("provenance", {})

        preview_rows = []
        columns = set()
        for node in nodes:
            row = {"label": node.get("label", "Element")}
            props = node.get("properties", {})
            row.update(props)
            preview_rows.append(row)
            columns.update(row.keys())

        if ap239_stats.get("is_ap239"):
            for row in preview_rows:
                if row.get("label") in ("Element", "Class") and row.get("name"):
                    row["ap239_concept"] = classify_ap239_concept(row["name"])

        rel_stats = {
            "relationship_count": len(relationships),
            "relationship_types": list({rel.get("type") for rel in relationships}),
        }

        namespace_uri = provenance.get("xmi_namespace", "")
        if not namespace_uri:
            namespace_map = provenance.get("namespaces", {}) if isinstance(provenance, dict) else {}
            if isinstance(namespace_map, dict):
                namespace_uri = namespace_map.get("xmi", "") or namespace_map.get("default", "")
        if not namespace_uri:
            try:
                import defusedxml.ElementTree as xml_tree

                xmi_root = xml_tree.fromstring(file_content[:8192])
                namespace_uri = xmi_root.tag[1:xmi_root.tag.index("}")] if xmi_root.tag.startswith("{") else ""
                if not namespace_uri:
                    for attr_name, attr_value in xmi_root.attrib.items():
                        if "xmlns" in attr_name.lower() and attr_value.startswith("http"):
                            namespace_uri = attr_value
                            break
            except Exception:
                pass
        namespace_prefix = derive_prefix_from_namespace(namespace_uri) if namespace_uri else (
            "ap239" if ap239_stats.get("is_ap239") else "xmi"
        )

        stats = {
            "success": True,
            "row_count": len(preview_rows),
            "column_count": len(columns),
            "columns": list(columns),
            "relationships": rel_stats,
            "provenance": provenance,
            "namespace": namespace_uri,
            "ontology_prefix": namespace_prefix,
            "ontology_name": namespace_uri.rstrip("/").split("/")[-1] or namespace_prefix,
            "_xmi_relationships": relationships,
            **ap239_stats,
        }
        return preview_rows, stats

    @staticmethod
    def parse_express(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            from .owl_generation_service import OWLGenerationService

            owl_ttl, schema_metadata = OWLGenerationService.generate_owl_from_express(
                file_content,
                "schema.exp",
            )
            schema_metadata["owl_ttl"] = owl_ttl
            rows = [
                {"type": "Schema", "name": schema_metadata.get("schema_name", "Unknown"), "entities": schema_metadata.get("entity_count", 0)},
                {"type": "DERIVE", "count": schema_metadata.get("derived_attributes", 0)},
                {"type": "INVERSE", "count": schema_metadata.get("inverse_attributes", 0)},
                {"type": "UNIQUE", "count": schema_metadata.get("unique_constraints", 0)},
                {"type": "OWL Generated", "triples": schema_metadata.get("owl_triple_count", 0)},
            ]
            for entity_name in schema_metadata.get("entities", [])[:10]:
                rows.append({"label": "ExpressEntity", "entity": entity_name})
            return rows, schema_metadata
        except Exception as exc:
            logging.error(f"EXPRESS parser error: {exc}")
            return [], {"error": str(exc)}

    @staticmethod
    def parse_xsd(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            import tempfile
            from lxml import etree
            from rdflib import Graph, Namespace, RDF, RDFS, URIRef, Literal
            from rdflib.namespace import OWL

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xsd") as tmp:
                tmp.write(file_content)
                tmp_path = Path(tmp.name)

            try:
                safe_xsd = etree.XMLParser(
                    resolve_entities=False,
                    no_network=True,
                    load_dtd=False,
                    huge_tree=False,
                )
                tree = etree.parse(str(tmp_path), safe_xsd)
                root = tree.getroot()

                nsmap = {k if k else "default": v for k, v in (root.nsmap or {}).items()}
                target_ns = root.get("targetNamespace") or ""

                model: Dict[str, Any] = {
                    "types": {},
                    "elements": {},
                    "attributes": {},
                    "groups": {},
                    "attributeGroups": {},
                    "imports": [],
                    "includes": [],
                    "redefines": [],
                    "substitutionGroups": {},
                    "keys": [],
                    "unique": [],
                    "keyrefs": [],
                    "enumerations": {},
                    "unions": {},
                    "lists": {},
                    "any": [],
                    "anyAttribute": [],
                    "provenance": {
                        "namespaces": nsmap,
                        "targetNamespace": target_ns,
                        "root_tag": root.tag,
                    },
                }

                xsd_ns = "{http://www.w3.org/2001/XMLSchema}"

                def xml_snippet(elem):
                    try:
                        return etree.tostring(elem, pretty_print=False).decode("utf-8")
                    except Exception:
                        return ""

                for ct in tree.findall(".//" + xsd_ns + "complexType"):
                    name = ct.get("name") or str(uuid.uuid4())
                    model["types"][name] = {"kind": "complex", "name": name, "xml": xml_snippet(ct), "elements": [], "attributes": []}
                    ext = ct.find(".//" + xsd_ns + "extension")
                    if ext is not None:
                        model["types"][name]["extension_base"] = ext.get("base")
                    restr = ct.find(".//" + xsd_ns + "restriction")
                    if restr is not None:
                        model["types"][name]["restriction_base"] = restr.get("base")

                for st in tree.findall(".//" + xsd_ns + "simpleType"):
                    name = st.get("name") or str(uuid.uuid4())
                    model["types"][name] = {"kind": "simple", "name": name, "xml": xml_snippet(st)}
                    enums = st.findall(".//" + xsd_ns + "enumeration")
                    if enums:
                        model["enumerations"][name] = [e.get("value") for e in enums if e.get("value")]
                    union = st.find(".//" + xsd_ns + "union")
                    if union is not None:
                        model["unions"][name] = union.get("memberTypes")
                    lst = st.find(".//" + xsd_ns + "list")
                    if lst is not None:
                        model["lists"][name] = lst.get("itemType") or ""

                for el in tree.findall(".//" + xsd_ns + "element"):
                    name = el.get("name") or str(uuid.uuid4())
                    model["elements"][name] = {
                        "name": name,
                        "type": el.get("type"),
                        "minOccurs": el.get("minOccurs"),
                        "maxOccurs": el.get("maxOccurs"),
                        "substitutionGroup": el.get("substitutionGroup"),
                        "xml": xml_snippet(el),
                    }
                    if el.get("substitutionGroup"):
                        model["substitutionGroups"].setdefault(el.get("substitutionGroup"), []).append(name)

                for attr in tree.findall(".//" + xsd_ns + "attribute"):
                    name = attr.get("name") or str(uuid.uuid4())
                    model["attributes"][name] = {"name": name, "type": attr.get("type"), "use": attr.get("use"), "xml": xml_snippet(attr)}

                for grp in tree.findall(".//" + xsd_ns + "group"):
                    gname = grp.get("name") or str(uuid.uuid4())
                    model["groups"][gname] = {"name": gname, "xml": xml_snippet(grp)}
                for ag in tree.findall(".//" + xsd_ns + "attributeGroup"):
                    aname = ag.get("name") or str(uuid.uuid4())
                    model["attributeGroups"][aname] = {"name": aname, "xml": xml_snippet(ag)}

                for key in tree.findall(".//" + xsd_ns + "key"):
                    model["keys"].append({"name": key.get("name"), "xml": xml_snippet(key)})
                for uq in tree.findall(".//" + xsd_ns + "unique"):
                    model["unique"].append({"name": uq.get("name"), "xml": xml_snippet(uq)})
                for kr in tree.findall(".//" + xsd_ns + "keyref"):
                    model["keyrefs"].append({"name": kr.get("name"), "refer": kr.get("refer"), "xml": xml_snippet(kr)})

                for any_el in tree.findall(".//" + xsd_ns + "any"):
                    model["any"].append({"xml": xml_snippet(any_el)})
                for any_attr in tree.findall(".//" + xsd_ns + "anyAttribute"):
                    model["anyAttribute"].append({"xml": xml_snippet(any_attr)})

                for imp in tree.findall(".//" + xsd_ns + "import"):
                    model["imports"].append({"namespace": imp.get("namespace"), "schemaLocation": imp.get("schemaLocation")})
                for inc in tree.findall(".//" + xsd_ns + "include"):
                    model["includes"].append({"schemaLocation": inc.get("schemaLocation")})
                for red in tree.findall(".//" + xsd_ns + "redefine"):
                    model["redefines"].append({"xml": xml_snippet(red)})

                src = Namespace("http://depo-onto.local/source#")
                src_g = Graph()
                src_g.bind("src", src)
                src_g.bind("owl", OWL)

                root_uri = URIRef(src[root.get("name") or Path(tmp_path).stem])
                src_g.add((root_uri, RDF.type, src.SourceSchema))
                src_g.add((root_uri, RDFS.label, Literal(Path(tmp_path).name)))

                for tname, tinfo in model["types"].items():
                    cls = URIRef(src["type/" + tname])
                    src_g.add((cls, RDF.type, OWL.Class))
                    src_g.add((cls, RDFS.label, Literal(tname)))
                    src_g.add((cls, src.sourceXml, Literal(tinfo.get("xml", ""))))
                    if tinfo.get("extension_base"):
                        src_g.add((cls, RDFS.subClassOf, URIRef(src["type/" + tinfo["extension_base"]])))
                    if tinfo.get("restriction_base"):
                        src_g.add((cls, src.restrictionOn, Literal(tinfo["restriction_base"])))

                for ename, einfo in model["elements"].items():
                    prop = URIRef(src["element/" + ename])
                    typ = einfo.get("type") or ""
                    if typ.startswith("xs:") or typ.startswith("xsd:") or typ in ("string", "int", "integer"):
                        src_g.add((prop, RDF.type, OWL.DatatypeProperty))
                    else:
                        src_g.add((prop, RDF.type, OWL.ObjectProperty))
                    src_g.add((prop, RDFS.label, Literal(ename)))
                    src_g.add((prop, src.sourceXml, Literal(einfo.get("xml", ""))))

                for aname, ainfo in model["attributes"].items():
                    prop = URIRef(src["attribute/" + aname])
                    src_g.add((prop, RDF.type, OWL.DatatypeProperty))
                    src_g.add((prop, RDFS.label, Literal(aname)))
                    src_g.add((prop, src.sourceXml, Literal(ainfo.get("xml", ""))))

                try:
                    ttl = src_g.serialize(format="turtle")
                except Exception:
                    ttl = ""

                rows: List[Dict[str, Any]] = []
                for tname, tinfo in model["types"].items():
                    rows.append({"kind": "type", "name": tname, "kind_detail": tinfo.get("kind")})
                for ename, einfo in model["elements"].items():
                    rows.append({"kind": "element", "name": ename, "type": einfo.get("type")})
                for aname, ainfo in model["attributes"].items():
                    rows.append({"kind": "attribute", "name": aname, "type": ainfo.get("type")})

                stats = {
                    "type_count": len(model["types"]),
                    "element_count": len(model["elements"]),
                    "attribute_count": len(model["attributes"]),
                    "group_count": len(model["groups"]),
                    "import_count": len(model["imports"]),
                    "enum_count": sum(1 for _ in model["enumerations"]),
                    "row_count": len(rows),
                    "format": "XSD",
                    "file_format": "XSD",
                    "provenance": model["provenance"],
                    "source_ttl": ttl,
                }
                return rows, stats
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as exc:
            logging.error(f"XSD parser error: {exc}")
            return [], {"error": str(exc), "file_format": "XSD"}
