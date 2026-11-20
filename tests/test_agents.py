import json

from hani2.agents import expand_agents, get_agent_type, make_agent, session_agent_override


def test_groups_expand_and_dedupe():
    pool = expand_agents(":notext,BoulwareTBNegotiator,helpers.AgentK")
    assert pool[0] == "BoulwareTBNegotiator" and pool.count("BoulwareTBNegotiator") == 1
    assert "helpers.AgentK" in pool


def test_query_override_and_group_file(hani2_home):
    assert session_agent_override({"agents": "AspirationNegotiator"}) == ["AspirationNegotiator"]
    g = hani2_home / "db" / "groups"
    g.mkdir(parents=True)
    (g / "finalists.json").write_text(json.dumps(["NaiveTitForTatNegotiator", ":notext"]), encoding="utf-8")
    pool = session_agent_override({"group": "finalists"})
    assert pool[0] == "NaiveTitForTatNegotiator" and "LinearTBNegotiator" in pool


def test_file_spec(tmp_path, monkeypatch):
    (tmp_path / "mine.py").write_text("from negmas.sao import AspirationNegotiator\nclass Mine(AspirationNegotiator):\n    pass\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert get_agent_type("file:mine.Mine").__name__ == "Mine"


def test_make_agent_wraps_and_refuses_none_accept():
    a = make_agent("helpers.AgentK", {"name": "x"}, practice=True)
    assert type(a).__name__.startswith("NoEnd_NoAcceptNone_")


def test_han_groups_when_installed():
    import pytest

    pytest.importorskip("han_agents")
    from hani2 import agents, groups

    years = agents.han_years()
    assert years
    y = years[-1]
    keys = {g["key"] for g in groups.list_groups(groups.OPPONENT)}
    for kind in ("all", "qualified", "finalists", "winners"):
        assert f"han{y}-{kind}" in keys
    every = agents.resolve_agent_group(f"han{y}-all")
    finalists = agents.session_agent_override({"group": f"han{y}-finalists"}) or []
    assert every and set(finalists) <= set(every)
    assert set(agents.expand_agents(f":han{y}-qualified")) <= set(every)
    # an empty group (no winners yet) is still a known group
    assert agents._builtin_known(f":han{y}-winners")


def test_han_groups_without_package(monkeypatch):
    import sys

    from hani2 import agents

    monkeypatch.setitem(sys.modules, "han_agents", None)
    monkeypatch.setitem(sys.modules, "han_agents.registry", None)
    assert agents.han_years() == [] and agents.han_groups() == {}


def test_url_file_specs_need_an_admin(tmp_path, monkeypatch):
    """?opponents=file:... from a browser must not make the server import a .py file for a non-admin."""
    from hani2.agents import session_agent_override

    marker = tmp_path / "ran.txt"
    (tmp_path / "evil.py").write_text(f"open({str(marker)!r}, 'w').write('x')\nclass X: pass\n", encoding="utf-8")
    q = {"opponents": f"file:{tmp_path / 'evil'}.X,BoulwareTBNegotiator"}
    specs = session_agent_override(q, allow_files=False)
    assert specs and not any(str(s).startswith("file:") for s in specs)
    assert not marker.exists()
    assert any(str(s).startswith("file:") for s in session_agent_override(q))  # admins keep the feature
