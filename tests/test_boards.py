"""Leaderboards of projects and studies (hani2.evaluation.boards): which games count, sorting and the
options a viewer may use, strata and rows from other projects, the leaderboard block's checks, the
API (visibility, tokens, 400 for options not allowed) and the evaluation cache."""

import csv
import itertools
import json
import time

import pytest
from conftest import write_settings
from fastapi.testclient import TestClient

from hani2 import projects, sso
from hani2.evaluation import boards, eval_cache
from hani2.projects import StudyRef

SECRET = "test-secret-0123456789abcdef"
A, B, C = "teamA.helper:Helper", "teamB.coach:Coach", "teamC.pal:Pal"
_ids = itertools.count()


def row(user, spec, adv, *, entrant=None, scenario="s1", opponent="Boulware", day=1, **kw):
    """An evaluation row as the cache gives it (only what boards read)."""
    return {"id": f"r{next(_ids)}", "user": user, "scenario": scenario, "opponent": opponent, "support_agent": spec,
            "assistant": spec, "assistant_entrant": entrant, "status": "success", "agreement": 1.0,
            "human_advantage": adv, "started": f"2027-03-{day:02d}T10:00:00+00:00", "practice": False,
            "counted": True, "mode": None, **kw}


def paired(m, u1, s1, a1, u2, s2, a2, *, scenario="s1", day=1, **kw):
    """The two rows of one Paired match."""
    common = dict(match_id=m, opponent_kind="human+assistant", study_mode="paired", scenario=scenario, day=day,
                  opponent="human", **kw)
    return [row(u1, s1, a1, side=0, opponent_user=u2, **common), row(u2, s2, a2, side=1, opponent_user=u1, **common)]


@pytest.fixture
def hi(hani2_home, monkeypatch):
    """A project HI with a study play; its rows come from ``ROWS`` (by study)."""
    projects.create_project("HI", kind="assistant", year=2027)
    projects.create_study("HI/play", type="online")
    rows: dict[str, list[dict]] = {}

    def fake(ref):
        return [dict(r, _study=str(ref)) for r in rows.get(str(ref), [])], {"games": 0}

    monkeypatch.setattr(boards, "study_rows", fake)
    return rows


def set_board(block, project="HI", study=None):
    f = (projects.study_dir(StudyRef(project, study)) / projects.STUDY_FILE) if study else \
        projects.project_dir(project) / projects.PROJECT_FILE
    d = projects.read_yaml(f)
    d["leaderboard"] = block
    projects.write_yaml(f, d)


RULES0 = {"min_games": 1, "min_participants": 1}


def names(out):
    return [e["entrant"] for e in out["entries"]]


# --------------------------------------------------------------------------- #
# Which games count (§8.1)                                                    #
# --------------------------------------------------------------------------- #
def test_the_game_rules(hi):
    set_board({"sort_options": ["utility"], "rules": RULES0})
    hi["HI/play"] = [
        row("u1", A, 0.8), row("u2", A, 0.6),
        row("u3", B, 0.4), row("u4", B, 0.2),
        row("u5", A, 0.0, practice=True),                         # practice
        row("admin", A, 0.0, counted=False),                       # an admin's or a test session
        row("sim_1", B, 1.0, mode="simulated"),                    # a simulated participant
        row("u6", B, 1.0, status="erred"),                         # a system failure
        *paired("m1", "u7", A, 0.9, "u8", B, 0.9, abandoned="opponent"),  # an abandoned match: both rows
    ]
    out = boards.board("HI", None, {}, n_boot=50)
    assert names(out) == ["teamA.helper:Helper", "teamB.coach:Coach"]
    a, b = out["entries"]
    assert a["rank"] == 1 and a["values"]["utility"]["mean"] > b["values"]["utility"]["mean"]
    assert a["games"] == {"all": 2, "people": 0, "ai": 2} and a["participants"] == 2
    assert a["label"] == "Helper" and a["assistant"] == A
    ex = out["excluded"]
    assert ex["practice"] == 1 and ex["admin or test session"] == 1 and ex["simulated participant"] == 1
    assert ex["system failure"] == 1 and ex["abandoned"] == 2
    # the abandon rate: the abandoned match's row among each Assistant's games
    assert a["abandon_rate"] == pytest.approx(1 / 3) and b["abandon_rate"] == pytest.approx(1 / 3)


