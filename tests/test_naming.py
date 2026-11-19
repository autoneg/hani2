"""With the Assistant, "human" and "agent" values are shown as "You" and "Opponent"."""

import json

from hani2.naming import relabel_components, relabel_text
from hani2.testing import make_session
from hani2.tools import ui


M = {"human": "You", "agent": "Opponent"}


def test_relabel_helpers():
    assert relabel_text("Compass=agent, Food = human; agentic", M) == "Compass=Opponent, Food = You; agentic"
    comps = [ui.card(ui.table([{"Compass": "agent", "U": 0.5}], on_select="pick"),
                     ui.select("who", ["agent", "human"], "agent"), ui.stat("Holder", "human"),
                     ui.button("Go", "agent"))]
    out = relabel_components(comps, M)
    card = out[0]["children"]
    assert card[0]["rows"][0]["Compass"] == "Opponent"
    assert [o["label"] for o in card[1]["options"]] == ["Opponent", "You"]
    assert [o["value"] for o in card[1]["options"]] == ["agent", "human"] and card[1]["value"] == "agent"
    assert card[2]["value"] == "You" and card[3]["action"] == "agent"
    assert comps[0]["children"][0]["rows"][0]["Compass"] == "agent"  # input untouched


def test_island_with_assistant_shows_you_and_opponent(hani2_home):
    s = make_session(scenario_type="Island")
    assert s.labels == M
    snap = s.snapshot()
    issue = snap["scenario"]["issues"][0]
    assert issue["values"] == ["agent", "human"] and issue["labels"] == {"agent": "Opponent", "human": "You"}
    assert snap["scenario"]["role"] == "" and snap["scenario"]["opponent_role"] == ""
    s.start()
    s.wait_for_turn()
    first = s.issues[0].name
    assert s.set_draft({first: "Opponent"})["ok"] and s.draft[first] == "agent"  # labels map back
    ctx = s.context()
    assert set(ctx["issues"][0]["values"]) == {"Opponent", "You"} and "names" in ctx
    assert all(v in ("You", "Opponent") for v in (ctx["partner_offer"] or {}).values())
    sel = next(t for t in s.tools if t.name == "Utility-based Selector")
    view = json.dumps(s.render_tool(s.tool_state(sel)["id"]))
    assert '"agent"' not in view.replace('"value": "agent"', "") and "Opponent" in view
    s.end()
    s.wait_until_done()
    import csv

    rows = list(csv.DictReader(open(hani2_home / "db" / "tester" / "results.csv")))
    assert "Opponent" not in rows[-1].get("agreement", "") and "You" not in rows[-1].get("agreement", "")


def test_no_relabelling_without_a_support_agent(hani2_home):
    s = make_session(scenario_type="Island", support_settings={"mode": "off"})
    assert s.support_agent is None and s.labels == {}
    assert "labels" not in s.snapshot()["scenario"]["issues"][0]


def test_names_can_be_configured(hani2_home):
    env = hani2_home / "settings" / "env.json"
    data = json.loads(env.read_text()) if env.exists() else {}
    data["names"] = {"apply": "always", "self": "Me", "opponent": "Them"}
    env.parent.mkdir(parents=True, exist_ok=True)
    env.write_text(json.dumps(data))
    s = make_session(scenario_type="Island", support_settings={"mode": "off"})
    assert s.labels == {"human": "Me", "agent": "Them"}


def test_results_keep_the_scenarios_own_values(hani2_home):
    import csv

    s = make_session(scenario_type="Island")
    s.start()
    s.wait_for_turn()
    assert s.accept()
    assert s.wait_until_done() and s.result["status"] == "success"
    assert "You" in (s.snapshot()["result"]["agreement_str"] or "") or "Opponent" in (s.snapshot()["result"]["agreement_str"] or "") \
        or s.snapshot()["result"]["agreement_str"]
    rows = list(csv.DictReader(open(hani2_home / "db" / "tester" / "results.csv")))
    agreement = rows[-1]["agreement"]
    assert ("agent" in agreement or "human" in agreement) and "Opponent" not in agreement and "You" not in agreement


def test_only_scenarios_with_side_words_are_relabelled(hani2_home):
    s = make_session(scenario_type="Trade")
    assert s.support_agent is not None and s.labels == {}


def test_scenario_info_uses_the_names(hani2_home):
    s = make_session(scenario_type="Island")
    info = next(t for t in s.tools if t.name == "Scenario Info")
    text = json.dumps(s.render_tool(s.tool_state(info)["id"]))
    import re

    assert not re.search(r"\b(human|agent)\b", text.replace('"value": "agent"', "")), re.findall(r".{30}\b(?:human|agent)\b.{10}", text)[:3]


def test_snapshot_names_both_roles(hani2_home):
    s = make_session()
    sc = s.snapshot()["scenario"]
    you = str(s.ss.get("human_id", "")).replace(" (You)", "")
    assert sc["role"] == you and sc["opponent_role"] == s.opponent_ufun.name and sc["opponent_role"] != you
