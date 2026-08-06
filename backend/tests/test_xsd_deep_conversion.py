from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS
from rdflib.namespace import OWL

from backend.Services.owl_xsd_engine import OntologyConfig, convert_xsd_to_owl
from backend.Services.xsd_relational_report import build_xsd_relational_report


XSD = '''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="http://example.test/model" xmlns:m="http://example.test/model"
    elementFormDefault="qualified">
  <xs:include schemaLocation="shared.xsd"/>
  <xs:element name="Root" type="m:Node"/>
  <xs:complexType name="Node">
    <xs:sequence>
      <xs:element name="id" type="xs:ID"/>
      <xs:element name="label" type="xs:string" minOccurs="0"/>
      <xs:element name="children" minOccurs="0" maxOccurs="unbounded">
        <xs:complexType>
          <xs:sequence><xs:element name="value" type="xs:decimal"/></xs:sequence>
          <xs:attribute name="quantity" type="xs:positiveInteger" use="required"/>
        </xs:complexType>
      </xs:element>
      <xs:element name="parent" type="m:Node" minOccurs="0"/>
    </xs:sequence>
    <xs:attribute name="revision" type="xs:string" use="required"/>
  </xs:complexType>
</xs:schema>'''

SHARED = '''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="http://example.test/model" xmlns:m="http://example.test/model">
  <xs:simpleType name="Code"><xs:restriction base="xs:string"/></xs:simpleType>
</xs:schema>'''


def _write_schema(tmp_path: Path) -> Path:
    (tmp_path / "model.xsd").write_text(XSD, encoding="utf-8")
    (tmp_path / "shared.xsd").write_text(SHARED, encoding="utf-8")
    return tmp_path / "model.xsd"


def test_deep_anonymous_recursive_xsd_creates_bounded_owl_graph(tmp_path):
    schema = _write_schema(tmp_path)
    output = tmp_path / "model.ttl"
    config = OntologyConfig(
        base_uri="http://example.test/model#", prefix="m", title="Model",
        description="test", schema_dir=str(tmp_path), target_files=["model"],
        output_ttl=str(output),
    )
    convert_xsd_to_owl(config)
    graph = Graph().parse(output, format="turtle")
    ns = Namespace("http://example.test/model#")
    assert (ns.Node, RDF.type, OWL.Class) in graph
    assert (ns.Node__children, RDF.type, OWL.Class) in graph
    assert (ns.Node__children_value, RDFS.domain, ns.Node__children) in graph
    assert len(graph) < 5000  # recursion must not expand indefinitely


def test_relational_projection_uses_child_and_junction_tables(tmp_path):
    schema = _write_schema(tmp_path)
    report = build_xsd_relational_report(schema)
    tables = {table["name"]: table for table in report["tables"]}
    assert "Node" in tables
    assert "Node__children" in tables
    assert "Node__children__link" in tables
    assert any(rel["association_table"] == "Node__children__link"
               for rel in tables["Node"]["relationships"])
    assert any(col["name"] == "revision" and col["required"]
               for col in tables["Node"]["columns"])