def test_minimums_put_entrants_on_the_not_ranked_list(hi):
    set_board({"sort_options": ["utility"], "rules": {"min_games": 3, "min_participants": 2}})
    hi["HI/play"] = [row("u1", A, 0.5), row("u2", A, 0.5), row("u3", A, 0.5),      # ranked
                     row("u1", B, 0.9), row("u2", B, 0.9),                          # 2 games < 3
                     row("t1", C, 0.9, own_assistant=True), row("t1", C, 0.9, own_assistant=True),
                     row("u9", C, 0.9)]                                             # 1 non-owner < 2
    out = boards.board("HI", None, {}, n_boot=20)
    assert names(out) == [A]
    why = {u["entrant"]: u["reason"] for u in out["unranked"]}
    assert why == {B: "min_games", C: "min_participants"}
    assert {u["entrant"]: u["games"]["all"] for u in out["unranked"]} == {B: 2, C: 3}


def test_own_team_games_count_unless_excluded(hi):
    set_board({"sort_options": ["utility"], "rules": {**RULES0, "adjust": "balanced"}})
    hi["HI/play"] = [row("t1", A, 1.0, own_assistant=True), row("u1", A, 0.0, own_assistant=False)]
    assert boards.board("HI", None, {}, n_boot=0)["entries"][0]["values"]["utility"]["mean"] == pytest.approx(0.5)
    set_board({"sort_options": ["utility"], "rules": {**RULES0, "exclude_own": True, "adjust": "balanced"}})
    out = boards.board("HI", None, {}, n_boot=0)
    assert out["entries"][0]["values"]["utility"]["mean"] == pytest.approx(0.0)
    assert out["excluded"]["own team"] == 1


def test_caps_drop_the_latest_games(hi):
    set_board({"sort_options": ["utility"], "rules": {**RULES0, "max_games_per_participant": 2, "adjust": "balanced"}})
    hi["HI/play"] = [row("u1", A, 1.0, day=1), row("u1", A, 1.0, day=2), row("u1", A, 0.0, day=3),
                     row("u2", A, 1.0, day=4)]
    out = boards.board("HI", None, {}, n_boot=0)
    assert out["excluded"]["cap"] == 1 and out["entries"][0]["values"]["utility"]["mean"] == pytest.approx(1.0)
    # per pair: the same two people's matches
    set_board({"sort_options": ["utility"], "rules": {**RULES0, "max_games_per_pair": 1, "adjust": "balanced"}})
    hi["HI/play"] = [*paired("m1", "u1", A, 0.9, "u2", B, 0.1, day=1), *paired("m2", "u2", B, 0.9, "u1", A, 0.1, day=2),
                     *paired("m3", "u3", A, 0.5, "u2", B, 0.5, day=3)]
    out = boards.board("HI", None, {}, n_boot=0)
    assert out["excluded"]["cap"] == 2  # m2's two rows
    e = {x["entrant"]: x for x in out["entries"]}
    assert e[A]["values"]["utility"]["mean"] == pytest.approx(0.7) and e[A]["games"]["people"] == 2


def test_guests_count_for_the_inviters_assistant_and_no_name_is_shown(hi):
    set_board({"sort_options": ["utility"], "columns": ["utility", "games", "participants", "guests"],
               "rules": RULES0})
    hi["HI/play"] = [row("anac_17", A, 0.5, entrant="sub_0412", own_assistant=True),
                     row("anac_g1", A, 0.7, entrant="sub_0412", invited_by="anac_17", own_assistant=False),
                     row("anac_g2", A, 0.9, entrant="sub_0412", invited_by="anac_17", own_assistant=False),
                     *paired("m9", "anac_31", B, 0.4, "anac_32", A, 0.6, entrant=None)]
    out = boards.board("HI", None, {}, n_boot=30)
    e = {x["entrant"]: x for x in out["entries"]}
    assert e["sub_0412"]["guests"] == 2 and e["sub_0412"]["participants"] == 3
    assert e["sub_0412"]["assistant"] == A  # the entrant id, and the spec beside it
    text = json.dumps(out)
    for secret in ("anac_17", "anac_g1", "anac_g2", "anac_31", "anac_32", "opponent_user", "invited_by",
                   "opponent_participant"):
        assert secret not in text, secret


def test_same_assistant_games_leave_utility_and_count_once_elsewhere(hi):
    set_board({"sort_options": ["utility", "agreement"], "rules": {**RULES0, "adjust": "balanced"}})
    hi["HI/play"] = [*paired("m1", "u1", A, 1.0, "u2", A, 0.0, agreement=1.0),  # an inviter against their guest
                     row("u3", A, 0.2, agreement=0.0)]
    out = boards.board("HI", None, {"sort": "utility"}, n_boot=0)
    a = out["entries"][0]
    assert a["values"]["utility"]["mean"] == pytest.approx(0.2)        # left out of utility
    out = boards.board("HI", None, {"sort": "agreement"}, n_boot=0)
    # agreement: the match once (mean of its rows: 1.0) and the AI game (0.0), in different cells
    assert out["entries"][0]["values"]["agreement"]["mean"] == pytest.approx(0.5)


