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
    (g / "finalists.json").write_text(json.dumps(["NaiveTitForTatNegotiator", ":notext"]))
    pool = session_agent_override({"group": "finalists"})
    assert pool[0] == "NaiveTitForTatNegotiator" and "LinearTBNegotiator" in pool


def test_file_spec(tmp_path, monkeypatch):
    (tmp_path / "mine.py").write_text("from negmas.sao import AspirationNegotiator\nclass Mine(AspirationNegotiator):\n    pass\n")
    monkeypatch.chdir(tmp_path)
    assert get_agent_type("file:mine.Mine").__name__ == "Mine"


def test_make_agent_wraps_and_refuses_none_accept():
    a = make_agent("helpers.AgentK", {"name": "x"}, practice=True)
    assert type(a).__name__.startswith("NoEnd_NoAcceptNone_")
