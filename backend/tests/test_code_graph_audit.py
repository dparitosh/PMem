from tools import code_graph_audit


def fixture_root(tmp_path, monkeypatch):
    config = tmp_path / 'frontend/src/config.js'
    config.parent.mkdir(parents=True)
    config.write_text('export const endpoint = "/api/v1/items";\n')
    monkeypatch.setattr(code_graph_audit, 'ROOT', tmp_path)


def test_literal_file_references_are_not_import_cycles(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    (tmp_path / 'a.py').write_text('other = "b.py"\n')
    (tmp_path / 'b.py').write_text('other = "a.py"\n')
    report = code_graph_audit.audit()
    assert report['summary']['module_cycles'] == 0
    assert any(e['source'] == 'a.py' and e['target'] == 'b.py' for e in report['graph']['edges'])


def test_eager_import_survives_later_lazy_import_and_reference(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    (tmp_path / 'a.py').write_text('import b\ndef later():\n    import b\nother = "b.py"\n')
    (tmp_path / 'b.py').write_text('import a\n')
    assert code_graph_audit.audit()['summary']['module_cycles'] == 1
    (tmp_path / 'a.py').write_text('def later():\n    import b\nother = "b.py"\n')
    assert code_graph_audit.audit()['summary']['module_cycles'] == 0


def test_complexity_finding_keeps_category_and_symbol_type(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    (tmp_path / 'a.py').write_text('def complex(value):\n' + '    if value:\n        pass\n' * 36)
    report = code_graph_audit.audit()
    finding = next(f for f in report['findings'] if f['kind'] == 'high_complexity_function')
    assert finding['symbol_kind'] == 'function'
    assert finding['file'] == 'a.py' and finding['line'] == 1


def test_main_only_import_is_not_module_initialization_cycle(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    (tmp_path / 'a.py').write_text('if __name__ == "__main__":\n    import b\n')
    (tmp_path / 'b.py').write_text('import a\n')
    report = code_graph_audit.audit()
    assert report['summary']['module_cycles'] == 0
    assert any(e['source'] == 'a.py' and e['kind'] == 'entrypoint_import' for e in report['graph']['edges'])


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