def test_relative_means_stay_on_the_values_scale(hi):
    set_board({"sort_options": ["utility"], "rules": RULES0})  # adjust: relative is the default
    hi["HI/play"] = [row("u1", A, 0.8, scenario="s1"), row("u2", B, 0.6, scenario="s1"),
                     row("u3", A, 0.4, scenario="s2"), row("u4", B, 0.2, scenario="s2")]
    out = boards.board("HI", None, {}, n_boot=0)
    e = {x["entrant"]: x["values"]["utility"]["mean"] for x in out["entries"]}
    assert e[A] == pytest.approx(0.6) and e[B] == pytest.approx(0.4)  # grand mean 0.5, ±0.1
    assert any("cell-adjusted" in n for n in out["notes"])


def test_a_lower_is_better_criterion_ranks_upwards(hi):
    set_board({"sort_options": ["utility", "n_offers"], "rules": {**RULES0, "adjust": "balanced"}})
    # n_offers has no direction in the catalogue: it cannot be a sort option
    with pytest.raises(ValueError):
        projects.check_file_data({"leaderboard": {"sort_options": ["n_offers"]}}, "defaults", project="HI")
    hi["HI/play"] = [row("u1", A, 0.5, irrational_accept=1.0), row("u2", B, 0.5, irrational_accept=0.0)]
    set_board({"sort_options": ["irrational_accept"], "rules": {**RULES0, "adjust": "balanced"}})
    out = boards.board("HI", None, {}, n_boot=0)
    assert names(out) == [B, A] and out["options"]["sort"][0]["direction"] == "lower"


# --------------------------------------------------------------------------- #
# Sorting and switches: what end users and admins may ask for                  #
# --------------------------------------------------------------------------- #
def test_options_and_400_for_values_not_allowed(hi):
    set_board({"sort_options": ["utility", "agreement"], "default_sort": "utility",
               "user_options": {"games": ["all", "people", "ai"]}, "rules": RULES0})
    hi["HI/play"] = [row("u1", A, 0.5), *paired("m1", "u2", A, 0.9, "u3", B, 0.1)]
    out = boards.board("HI", None, {}, n_boot=0)
    o = out["options"]
    assert [x["key"] for x in o["sort"]] == ["utility", "agreement"]
    assert o["sort"][0]["kind"] == "score" and o["sort"][1] == {**o["sort"][1], "kind": "criterion", "direction": "higher"}
    assert o["games"] == ["all", "people", "ai"] and "stratum" not in o and "window" not in o
    assert o["defaults"] == {"sort": "utility", "games": "all", "stratum": "combined", "window": "all"}
    for bad in ({"sort": "hi_team"}, {"stratum": "paired"}, {"window": "last_30_days"}, {"games": "bots"},
                {"colour": "red"}):
        with pytest.raises(boards.BoardError):
            boards.board("HI", None, bad, n_boot=0)
    # the default value of a switch that is not offered is accepted
    assert boards.board("HI", None, {"stratum": "combined"}, n_boot=0)["query"]["stratum"] == "combined"
    # admins may sort by any enabled score or criterion, with any switch value
    out = boards.board("HI", None, {"sort": "hi_team", "stratum": "paired", "window": "last_7_days"}, admin=True,
                       n_boot=0, now=__import__("datetime").datetime(2027, 3, 3, tzinfo=__import__("datetime").timezone.utc))
    assert out["query"]["sort"] == "hi_team" and "paired" in out["options"]["stratum"]
    # games: people / ai
    people = boards.board("HI", None, {"games": "people"}, n_boot=0)
    assert {e["entrant"]: e["games"]["all"] for e in people["entries"]} == {A: 2, B: 1}
    ai = boards.board("HI", None, {"games": "ai"}, n_boot=0)
    assert names(ai) == [A] and ai["entries"][0]["values"]["utility"]["mean"] == pytest.approx(0.5)


def test_the_window_switch(hi):
    from datetime import datetime, timezone

    set_board({"sort_options": ["utility"], "user_options": {"window": ["all", "last_7_days"]}, "rules": RULES0})
    hi["HI/play"] = [row("u1", A, 0.5, day=1), row("u2", B, 0.5, day=20)]
    now = datetime(2027, 3, 22, tzinfo=timezone.utc)
    assert set(names(boards.board("HI", None, {}, n_boot=0, now=now))) == {A, B}
    assert names(boards.board("HI", None, {"window": "last_7_days"}, n_boot=0, now=now)) == [B]


