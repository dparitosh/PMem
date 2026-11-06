"""
services/ontology_validator.py
──────────────────────────────
Post-generation structural validator for OWL2/Turtle ontology files.

Checks performed
────────────────
1. Syntax          — rdflib can parse the file without error
2. Ontology header — owl:Ontology node present with rdfs:label / owl:versionInfo
3. Classes         — each owl:Class has rdfs:label; subClassOf targets exist
4. Object props    — each owl:ObjectProperty has label, rdfs:domain, rdfs:range
5. Datatype props  — each owl:DatatypeProperty has label, rdfs:domain, rdfs:range
6. Annotation props— each owl:AnnotationProperty has a label
7. Individuals     — each owl:NamedIndividual has label and at least one rdf:type
8. Disconnected    — properties whose domain/range URIs are not declared classes
9. Orphan classes  — classes that have no parent, no child, no property reference
10. Triple count   — summary statistics per construct category

Returns a ValidationReport dataclass; call .is_valid to gate the pipeline.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Set
from loguru import logger

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

# ── Helpers ──────────────────────────────────────────────────────────────────

def _local(uri) -> str:
    """Return the local name of a URI."""
    s = str(uri)
    return s.split("#")[-1].split("/")[-1] if ("#" in s or "/" in s) else s


def _has_provenance(g: Graph, uri: URIRef) -> bool:
    """Check if a URI has provenance annotation (dc:source)."""
    from rdflib.namespace import DC
    return len(list(g.objects(uri, DC.source))) > 0


def _label(g: Graph, uri: URIRef) -> str:
    lbl = next(g.objects(uri, RDFS.label), None)
    return str(lbl) if lbl else _local(uri)


# ── Report dataclasses ───────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    severity: str   # "error" | "warning" | "info"
    category: str   # "syntax" | "class" | "property" | "provenance" | ...
    message: str
    subject: str = ""
    
    def __str__(self) -> str:
        prefix = f"[{self.severity.upper()}:{self.category}]"
        return f"{prefix} {self.message}" + (f" ({self.subject})" if self.subject else "")


@dataclass
class ValidationReport:
    source: str = ""
    issues: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        """True when there are no error-level issues."""
        return len(self.errors) == 0
    
    @property 
    def provenance_coverage(self) -> float:
        """Return percentage of classes/properties with provenance annotations."""
        classes_total = self.stats.get("classes", 0)
        props_total = self.stats.get("properties", 0) 
        total_entities = classes_total + props_total
        if total_entities == 0:
            return 0.0
        classes_with_prov = self.stats.get("classes_with_provenance", 0)
        props_with_prov = self.stats.get("properties_with_provenance", 0)
        entities_with_prov = classes_with_prov + props_with_prov
        return (entities_with_prov / total_entities) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "stats": self.stats,
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "subject": i.subject,
                }
                for i in self.issues
            ],
        }

    def log_summary(self):
        valid_str = "VALID" if self.is_valid else "INVALID"
        logger.info(f"[OntologyValidator] {self.source} — {valid_str}  "
                    f"({len(self.errors)} errors, {len(self.warnings)} warnings)")
        for cat, count in self.stats.items():
            logger.info(f"  {cat:<30} {count}")
        for issue in self.issues:
            lvl = logger.error if issue.severity == "error" else logger.warning
            lvl(f"  [{issue.category}] {issue.message}"
                + (f"  <{issue.subject}>" if issue.subject else ""))


# ── Validator ────────────────────────────────────────────────────────────────

class OntologyValidator:
    """
    Validates a generated OWL2/Turtle ontology file.

    Usage
    ─────
    report = OntologyValidator().validate("path/to/output.ttl")
    if not report.is_valid:
        raise ValueError("Generated ontology has errors — aborting ingest.")
    """

    def validate(self, ttl_source: str, *, is_content: bool = False) -> ValidationReport:
        """
        Validate a Turtle file (path) or raw Turtle string (is_content=True).

        Parameters
        ──────────
        ttl_source  : file path or raw Turtle string
        is_content  : set True when ttl_source is a raw string, not a path
        """
        report = ValidationReport(source=ttl_source if not is_content else "<inline>")

        # ── 1. Syntax check ───────────────────────────────────────────────────
        g = Graph()
        try:
            if is_content:
                g.parse(data=ttl_source, format="turtle")
            else:
                g.parse(ttl_source, format="turtle")
        except Exception as exc:
            report.issues.append(ValidationIssue(
                severity="error", category="syntax",
                message=f"Turtle parse failed: {exc}",
            ))
            return report  # nothing else can run without a valid graph

        report.stats["total_triples"] = len(g)

        # ── 2. Ontology header ───────────────────────────────────────────────
        self._check_header(g, report)

        # ── 3. Classes ───────────────────────────────────────────────────────
        declared_class_uris: Set[URIRef] = self._check_classes(g, report)

        # ── 4 & 5. Properties ────────────────────────────────────────────────
        all_prop_domain_range_uris: Set[URIRef] = self._check_properties(g, report)

        # ── 6. Annotation properties ─────────────────────────────────────────
        self._check_annotation_properties(g, report)

        # ── 7. Individuals ───────────────────────────────────────────────────
        self._check_individuals(g, report)

        # ── 8. Provenance validation ─────────────────────────────────────────────
        self._check_provenance(g, report, declared_class_uris)

        # ── 9. Disconnected domains/ranges ───────────────────────────────────
        self._check_disconnected(report, declared_class_uris, all_prop_domain_range_uris)

        # ── 10. Orphan classes ───────────────────────────────────────────────
        self._check_orphan_classes(g, report, declared_class_uris)

        return report

    def validate_file(self, file_path: str) -> ValidationReport:
        """Backward-compatible file validator used by OWL generation services."""
        return self.validate(file_path, is_content=False)

    # ── Private check methods ─────────────────────────────────────────────────

    def _check_header(self, g: Graph, report: ValidationReport):
        ontos = list(g.subjects(RDF.type, OWL.Ontology))
        if not ontos:
            report.issues.append(ValidationIssue(
                severity="error", category="header",
                message="No owl:Ontology declaration found.",
            ))
            return
        report.stats["ontology_nodes"] = len(ontos)
        onto = ontos[0]

        if not list(g.objects(onto, RDFS.label)):
            report.issues.append(ValidationIssue(
                severity="warning", category="header",
                message="owl:Ontology missing rdfs:label.",
                subject=str(onto),
            ))
        if not list(g.objects(onto, OWL.versionInfo)):
            report.issues.append(ValidationIssue(
                severity="info", category="header",
                message="owl:Ontology missing owl:versionInfo.",
                subject=str(onto),
            ))

    def _check_classes(self, g: Graph, report: ValidationReport) -> Set[URIRef]:
        classes: Set[URIRef] = {s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}
        report.stats["owl_classes"] = len(classes)
        no_label = 0
        bad_parent = 0

        for cls in classes:
            if not list(g.objects(cls, RDFS.label)):
                no_label += 1
                report.issues.append(ValidationIssue(
                    severity="warning", category="class",
                    message="owl:Class has no rdfs:label.",
                    subject=str(cls),
                ))
            for parent in g.objects(cls, RDFS.subClassOf):
                if isinstance(parent, URIRef) and parent not in classes:
                    # Could be a BNode restriction — skip BNodes
                    bad_parent += 1
                    report.issues.append(ValidationIssue(
                        severity="warning", category="class",
                        message=(f"rdfs:subClassOf target '{_local(parent)}' is not "
                                 f"declared as owl:Class in this file."),
                        subject=str(cls),
                    ))

        subclass_rels = len(list(g.subject_objects(RDFS.subClassOf)))
        report.stats["subclass_axioms"] = subclass_rels
        return classes

    def _check_properties(self, g: Graph, report: ValidationReport) -> Set[URIRef]:
        obj_props: Set[URIRef] = {s for s in g.subjects(RDF.type, OWL.ObjectProperty) if isinstance(s, URIRef)}
        dt_props: Set[URIRef]  = {s for s in g.subjects(RDF.type, OWL.DatatypeProperty) if isinstance(s, URIRef)}
        all_props = obj_props | dt_props
        report.stats["object_properties"]   = len(obj_props)
        report.stats["datatype_properties"] = len(dt_props)

        referenced_uris: Set[URIRef] = set()

        for prop in all_props:
            lbl = list(g.objects(prop, RDFS.label))
            if not lbl:
                report.issues.append(ValidationIssue(
                    severity="warning", category="property",
                    message="Property has no rdfs:label.",
                    subject=str(prop),
                ))

            # domain
            domains = list(g.objects(prop, RDFS.domain))
            if not domains:
                report.issues.append(ValidationIssue(
                    severity="warning", category="property",
                    message=f"Property '{_label(g, prop)}' has no rdfs:domain.",
                    subject=str(prop),
                ))
            for d in domains:
                if isinstance(d, URIRef):
                    referenced_uris.add(d)

            # range
            ranges = list(g.objects(prop, RDFS.range))
            if not ranges:
                report.issues.append(ValidationIssue(
                    severity="warning", category="property",
                    message=f"Property '{_label(g, prop)}' has no rdfs:range.",
                    subject=str(prop),
                ))
            for r in ranges:
                if isinstance(r, URIRef) and str(r).startswith("http://www.w3.org/2001/XMLSchema"):
                    pass  # XSD types are fine — external
                elif isinstance(r, URIRef):
                    referenced_uris.add(r)

        report.stats["domain_range_refs"] = len(referenced_uris)
        return referenced_uris

    def _check_annotation_properties(self, g: Graph, report: ValidationReport):
        anno_props = list(g.subjects(RDF.type, OWL.AnnotationProperty))
        report.stats["annotation_properties"] = len(anno_props)
        for ap in anno_props:
            if not list(g.objects(ap, RDFS.label)):
                report.issues.append(ValidationIssue(
                    severity="info", category="annotation_property",
                    message="AnnotationProperty has no rdfs:label.",
                    subject=str(ap),
                ))

    def _check_individuals(self, g: Graph, report: ValidationReport):
        individuals = list(g.subjects(RDF.type, OWL.NamedIndividual))
        report.stats["individuals"] = len(individuals)
        no_label = 0
        no_type  = 0

        for ind in individuals:
            if not list(g.objects(ind, RDFS.label)):
                no_label += 1
                report.issues.append(ValidationIssue(
                    severity="info", category="individual",
                    message="NamedIndividual has no rdfs:label.",
                    subject=str(ind),
                ))
            # Has at least one non-NamedIndividual type
            types = [t for t in g.objects(ind, RDF.type) if t != OWL.NamedIndividual]
            if not types:
                no_type += 1
                report.issues.append(ValidationIssue(
                    severity="warning", category="individual",
                    message="NamedIndividual has no class membership (rdf:type) beyond owl:NamedIndividual.",
                    subject=str(ind),
                ))

    def _check_disconnected(
        self,
        report: ValidationReport,
        declared_classes: Set[URIRef],
        prop_refs: Set[URIRef],
    ):
        """Warn when domain/range references point outside the declared class set."""
        # OWL built-ins and XSD are intentionally external
        builtin_prefixes = (
            "http://www.w3.org/2002/07/owl#",
            "http://www.w3.org/2000/01/rdf-schema#",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "http://www.w3.org/2001/XMLSchema#",
            "http://www.w3.org/2004/02/skos/core#",
        )
        disconnected = 0
        for uri in prop_refs:
            if uri in declared_classes:
                continue
            if any(str(uri).startswith(p) for p in builtin_prefixes):
                continue
            disconnected += 1
            report.issues.append(ValidationIssue(
                severity="warning", category="disconnected",
                message=(f"domain/range ref '{_local(uri)}' is not declared as "
                         f"owl:Class in this file (may be in an imported ontology)."),
                subject=str(uri),
            ))
        report.stats["disconnected_refs"] = disconnected

    def _check_orphan_classes(
        self,
        g: Graph,
        report: ValidationReport,
        declared_classes: Set[URIRef],
    ):
        """
        A class is an orphan if it has no subClassOf, is not the target of any
        subClassOf, and no property has it as domain or range.
        """
        has_parent: Set[URIRef] = {s for s in g.subjects(RDFS.subClassOf, None) if isinstance(s, URIRef)}
        is_parent: Set[URIRef]  = {o for o in g.objects(None, RDFS.subClassOf) if isinstance(o, URIRef)}
        in_domain: Set[URIRef]  = {o for o in g.objects(None, RDFS.domain) if isinstance(o, URIRef)}
        in_range: Set[URIRef]   = {o for o in g.objects(None, RDFS.range) if isinstance(o, URIRef)}
        connected: Set[URIRef]  = has_parent | is_parent | in_domain | in_range
        orphans = declared_classes - connected
        report.stats["orphan_classes"] = len(orphans)
        for cls in orphans:
            report.issues.append(ValidationIssue(
                severity="info", category="orphan",
                message=(f"Class '{_label(g, cls)}' has no subClassOf relation "
                         f"and is not referenced by any property domain/range."),
                subject=str(cls),
            ))

    def _check_provenance(self, g: Graph, report: ValidationReport, declared_classes: Set[URIRef]):
        """Check provenance annotations and detect abstract-only vs element-mapping ontologies."""
        
        # Count classes and properties with dc:source annotations
        classes_with_prov = 0
        props_with_prov = 0
        skos_concept_classes = set()
        element_mapping_classes = set()
        
        # Check classes
        for cls in declared_classes:
            if _has_provenance(g, cls):
                classes_with_prov += 1
            
            # Detect SKOS concept classes (abstract categories)
            if (cls, RDF.type, SKOS.Concept) in g:
                skos_concept_classes.add(cls)
            else:
                element_mapping_classes.add(cls)
        
        # Check properties
        all_props = set(g.subjects(RDF.type, OWL.ObjectProperty)) | set(g.subjects(RDF.type, OWL.DatatypeProperty))
        for prop in all_props:
            if _has_provenance(g, prop):
                props_with_prov += 1
        
        report.stats["classes_with_provenance"] = classes_with_prov
        report.stats["properties_with_provenance"] = props_with_prov
        report.stats["skos_concept_classes"] = len(skos_concept_classes)
        report.stats["element_mapping_classes"] = len(element_mapping_classes)
        
        # Calculate coverage
        total_classes = len(declared_classes)
        total_props = len(all_props)
        
        # Warn about missing provenance
        if total_classes > 0:
            class_prov_pct = (classes_with_prov / total_classes) * 100
            if class_prov_pct < 50:
                report.issues.append(ValidationIssue(
                    severity="warning", category="provenance",
                    message=f"Only {class_prov_pct:.1f}% of classes have provenance annotations (dc:source). Expected >50% for proper traceability.",
                ))
        
        if total_props > 0:
            prop_prov_pct = (props_with_prov / total_props) * 100  
            if prop_prov_pct < 50:
                report.issues.append(ValidationIssue(
                    severity="warning", category="provenance", 
                    message=f"Only {prop_prov_pct:.1f}% of properties have provenance annotations (dc:source). Expected >50% for proper traceability.",
                ))
        
        # Detect abstract-only ontologies (only SKOS concepts, no element mappings)
        if len(skos_concept_classes) > 0 and len(element_mapping_classes) == 0:
            report.issues.append(ValidationIssue(
                severity="error", category="completeness",
                message="Ontology contains only abstract SKOS concept classes, missing concrete element mappings from source data. This breaks semantic traceability.",
            ))
            
        # Detect likely incomplete generation
        if len(skos_concept_classes) > 0 and len(element_mapping_classes) < len(skos_concept_classes):
            report.issues.append(ValidationIssue(
                severity="warning", category="completeness",
                message=f"Found {len(skos_concept_classes)} abstract categories but only {len(element_mapping_classes)} concrete mappings. Source XSD conversion may be incomplete.",
            ))
        
        # Report provenance summary
        if classes_with_prov + props_with_prov > 0:
            report.issues.append(ValidationIssue(
                severity="info", category="provenance",
                message=f"Provenance coverage: {classes_with_prov}/{total_classes} classes, {props_with_prov}/{total_props} properties have dc:source annotations.",
            ))
