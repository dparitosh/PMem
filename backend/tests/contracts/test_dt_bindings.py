import json
from pathlib import Path
from backend.agentic_service.dt_bindings import extend_catalog, capabilities


def test_all_roles_resolve_and_extension_is_idempotent():
    source = json.loads((Path(__file__).parents[2] / "agentic_service/catalog.json").read_text())
    catalog = extend_catalog(source)
    assert extend_catalog(catalog) == catalog
    tools = {tool["id"]: tool for tool in catalog["tools"]}
    roles = [agent for agent in catalog["agents"] if agent["id"].startswith("dt-")]
    assert len(roles) == 12
    for agent in roles:
        assert set(agent["tools"]) <= tools.keys()
        assert "data.product.publish" not in agent["tools"]
    assert tools["pipeline.run"]["mutates"] is True
    assert capabilities()["external_client_binding_required"] is True