def test_hi_strata(hi):
    set_board({"sort_options": ["utility"], "user_options": {"stratum": ["combined", "solo", "paired"]},
               "rules": RULES0})
    hi["HI/play"] = [row("u1", A, 0.5), *paired("m1", "u2", B, 0.9, "u3", C, 0.1),
                     row("u4", B, 0.3, pairing="fallback", study_mode="paired")]  # a fallback is Solo
    solo = boards.board("HI", None, {"stratum": "solo"}, n_boot=0)
    assert set(names(solo)) == {A, B}
    pair = boards.board("HI", None, {"stratum": "paired"}, n_boot=0)
    assert set(names(pair)) == {B, C}
    assert len(boards.board("HI", None, {}, n_boot=0)["entries"]) == 3


def test_a_han_board_with_rows_from_an_hi_project(hi):
    projects.create_project("HAN", kind="opponent", year=2027)
    projects.create_study("HAN/play", type="online")
    set_board({"studies": ["play"], "include": [{"study": "HI/play", "stratum": "vs_team"}],
               "sort_options": ["utility"], "user_options": {"stratum": ["alone", "vs_team"]},
               "defaults": {"stratum": "alone"}, "rules": RULES0}, project="HAN")
    X, Y = "han.x:X", "han.y:Y"
    hi["HAN/play"] = [row("u1", "none", 0.3, opponent=X, assistant=None), row("u2", "none", 0.6, opponent=Y, assistant=None),
                      *paired("m1", "u3", "none", 0.5, "u4", "none", 0.5, assistant=None)]  # people only: no entrant
    hi["HI/play"] = [row("u5", A, 0.2, opponent=X, opponent_han_year=2027),
                     row("u6", A, 0.9, opponent="Boulware")]  # not a HAN agent: not taken in
    out = boards.board("HAN", None, {}, n_boot=0)
    assert out["track"] == "han" and set(names(out)) == {X, Y}
    assert "opponent" in out["entries"][0] and out["excluded"]["human opponent"] == 2
    vt = boards.board("HAN", None, {"stratum": "vs_team"}, n_boot=0)
    assert names(vt) == [X] and vt["entries"][0]["games"]["all"] == 1
    with pytest.raises(boards.BoardError):
        boards.board("HAN", None, {"stratum": "both"}, n_boot=0)


def test_study_board_overrides_the_project_key_by_key(hi):
    projects.create_study("HI/lab", type="lab")
    set_board({"sort_options": ["utility", "agreement"], "visibility": "public", "rules": {"min_games": 5}})
    set_board({"default_sort": "agreement", "rules": {"min_games": 1, "min_participants": 1}}, study="lab")
    hi["HI/lab"] = [row("u1", A, 0.5)]
    hi["HI/play"] = [row("u2", B, 0.5)]
    out = boards.board("HI", "lab", {}, n_boot=0)
    assert out["study"] == "lab" and out["query"]["sort"] == "agreement" and names(out) == [A]
    assert out["rules"]["min_games"] == 1 and out["rules"]["min_participants"] == 1 and out["visibility"] == "public"
    assert boards.visibility("HI", "lab") == "public"


def test_data_version_is_stable_and_changes_with_the_data(hi):
    set_board({"sort_options": ["utility"], "rules": RULES0})
    hi["HI/play"] = [row("u1", A, 0.5)]
    v1 = boards.board("HI", None, {}, n_boot=0)["data_version"]
    assert boards.board("HI", None, {}, n_boot=0)["data_version"] == v1
    assert v1.startswith("sha1:")


# --------------------------------------------------------------------------- #
# The block: checks on save and on load                                        #
# --------------------------------------------------------------------------- #
def test_the_block_is_checked(hi):
    p = projects.file_problems({"leaderboard": {"track": "x", "visibility": "friends", "colour": 1,
                                                "user_options": {"games": ["bots"], "mood": ["x"]},
                                                "defaults": {"window": "yesterday"},
                                                "rules": {"min_games": -1, "ci": 2, "adjust": "z", "cap": 1},
                                                "include": [{"study": "HI2027"}]}}, "defaults")
    text = " | ".join(p)
    for bit in ("track", "visibility", "colour", "'bots'", "mood", "yesterday", "min_games", "ci", "adjust",
                "unknown rule 'cap'", "<project>/<study>"):
        assert bit in text, bit
    # on save: keys must be enabled in every study the board reads, default_sort among the options
    with pytest.raises(ValueError, match="not enabled"):
        projects.check_file_data({"scores_enabled": ["utility"], "leaderboard": {"sort_options": ["hi_team"]}},
                                 "defaults", project="HI")
    with pytest.raises(ValueError, match="default_sort"):
        projects.check_file_data({"leaderboard": {"sort_options": ["utility"], "default_sort": "hi_team"}},
                                 "defaults", project="HI")
    with pytest.raises(ValueError, match="user_options.games"):
        projects.check_file_data({"leaderboard": {"user_options": {"games": ["all", "ai"]},
                                                  "defaults": {"games": "people"}}}, "defaults", project="HI")
    projects.check_file_data({"leaderboard": {"sort_options": ["utility", "agreement"]}}, "defaults", project="HI")
    # a study that disables a score the project's board sorts by is refused
    set_board({"sort_options": ["utility", "hi_team"]})
    with pytest.raises(ValueError, match="hi_team"):
        projects.check_file_data({"scores_enabled": ["utility"]}, "overrides", ref="HI/play")


