"""Repository-wide NetworkX dependency and issue audit.

This is intentionally dependency-light and read-only with respect to source code.
It emits a machine-readable report under data/code_audit/.
"""
from __future__ import annotations

import ast
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "code_audit" / "networkx_audit.json"
EXCLUDED = {
    ".git", ".dt_venv", "node_modules", "build", "coverage", "__pycache__",
    "data", "ontology_uploads", "uploads", "logs", "_restore_ingest", "external",
}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
TEST_MARKERS = ("test_", ".test.", ".spec.", "tests/", "tests\\")


def files() -> list[Path]:
    result = []
    for directory, dirs, names in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in EXCLUDED]
        result.extend(
            Path(directory) / name for name in names
            if Path(name).suffix.lower() in SOURCE_SUFFIXES
        )
    return sorted(result)


def repository_files(suffixes: set[str]):
    for directory, dirs, names in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in EXCLUDED]
        for name in names:
            path = Path(directory) / name
            if path.suffix.lower() in suffixes:
                yield path


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_test(path: Path) -> bool:
    name = rel(path).lower()
    return any(marker in name for marker in TEST_MARKERS)


def py_module(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def resolve_python_import(current: Path, module: str | None, level: int, module_map: dict[str, str]) -> str | None:
    if level:
        base = list(current.relative_to(ROOT).with_suffix("").parts[:-1])
        keep = max(0, len(base) - level + 1)
        candidate = ".".join(base[:keep] + ([module] if module else []))
    else:
        candidate = module or ""
    alternatives = [candidate]
    if candidate and not candidate.startswith("backend."):
        alternatives.append("backend." + candidate)
    for item in alternatives:
        if item in module_map:
            return module_map[item]
    return None


def js_target(path: Path, spec: str, known: set[str]) -> str | None:
    if not spec.startswith("."):
        return None
    # Keep the import's original casing. On case-insensitive filesystems,
    # resolve() can turn `./App` into the existing `app/` directory and make
    # the real sibling `App.js` impossible to discover.
    base = Path(os.path.normpath(path.parent / spec))
    source_extensions = {".js", ".jsx", ".ts", ".tsx"}
    if base.suffix:
        candidates = [base] if base.suffix.lower() in source_extensions else []
    else:
        candidates = [base, *(base.with_suffix(s) for s in source_extensions)]
        candidates += [base / ("index" + s) for s in source_extensions]
    for candidate in candidates:
        try:
            value = rel(candidate)
        except ValueError:
            continue
        if value in known:
            return value
    return None


class PythonFacts(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: list[tuple[str | None, int, str]] = []
        self.definitions: list[dict] = []
        self.calls = Counter()
        self.routes: list[dict] = []
        self.broad_excepts: list[int] = []
        self.silent_excepts: list[int] = []
        self.dynamic_execution: list[dict] = []
        self.current_class: list[str] = []
        self.function_depth = 0

    def visit_Import(self, node: ast.Import) -> None:
        kind = "lazy_import" if self.function_depth else "import"
        self.imports.extend((alias.name, 0, kind) for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        kind = "lazy_import" if self.function_depth else "import"
        self.imports.append((node.module, node.level, kind))

    def _definition(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        decisions = sum(isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.BoolOp, ast.Match, ast.comprehension)) for n in ast.walk(node))
        self.definitions.append({
            "name": ".".join(self.current_class + [node.name]),
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "complexity_proxy": 1 + decisions,
        })
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr.lower() in {"get", "post", "put", "delete", "patch"}:
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    self.routes.append({"method": dec.func.attr.upper(), "path": dec.args[0].value, "line": node.lineno, "handler": node.name})
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1

    visit_FunctionDef = _definition
    visit_AsyncFunctionDef = _definition

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.current_class.append(node.name)
        self.generic_visit(node)
        self.current_class.pop()

    def visit_Call(self, node: ast.Call) -> None:
        direct_name = isinstance(node.func, ast.Name)
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            name = "<dynamic>"
        self.calls[name] += 1
        if (direct_name and name in {"eval", "exec", "compile"}) or name in {"system", "Popen"}:
            self.dynamic_execution.append({"name": name, "line": node.lineno})
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"})
        if broad:
            self.broad_excepts.append(node.lineno)
            meaningful = [n for n in node.body if not isinstance(n, (ast.Pass, ast.Continue))]
            if not meaningful:
                self.silent_excepts.append(node.lineno)
        self.generic_visit(node)


def audit() -> dict:
    source_files = files()
    known = {rel(p) for p in source_files}
    module_map = {py_module(p): rel(p) for p in source_files if p.suffix == ".py"}
    graph = nx.DiGraph()
    findings: list[dict] = []
    facts_by_file: dict[str, dict] = {}
    backend_routes: list[dict] = []
    frontend_paths: list[dict] = []
    frontend_api_refs: list[dict] = []

    config_text = (ROOT / "frontend" / "src" / "config.js").read_text(encoding="utf-8", errors="ignore")
    api_endpoint_map: dict[tuple[str, str], str] = {}
    for object_name, body in re.findall(r"const\s+([A-Z_]+)_ENDPOINTS\s*=\s*\{(.*?)\n\};", config_text, re.DOTALL):
        words = object_name.lower().split("_")
        group = words[0] + "".join(word.title() for word in words[1:])
        group = {"report": "reports", "recommendation": "recommendations"}.get(group, group)
        for key, endpoint in re.findall(r"(\w+)\s*:\s*[^\n]*?['\"](/[^'\"]+)['\"]", body):
            api_endpoint_map[(group, key)] = endpoint

    for path in source_files:
        name = rel(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.count("\n") + (1 if text else 0)
        graph.add_node(name, language=path.suffix.lower(), lines=lines, test=is_test(path))
        if not text.strip():
            if path.name == "__init__.py":
                continue
            findings.append({"severity": "medium", "kind": "empty_source_file", "file": name, "line": 1})
            continue
        if lines > 1500:
            findings.append({"severity": "high", "kind": "oversized_file", "file": name, "line": 1, "detail": f"{lines} lines"})
        elif lines > 700:
            findings.append({"severity": "medium", "kind": "large_file", "file": name, "line": 1, "detail": f"{lines} lines"})

        if path.suffix == ".py":
            try:
                tree = ast.parse(text, filename=name)
            except SyntaxError as exc:
                findings.append({"severity": "critical", "kind": "python_syntax_error", "file": name, "line": exc.lineno or 1, "detail": exc.msg})
                continue
            facts = PythonFacts()
            facts.visit(tree)
            for module, level, import_kind in facts.imports:
                target = resolve_python_import(path, module, level, module_map)
                if target and target != name:
                    graph.add_edge(name, target, kind=import_kind)
            for definition in facts.definitions:
                if definition["complexity_proxy"] >= 35:
                    findings.append({"severity": "high", "kind": "high_complexity_function", "file": name, **definition})
                elif definition["complexity_proxy"] >= 20:
                    findings.append({"severity": "medium", "kind": "complex_function", "file": name, **definition})
                if definition["end_line"] - definition["line"] + 1 > 250:
                    findings.append({"severity": "high", "kind": "oversized_function", "file": name, **definition})
            for line in facts.broad_excepts:
                findings.append({"severity": "low", "kind": "broad_exception", "file": name, "line": line})
            for line in facts.silent_excepts:
                findings.append({"severity": "medium", "kind": "silent_exception", "file": name, "line": line})
            for item in facts.dynamic_execution:
                findings.append({"severity": "high", "kind": "dynamic_execution", "file": name, **item})
            for route in facts.routes:
                backend_routes.append({"file": name, **route})
            facts_by_file[name] = {
                "definitions": len(facts.definitions), "broad_excepts": len(facts.broad_excepts),
                "routes": len(facts.routes), "top_calls": facts.calls.most_common(10),
            }
        else:
            imports = re.findall(
                r"(?:"
                r"import\s+(?:[^;]*?\s+from\s+)?"
                r"|export\s+(?:[^;]*?\s+from\s+)"
                r"|import\s*\("
                r"|require\s*\("
                r")\s*['\"]([^'\"]+)['\"]",
                text,
            )
            for spec in imports:
                target = js_target(path, spec, known)
                if target and target != name:
                    graph.add_edge(name, target, kind="import")
            for match in re.finditer(r"(?:fetch|axios\.(?:get|post|put|delete|patch)|apiClient\.(?:get|post|put|delete|patch))\s*\(\s*[`'\"]([^`'\"]+)", text):
                frontend_paths.append({"file": name, "line": text[:match.start()].count("\n") + 1, "path": match.group(1)})
            for match in re.finditer(r"\bAPI\.(\w+)\.(\w+)\b", text):
                endpoint = api_endpoint_map.get((match.group(1), match.group(2)))
                if endpoint:
                    frontend_api_refs.append({
                        "file": name,
                        "line": text[:match.start()].count("\n") + 1,
                        "path": endpoint,
                        "reference": match.group(0),
                    })
            hooks = len(re.findall(r"\buse(?:State|Effect|Memo|Callback|Reducer|Context|Ref)\s*\(", text))
            if hooks > 25:
                findings.append({"severity": "medium", "kind": "stateful_component_hotspot", "file": name, "line": 1, "detail": f"{hooks} React hooks"})

        for match in re.finditer(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?", text):
            findings.append({"severity": "low", "kind": "hardcoded_local_url", "file": name, "line": text[:match.start()].count("\n") + 1, "detail": match.group(0)})

    def normalized_route(path_value: str) -> str:
        return re.sub(r"\{[^}]+\}", "{param}", path_value.split("?", 1)[0])

    routes_by_path: dict[str, list[dict]] = defaultdict(list)
    for route in backend_routes:
        routes_by_path[normalized_route(route["path"])].append(route)
    api_edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    for reference in frontend_api_refs:
        for route in routes_by_path.get(normalized_route(reference["path"]), []):
            api_edges[(reference["file"], route["file"])].add(reference["path"])
    for (source, target), endpoints in api_edges.items():
        graph.add_edge(source, target, kind="api_call", endpoints=sorted(endpoints))

    app_graph = graph.subgraph([n for n, d in graph.nodes(data=True) if not d["test"]]).copy()
    import_time_graph = nx.DiGraph(
        (source, target, attrs)
        for source, target, attrs in app_graph.edges(data=True)
        if attrs.get("kind") != "lazy_import"
    )
    import_time_graph.add_nodes_from(app_graph.nodes(data=True))
    cycles = [sorted(c) for c in nx.strongly_connected_components(import_time_graph) if len(c) > 1]
    for cycle in cycles:
        findings.append({"severity": "medium", "kind": "module_dependency_cycle", "file": cycle[0], "line": 1, "detail": cycle})

    test_nodes = {n for n, d in graph.nodes(data=True) if d["test"]}
    covered = {target for test in test_nodes for target in nx.descendants(graph, test) if target not in test_nodes}
    orphans = [n for n in app_graph if app_graph.in_degree(n) == 0 and app_graph.out_degree(n) == 0]
    hubs = sorted(
        ({"file": n, "in_degree": app_graph.in_degree(n), "out_degree": app_graph.out_degree(n), "lines": app_graph.nodes[n]["lines"]} for n in app_graph),
        key=lambda x: x["in_degree"] + x["out_degree"], reverse=True,
    )[:30]
    untested_hubs = [h for h in hubs if h["file"] not in covered and not is_test(ROOT / h["file"])]
    for hub in untested_hubs[:15]:
        findings.append({"severity": "medium", "kind": "untested_dependency_hub", "file": hub["file"], "line": 1, "detail": hub})

    route_paths = {r["path"] for r in backend_routes}
    normalized_frontend = set()
    for item in frontend_paths:
        path = re.sub(r"\$\{[^}]+\}", "{param}", item["path"].split("?", 1)[0])
        if path.startswith("/"):
            normalized_frontend.add(path)
    duplicate_routes = defaultdict(list)
    for route in backend_routes:
        duplicate_routes[(route["method"], route["path"])].append(route)
    for key, definitions in duplicate_routes.items():
        if len(definitions) > 1:
            findings.append({"severity": "low", "kind": "duplicate_route_candidate", "file": definitions[0]["file"], "line": definitions[0]["line"], "detail": {"route": key, "definitions": definitions, "note": "Router prefixes require runtime validation"}})

    stale_refs = []
    for path in repository_files(SOURCE_SUFFIXES | {".bat", ".md", ".json"}):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "ontology_agentic" in text:
            stale_refs.append({"file": rel(path), "lines": [i for i, line in enumerate(text.splitlines(), 1) if "ontology_agentic" in line][:20]})

    # Rank architecture significance using complementary NetworkX algorithms.
    for source, target, attrs in app_graph.edges(data=True):
        attrs["weight"] = 1.5 if attrs.get("kind") == "api_call" else 0.6 if attrs.get("kind") == "lazy_import" else 1.0
    undirected = app_graph.to_undirected()
    pagerank = nx.pagerank(app_graph, weight="weight") if app_graph else {}
    betweenness = nx.betweenness_centrality(app_graph, normalized=True, weight=None) if app_graph else {}
    core = nx.core_number(undirected) if undirected.number_of_nodes() else {}
    communities = list(nx.community.greedy_modularity_communities(undirected, weight="weight")) if undirected.number_of_edges() else [set(undirected.nodes())]
    community_by_node = {
        node: index for index, members in enumerate(communities, 1) for node in members
    }
    cycle_nodes = {node for cycle in cycles for node in cycle}
    finding_weight = Counter()
    severity_weight = {"critical": 4.0, "high": 3.0, "medium": 1.5, "low": 0.5}
    for finding in findings:
        finding_weight[finding["file"]] += severity_weight.get(finding["severity"], 1.0)

    def normalized(values: dict[str, float]) -> dict[str, float]:
        maximum = max(values.values(), default=0.0)
        return {key: (value / maximum if maximum else 0.0) for key, value in values.items()}

    degree = {node: app_graph.in_degree(node) + app_graph.out_degree(node) for node in app_graph}
    page_norm = normalized(pagerank)
    between_norm = normalized(betweenness)
    degree_norm = normalized(degree)
    core_norm = normalized(core)
    line_norm = normalized({node: app_graph.nodes[node].get("lines", 0) for node in app_graph})
    finding_norm = normalized(dict(finding_weight))
    ranking = []
    for node in app_graph:
        centrality = 100.0 * (
            0.35 * page_norm.get(node, 0.0)
            + 0.35 * between_norm.get(node, 0.0)
            + 0.20 * degree_norm.get(node, 0.0)
            + 0.10 * core_norm.get(node, 0.0)
        )
        priority = min(100.0,
            0.45 * centrality
            + 20.0 * line_norm.get(node, 0.0)
            + 20.0 * finding_norm.get(node, 0.0)
            + (10.0 if node not in covered and degree.get(node, 0) >= 5 else 0.0)
            + (5.0 if node in cycle_nodes else 0.0)
        )
        role = "isolated" if degree[node] == 0 else "bridge" if between_norm.get(node, 0) >= 0.35 else "hub" if degree_norm.get(node, 0) >= 0.35 else "leaf" if degree[node] == 1 else "module"
        metrics = {
            "file": node,
            "rank_score": round(centrality, 3),
            "streamline_priority": round(priority, 3),
            "pagerank": round(pagerank.get(node, 0.0), 8),
            "betweenness": round(betweenness.get(node, 0.0), 8),
            "in_degree": app_graph.in_degree(node),
            "out_degree": app_graph.out_degree(node),
            "core_number": core.get(node, 0),
            "community": community_by_node.get(node, 0),
            "architecture_role": role,
            "covered_by_test_graph": node in covered,
            "in_cycle": node in cycle_nodes,
            "finding_weight": round(finding_weight.get(node, 0.0), 2),
        }
        ranking.append(metrics)
        graph.nodes[node].update({key: value for key, value in metrics.items() if key != "file"})
    ranking.sort(key=lambda item: (-item["streamline_priority"], -item["rank_score"], item["file"]))

    backbone_nodes = {item["file"] for item in ranking[:40]}
    backbone_nodes.update(cycle_nodes)
    for members in communities:
        if len(members) < 2:
            continue
        candidates = [item for item in ranking if item["file"] in members]
        backbone_nodes.update(item["file"] for item in candidates[:1])
    for source, target, attrs in graph.edges(data=True):
        if attrs.get("kind") == "api_call":
            backbone_nodes.update((source, target))
    for node in graph:
        graph.nodes[node]["backbone"] = node in backbone_nodes

    community_summary = []
    for index, members in enumerate(communities, 1):
        ranked_members = sorted(
            (item for item in ranking if item["file"] in members),
            key=lambda item: (-item["rank_score"], item["file"]),
        )
        community_summary.append({
            "id": index,
            "size": len(members),
            "leader": ranked_members[0]["file"] if ranked_members else None,
            "members": sorted(members),
        })

    recommendations = []
    for item in ranking[:30]:
        reasons = []
        if item["architecture_role"] in {"hub", "bridge"}: reasons.append(item["architecture_role"])
        if app_graph.nodes[item["file"]].get("lines", 0) > 700: reasons.append("large file")
        if not item["covered_by_test_graph"] and degree.get(item["file"], 0) >= 5: reasons.append("untested dependency hub")
        if item["in_cycle"]: reasons.append("dependency cycle")
        if item["finding_weight"] >= 3: reasons.append("concentrated findings")
        if reasons:
            recommendations.append({"file": item["file"], "priority": item["streamline_priority"], "reasons": reasons})

    finding_counts = Counter((f["severity"], f["kind"]) for f in findings)
    return {
        "summary": {
            "source_files": len(source_files), "application_files": len(app_graph), "test_files": len(test_nodes),
            "dependency_edges": graph.number_of_edges(), "module_cycles": len(cycles), "orphan_files": len(orphans),
            "backend_routes": len(backend_routes), "frontend_literal_api_calls": len(frontend_paths),
            "test_reachable_application_files": len(covered), "findings": len(findings),
        },
        "finding_counts": [{"severity": s, "kind": k, "count": c} for (s, k), c in sorted(finding_counts.items())],
        "findings": sorted(findings, key=lambda f: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f["severity"], 9), f["file"], f.get("line", 0))),
        "graph": {
            "nodes": [{"id": name, **attrs} for name, attrs in sorted(graph.nodes(data=True))],
            "edges": [
                {"source": source, "target": target, **attrs}
                for source, target, attrs in sorted(graph.edges(data=True))
            ],
            "hubs": hubs, "cycles": cycles, "orphans": orphans, "untested_hubs": untested_hubs,
            "analysis": {
                "algorithm": "PageRank + betweenness + degree + k-core + greedy modularity",
                "ranking": ranking,
                "communities": community_summary,
                "backbone_node_count": len(backbone_nodes),
                "recommendations": recommendations,
            },
        },
        "api": {"backend_routes": backend_routes, "frontend_literal_calls": frontend_paths, "frontend_configured_calls": frontend_api_refs, "backend_route_paths": sorted(route_paths), "frontend_literal_paths": sorted(normalized_frontend)},
        "stale_agentic_references": stale_refs,
        "files": facts_by_file,
    }


if __name__ == "__main__":
    report = audit()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {OUTPUT}")
