from tools import code_graph_audit


def test_code_audit_emits_a_resolved_hierarchy_with_javascript_symbols(tmp_path, monkeypatch):
    # A unit test must not crawl installed wheels or depend on the current checkout size.
    source = tmp_path / 'frontend' / 'src'
    source.mkdir(parents=True)
    (source / 'config.js').write_text('export const endpoint = "/api/v1/items";\n', encoding='utf-8')
    (source / 'App.js').write_text('import { endpoint } from "./config";\nexport function App() { return endpoint; }\n', encoding='utf-8')
    monkeypatch.setattr(code_graph_audit, 'ROOT', tmp_path)
    report = code_graph_audit.audit()
    hierarchy = report['hierarchy']
    node_ids = {node['id'] for node in hierarchy['nodes']}
    assert report['summary']['source_files'] == 2
    assert hierarchy['root'] in node_ids
    assert all(edge['source'] in node_ids and edge['target'] in node_ids for edge in hierarchy['edges'])
    assert any(node['type'] == 'function' and node.get('path', '').endswith('App.js') for node in hierarchy['nodes'])
    assert any(edge['source'] == 'frontend/src/App.js' and edge['target'] == 'frontend/src/config.js'
               for edge in report['graph']['edges'])