def test_the_admin_api_refuses_a_bad_block(hi, monkeypatch):
    from hani2.server import app

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        p = c.get("/api/admin/projects/HI").json()
        data = {k: v for k, v in p.items() if k not in ("name", "editor")}
        data["leaderboard"] = {"sort_options": ["utility"], "default_sort": "hi_team"}
        r = c.put("/api/admin/projects/HI", json={"data": data})
        assert r.status_code == 400 and "default_sort" in r.text


# --------------------------------------------------------------------------- #
# The API                                                                      #
# --------------------------------------------------------------------------- #
@pytest.fixture
def api(hi, hani2_home):
    write_settings(hani2_home, "env.json", {"auth": {"sso": {"scmlweb": {"secret": SECRET}}}})
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c


def token(**kw):
    now = int(time.time())
    return sso.sign({"iss": "scmlweb", "aud": "hani2-api", "scope": "leaderboard:read", "iat": now,
                     "exp": now + 60, **kw}, SECRET)


def bearer(**kw):
    return {"Authorization": f"Bearer {token(**kw)}"}


URL = "/api/v1/projects/HI/leaderboard"


def test_visibility_and_tokens(api, hi):
    hi["HI/play"] = [row("u1", A, 0.5), row("u2", B, 0.4)]
    set_board({"sort_options": ["utility"], "visibility": "public", "rules": RULES0})
    assert api.get(URL).status_code == 200
    set_board({"sort_options": ["utility"], "visibility": "participants", "rules": RULES0})
    assert api.get(URL).status_code == 401
    assert api.get(URL, headers=bearer()).status_code == 200
    assert api.get(URL, headers=bearer(scope="other")).status_code == 403
    assert api.get(URL, headers={"Authorization": "Bearer nonsense"}).status_code == 401
    signin = sso.sign({"iss": "scmlweb", "aud": "hani2", "sub": "7", "iat": int(time.time()),
                       "exp": int(time.time()) + 60, "jti": "abcdefgh123"}, SECRET)
    assert api.get(URL, headers={"Authorization": f"Bearer {signin}"}).status_code == 401
    api.post("/api/auth/register", json={"username": "bob", "password": "bobpass1"})
    api.post("/api/auth/login", json={"username": "bob", "password": "bobpass1"})
    assert api.get(URL).status_code == 200
    set_board({"sort_options": ["utility"], "visibility": "admins", "rules": RULES0})
    assert api.get(URL).status_code == 403
    assert api.get(URL, headers=bearer()).status_code == 200
    api.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    assert api.get(URL).status_code == 200
    assert api.get("/api/v1/projects/nope/leaderboard").status_code == 404
    assert api.get("/api/v1/projects/HI/studies/nope/leaderboard").status_code == 404


def test_the_api_serves_the_same_board_and_400s(api, hi):
    hi["HI/play"] = [row("u1", A, 0.5), row("u2", B, 0.4), *paired("m1", "u3", A, 0.9, "u4", B, 0.1)]
    set_board({"sort_options": ["utility", "agreement"], "user_options": {"games": ["all", "people"]},
               "visibility": "public", "rules": RULES0})
    r = api.get(URL, params={"sort": "agreement", "games": "people"})
    assert r.status_code == 200
    d = r.json()
    page = boards.board("HI", None, {"sort": "agreement", "games": "people"})
    for k in ("schema", "project", "track", "query", "options", "columns", "scores", "rules", "entries",
              "unranked", "excluded", "data_version"):
        assert d[k] == json.loads(json.dumps(page[k])), k
    assert list(d)[:16] == ["schema", "project", "study", "track", "source", "generated_at", "data_version", "query",
                            "options", "columns", "scores", "rules", "entries", "unranked", "excluded", "warnings"]
    assert d["schema"] == "hani2.leaderboard/2" and d["study"] is None
    e = d["entries"][0]
    assert set(e) >= {"rank", "tied_with_leader", "entrant", "assistant", "label", "values", "games", "participants",
                      "guests", "ci_unit", "abandon_rate", "cost_usd"}
    assert set(e["values"]["agreement"]) == {"mean", "ci"} and set(e["games"]) == {"all", "people", "ai"}
    for bad in ({"sort": "hi_team"}, {"games": "ai"}, {"window": "last_30_days"}, {"x": "1"}):
        r = api.get(URL, params=bad)
        assert r.status_code == 400, bad
    # the same data gives the same ETag, and If-None-Match a 304
    r1 = api.get(URL)
    assert api.get(URL, headers={"If-None-Match": r1.headers["etag"]}).status_code == 304
    # a study board
    assert api.get("/api/v1/projects/HI/studies/play/leaderboard").json()["study"] == "play"


def test_the_list_of_boards(api, hi):
    projects.create_project("PRIV", kind="assistant")
    set_board({"sort_options": ["utility"], "visibility": "public"})
    set_board({"sort_options": ["utility"], "visibility": "admins"}, project="PRIV")
    d = api.get("/api/v1/leaderboards").json()
    assert [b["project"] for b in d["boards"]] == ["HI"]
    b = d["boards"][0]
    assert b["track"] == "hi" and b["year"] == 2027 and b["visibility"] == "public"
    assert {x["project"] for x in api.get("/api/v1/leaderboards", headers=bearer()).json()["boards"]} == {"HI", "PRIV"}


# --------------------------------------------------------------------------- #
# The evaluation cache, with real games                                        #
# --------------------------------------------------------------------------- #
HELLO = "level1_hello:HelloAgent"
RULES_A = "level2_rules:RulesAgent"


def _play(s):
    s.start()
    s.wait_for_turn()
    s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()


def test_games_reach_the_board_through_the_cache(hani2_home):
    from hani2.testing import make_session

    projects.create_project("G", kind="assistant", year=2027)
    ref = StudyRef("G", "play")
    projects.create_study(ref, type="online")
    f = projects.study_dir(ref) / projects.STUDY_FILE
    d = projects.read_yaml(f)
    d.update(practice=False, leaderboard={"sort_options": ["utility", "agreement"], "rules": RULES0})
    projects.write_yaml(f, d)
    gdir = projects.study_dir(ref) / "results" / "groups"
    gdir.mkdir(parents=True, exist_ok=True)
    for k, spec in (("a", HELLO), ("b", RULES_A)):
        (gdir / f"t_{k}.json").write_text(json.dumps({"agents": ["ConcederTBNegotiator"], "assistant": spec,
                                                      "entrant": f"sub_{k}", "own": False}))
    sessions = []
    for i in range(2):
        for k in "ab":
            s = make_session(user=f"anac_{k}{i}", mode="main", partner=None, study=ref,
                             query={"noautostart": "1", "group": f"t_{k}"})
            _play(s)
            sessions.append(s)
    eval_cache.wait(30)
    # written live when the rows were written (the recordings are still open)
    cached = list(eval_cache.entries(ref))
    assert len(cached) == 4 and all(e["row"].get("assistant_entrant") in ("sub_a", "sub_b") for e in cached)
    row = next(csv.DictReader(open(sessions[0].ss["user_path"] / "results.csv")))
    assert row["counted"] == "True"
    for s in sessions:
        s.recorder.finalize()
    eval_cache.wait(30)
    assert all(e["file"].endswith(".hrec") for e in eval_cache.entries(ref))  # computed again once closed
    out = boards.board("G", "play", {}, n_boot=20)
    assert sorted(names(out)) == ["sub_a", "sub_b"]
    assert {e["label"] for e in out["entries"]} == {"HelloAgent", "RulesAgent"}
    # judge values survive a refresh, and a stale entry is computed again
    e0 = cached[0]
    entry = eval_cache.read_entry(ref, e0["id"])
    entry["judged"] = {"ja_overall": 5.0, "judge_model": "test:judge"}
    eval_cache._write_entry(ref, e0["id"], entry)
    n = eval_cache.refresh(ref)
    assert n["games"] == 4 and eval_cache.read_entry(ref, e0["id"])["judged"]["ja_overall"] == 5.0
    entry = eval_cache.read_entry(ref, e0["id"])
    entry["size"] = 1
    eval_cache._write_entry(ref, e0["id"], entry)
    rows, info = eval_cache.rows(ref)
    assert info["computed"] == 1 and len(rows) == 4 and any(r.get("ja_overall") == 5.0 for r in rows)


def test_cli_show_refresh_and_project_export(hani2_home, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from hani2.cli import app

    projects.create_project("E", kind="assistant", year=2027)
    projects.create_study("E/play", type="online")
    set_board({"sort_options": ["utility"], "visibility": "public"}, project="E")
    pdir = projects.project_dir("E")
    (pdir / "groups").mkdir()
    (pdir / "groups" / "g.json").write_text('["ConcederTBNegotiator"]')
    (pdir / "env.json").write_text('{"llm": {"api_key": "sk-secret"}}')
    res = projects.study_dir(StudyRef("E", "play")) / "results"
    (res / "u1").mkdir(parents=True)
    (res / "u1" / "results.csv").write_text("x\n1\n")
    r = CliRunner()
    out = r.invoke(app, ["leaderboard", "show", "E"])
    assert out.exit_code == 0, out.output
    assert "hi board, sorted by utility" in out.output
    assert r.invoke(app, ["leaderboard", "show", "E", "--as-user", "--sort", "hi_team"]).exit_code == 1
    assert r.invoke(app, ["leaderboard", "refresh", "E"]).exit_code == 0
    assert r.invoke(app, ["leaderboard", "list"]).output.startswith("E ")
    dest = tmp_path / "export"
    out = r.invoke(app, ["project", "export", "E", "--out", str(dest)])
    assert out.exit_code == 0, out.output
    got = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
    assert got == ["E/groups/g.json", "E/project.yaml", "E/studies/play/study.yaml"]
    assert "skipped env.json" in out.output
    assert "leaderboard" in (dest / "E" / "project.yaml").read_text()
    # an existing file is kept unless --overwrite
    (dest / "E" / "project.yaml").write_text("x: 1\n")
    r.invoke(app, ["project", "export", "E", "--out", str(dest)])
    assert (dest / "E" / "project.yaml").read_text() == "x: 1\n"
    r.invoke(app, ["project", "export", "E", "--out", str(dest), "--overwrite"])
    assert "leaderboard" in (dest / "E" / "project.yaml").read_text()


# --------------------------------------------------------------------------- #
# Fixes: HAN cells, data_version, unfinished games, hand-edited blocks         #
# --------------------------------------------------------------------------- #
def test_han_vs_team_cells_name_the_assistant_not_the_agent(hi):
    projects.create_project("HAN", kind="opponent")
    projects.create_study("HAN/play", type="online")
    set_board({"sort_options": ["utility"], "user_options": {"stratum": ["alone", "vs_team"]}, "rules": RULES0},
              project="HAN")
    X, Y = "han.x:X", "han.y:Y"
    hi["HAN/play"] = [row("u1", A, 0.2, opponent=X, opponent_han_year=2027),
                      row("u2", A, 0.8, opponent=Y, opponent_han_year=2027)]
    out = boards.board("HAN", None, {"stratum": "vs_team"}, n_boot=0)  # adjust: relative
    e = {x["entrant"]: x["values"]["utility"]["mean"] for x in out["entries"]}
    assert e[X] != pytest.approx(e[Y]) and e[Y] > e[X]  # one cell (s1 × the Assistant) holds both agents


def test_data_version_follows_the_values(hi):
    set_board({"sort_options": ["utility"], "rules": RULES0})
    hi["HI/play"] = [row("u1", A, 0.5, id="x1"), row("u2", B, 0.4, id="x2")]
    v1 = boards.board("HI", None, {}, n_boot=0)["data_version"]
    hi["HI/play"][0]["human_advantage"] = 0.6
    v2 = boards.board("HI", None, {}, n_boot=0)["data_version"]
    assert v1 != v2 and boards.board("HI", None, {}, n_boot=0)["data_version"] == v2


def test_a_hand_edited_block_is_still_served(hi):
    set_board({"sort_options": ["utility", "nope"], "default_sort": "nope", "columns": ["utility", "games"],
               "user_options": {"games": ["all", "bots"]},
               "defaults": {"stratum": "sideways", "window": "yesterday", "games": "people"},
               "rules": {"min_games": "many", "min_participants": 1, "ci": 7}})
    hi["HI/play"] = [row(f"u{i}", A, 0.5) for i in range(12)]
    out = boards.board("HI", None, {}, n_boot=0)
    assert out["query"] == {"sort": "utility", "games": "people", "stratum": "combined", "window": "all"}
    assert out["rules"]["min_games"] == 10 and out["rules"]["ci"] == 0.95
    assert out["options"]["games"] == ["all"] and out["options"]["defaults"]["sort"] == "utility"
    assert any("default_sort 'nope'" in w for w in out["warnings"])
    assert any("leaderboard settings" in w for w in out["warnings"])


def test_unfinished_recordings_are_read_once(hani2_home, monkeypatch):
    from test_criteria import _write_recording

    from hani2.recording import format as F

    projects.create_project("U", kind="assistant")
    ref = StudyRef("U", "s")
    projects.create_study(ref, type="online")
    res = projects.study_dir(ref) / "results"
    _write_recording(res / "u1" / "recordings", "done", n_offers=4, started="2027-01-01T10:00:00")
    _write_recording(res / "u2" / "recordings", "open", n_offers=4, started="2027-01-01T10:00:00", result=False)
    rows, info = eval_cache.rows(ref)
    assert len(rows) == 1 and info["computed"] == 2
    loads = []
    real = F.Recording.load.__func__
    monkeypatch.setattr(F.Recording, "load", classmethod(lambda cls, p: loads.append(p) or real(cls, p)))
    rows, info = eval_cache.rows(ref)
    assert len(rows) == 1 and info["computed"] == 0 and loads == []
    # once the game finishes (the file grows), it is read again
    _write_recording(res / "u2" / "recordings", "open", n_offers=4, started="2027-01-01T10:00:00")
    rows, _ = eval_cache.rows(ref)
    assert len(rows) == 2 and len(loads) == 1


def test_post_session_answers_join_the_games_of_one_assistant(hani2_home):
    import yaml

    from test_criteria import _write_recording

    projects.create_project("Q", kind="assistant")
    ref = StudyRef("Q", "s")
    projects.create_study(ref, type="online")
    sdir = projects.study_dir(ref)
    (sdir / "questionnaires").mkdir(parents=True)
    (sdir / "questionnaires" / "post_session.yaml").write_text(yaml.safe_dump(
        {"questions": [{"id": "overall", "text": "Overall?", "type": "likert7"}]}), encoding="utf-8")
    # a guest's folder is <account>~<browser id>, and their recordings name that user (the helper uses
    # the recording id as the user)
    for u, a in (("anac_g~3f2a9c1b0d4e", 6), ("u2", 2)):
        _write_recording(sdir / "results" / u / "recordings", u, n_offers=4, started="2027-01-01T10:00:00")
        (sdir / "results" / u / "post_session.json").write_text(json.dumps({"answers": {"overall": a}}))
    rows, _ = boards.study_rows(ref)
    assert {r["user"]: r.get("post_q_overall") for r in rows} == {"anac_g~3f2a9c1b0d4e": 6, "u2": 2}
    # several Assistants used by one person: their answer is credited to none
    base = {k: v for k, v in rows[0].items() if not k.startswith("post_")}
    rows2 = boards._post_session(ref, [dict(base, assistant="a:A"), dict(base, assistant="b:B")])
    assert all("post_q_overall" not in r for r in rows2)


def test_judge_adds_its_criteria_to_the_cache(hani2_home, monkeypatch):
    from test_criteria import _write_recording

    import hani2.evaluation as E

    projects.create_project("J", kind="assistant")
    ref = StudyRef("J", "s")
    projects.create_study(ref, type="online")
    res = projects.study_dir(ref) / "results"
    for i in range(2):
        _write_recording(res / f"u{i}" / "recordings", f"g{i}", n_offers=4, started="2027-01-01T10:00:00")
    calls = []

    def fake(rec, metrics=None, *, use_llm=False, key=None, judge=None, **kw):
        calls.append((rec.id, tuple(metrics or ()), use_llm, judge))
        return {"row": {"ja_overall": 6.0, "judge_model": "test:judge", "human_advantage": 0.1}, "details": {},
                "errors": {}}

    eval_cache.rows(ref)  # the entries exist
    with monkeypatch.context() as m:
        m.setattr(E, "evaluate_recording", fake)
        n = eval_cache.judge(ref, judge="test:judge", limit=1)
        assert n["judged"] == 1 and calls[0][2] is True and calls[0][3] == "test:judge"
        assert set(calls[0][1]) == set(eval_cache.soft_metrics())
        n = eval_cache.judge(ref)
        assert n == {"judged": 1, "skipped": 1, "failed": 0}
    rows, info = eval_cache.rows(ref)
    assert info["judged"] == 2 and all(r["ja_overall"] == 6.0 and r["judge_model"] == "test:judge" for r in rows)
    assert all(r["human_advantage"] != 0.1 for r in rows)  # only the judged columns are taken


def test_a_guest_sees_only_the_board_of_their_study(api, hi, monkeypatch):
    projects.create_study("HI/other", type="online")
    set_board({"sort_options": ["utility"], "visibility": "participants", "rules": RULES0})
    api.post("/api/auth/register", json={"username": "bob", "password": "bobpass1"})
    api.post("/api/auth/login", json={"username": "bob", "password": "bobpass1"})
    monkeypatch.setattr(sso, "guest_study", lambda u: "HI/play" if u == "bob" else None)
    assert api.get("/api/v1/projects/HI/studies/play/leaderboard").status_code == 200
    assert api.get("/api/v1/projects/HI/studies/other/leaderboard").status_code == 403
    assert api.get(URL).status_code == 403
    assert api.get("/api/v1/leaderboards").json()["boards"] == []
