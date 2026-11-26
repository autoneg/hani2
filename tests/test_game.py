"""A game study: registered participants and invited guests play each other (or an AI), never
learning about the other side; see docs/guide/human-opponents.md#a-game."""

import csv
import json
import time
import uuid

import pytest
from conftest import write_settings
from fastapi.testclient import TestClient

from hani2 import auth, matches, projects, sso
from hani2.testing import make_session

SECRET = "test-secret-0123456789abcdef"
GAME = "game/play"


@pytest.fixture(autouse=True)
def _empty_lobby():
    matches.LOBBY.clear()
    yield
    matches.LOBBY.clear()


def game_study(home, **neg):
    projects.create_project("game", kind="none", defaults={"opponents": ["human+assistant", "human",
                                                                          "BoulwareTBNegotiator"],
                                                           "questionnaires": False})
    st = projects.create_study(GAME, type="online", title="The game")
    (st.path if hasattr(st, "path") else projects.study_dir(projects.parse_ref(GAME))).mkdir(parents=True, exist_ok=True)
    folder = projects.study_dir(projects.parse_ref(GAME))
    (folder / "env.json").write_text(json.dumps({"negotiation": {
        "human_opponents_first": True, "human_opponent_codes": False, "human_opponent_wait": 120, **neg}}))
    return folder


def play(user, **kw):
    kw.setdefault("opponent", None)
    kw.setdefault("partner", None)
    kw.setdefault("n_steps", 10)
    kw.setdefault("study", GAME)
    return make_session(user=user, **kw)


# --------------------------------------------------------------------------- #
# Pairing                                                                     #
# --------------------------------------------------------------------------- #
def test_human_first_pairs_any_human_kind(hani2_home):
    game_study(hani2_home)
    a = play("alice")  # with an Assistant
    b = play("bob", assistant_settings={"mode": "off"})  # without one
    # both take any person; alice (Assistant) fits bob who has none, and the reverse
    assert a.match is not None and a.match is b.match
    assert a.snapshot()["opponent_kind"] == "human" and b.snapshot()["opponent_kind"] == "human+assistant"


def test_human_first_never_draws_the_ai_while_looking(hani2_home):
    game_study(hani2_home)
    for i in range(6):
        s = play(f"p{i}")
        assert s.match is not None, "every round looks for a person first"
        s.close()


def test_url_match_codes_are_ignored_when_the_study_says_so(hani2_home):
    game_study(hani2_home)
    a = play("alice", query={"match": "x1"})
    assert matches.match_key(a) == "project:game"
    b = play("bob", query={"match": "zz"})
    assert a.match is b.match  # the codes did not separate them


def test_pairing_is_random_among_those_waiting(hani2_home):
    game_study(hani2_home)
    hosts = []
    for i in range(4):  # four people waiting who do not fit each other (as if just separated)
        h = play(f"h{i}", load=False)
        h._avoid_sids = {x.sid for x in hosts}
        for x in hosts:
            x._avoid_sids.add(h.sid)
        h.load()
        hosts.append(h)
    assert matches.LOBBY.n_waiting() == 4
    met = set()
    for i in range(16):
        j = play(f"j{i}")
        assert j.match is not None and j.match.paired
        met.add(j.match.other(j).user)
        j.close()  # that host waits again
    assert len(met) >= 2


def test_the_choice_screen_counts_people_and_offers_an_ai(hani2_home):
    game_study(hani2_home, human_opponent_choice=True)
    a = play("alice")
    assert a.match is None and a.opponent_choice_pending
    assert a.snapshot()["opponent_choice"] == {"people_waiting": 0}
    a.start()
    assert a.phase == "ready"  # nothing starts before the choice
    assert a.choose_opponent_kind("person")["ok"]
    assert a.match is not None and not a.opponent_choice_pending and a.snapshot()["can_play_ai_instead"]
    b = play("bob")
    assert b.snapshot()["opponent_choice"] == {"people_waiting": 1}
    assert b.choose_opponent_kind("person")["ok"]
    assert b.match is a.match and a.match.paired


def test_play_an_ai_now_and_instead_of_waiting(hani2_home):
    game_study(hani2_home, human_opponent_choice=True)
    a = play("alice")
    assert a.choose_opponent_kind("ai")["ok"]
    assert a.match is None and not matches.is_human(a.round_plan["partner"])
    a.start()
    assert a.wait(lambda: a.phase == "running", 20)
    assert a.snapshot()["opponent_kind"] == "agent"
    # waiting for a person, then giving up
    b = play("bob")
    assert b.choose_opponent_kind("person")["ok"] and b.match is not None
    b.start()
    assert b.phase == "starting" and b.waiting_for_opponent
    assert b.choose_opponent_kind("ai")["ok"]
    assert b.wait(lambda: b.phase == "running", 20) and b.match is None
    assert matches.LOBBY.n_waiting() == 0


def test_the_url_flag_turns_the_choice_on(hani2_home):
    game_study(hani2_home)
    a = play("alice", query={"opponent_choice": "1"})
    assert a.opponent_choice_pending
    b = play("bob")
    assert not b.opponent_choice_pending and b.match is not None  # paired automatically (waits)


# --------------------------------------------------------------------------- #
# Nothing about the other side                                                #
# --------------------------------------------------------------------------- #
def _run_to_agreement(a, b):
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    first, second = (a, b) if a.wait_for_turn(5) and a.is_my_turn() else (b, a)
    assert first.send_counter("deal?").get("ok", True)
    assert second.wait_for_turn()
    assert second.accept()
    assert a.wait_until_done() and b.wait_until_done()


def test_a_game_records_both_sides_and_asks_no_questionnaire(hani2_home):
    game_study(hani2_home)
    a, b = play("alice"), play("bob")
    assert a.match is b.match
    _run_to_agreement(a, b)
    for me in (a, b):
        assert me.questionnaire is None and me.phase == "ended"  # questionnaires: false
    with open(a.ss["user_path"] / "results.csv") as fh:
        row = list(csv.DictReader(fh))[-1]
    assert row["opponent_user"] == "bob" and row["match_id"] and row["agent_utility"] != ""
    # the page shows the other participant's name nowhere
    assert "bob" not in json.dumps(a.snapshot(), default=str)


def test_questionnaires_off_wins_over_the_environment(hani2_home, monkeypatch):
    from hani2 import questionnaires

    monkeypatch.setenv("PROLIFIC_PER_NEG_YAML", "evaluation")
    game_study(hani2_home)
    with projects.use_study(projects.parse_ref(GAME)):
        r = questionnaires.resolve("per_negotiation")
        assert r.spec is None and r.disabled and r.source == "study"
    assert questionnaires.resolve("per_negotiation").spec is not None  # elsewhere the variable applies


# --------------------------------------------------------------------------- #
# Invited guests                                                              #
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(hani2_home, monkeypatch):
    game_study(hani2_home)
    projects.create_study("game/other", type="online")
    write_settings(hani2_home, "env.json", {
        "auth": {"sso": {"scmlweb": {"secret": SECRET, "guest_studies": [GAME]}}}})
    monkeypatch.setenv("HANI2_PROJECTS", str(hani2_home / "projects"))
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c
    for s in list(hub.sessions.values()):
        s.close()
    hub.sessions.clear()


def claims(**kw):
    now = int(time.time())
    return {"iss": "scmlweb", "aud": "hani2", "sub": "invite-42", "iat": now, "exp": now + 60,
            "jti": uuid.uuid4().hex, "guest": True, "invited_by": 789, "name": "Sam", **kw}


NEXT = f"/app?study={GAME}&group=g1&opponent_choice=1"


def wait(pred, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def go(client, token, next=NEXT):
    return client.get("/api/sso/scmlweb", params={"token": token, "next": next}, follow_redirects=False)


def test_a_guest_token_makes_a_guest_bound_to_the_game(client):
    r = go(client, sso.sign(claims(), SECRET))
    assert r.status_code == 303 and r.headers["location"] == NEXT
    meta = auth.get_meta("anac_invite-42")
    assert meta["guest"] is True and meta["guest_study"] == GAME and meta["invited_by"] == "789"
    assert meta["full_name"] == "Sam"
    ok = client.post("/api/session", json={"mode": "main", "query": {"study": GAME, "opponent_choice": "1"}})
    assert ok.status_code == 200, ok.text
    sid = ok.json()["sid"]
    from hani2.server import hub

    s = hub.get(sid)
    assert s.user.startswith("anac_invite-42~") and s.ss["invited_by"] == "789" and not s.is_admin
    assert s.opponent_choice_pending
    # nothing else: another study, the default study, the playground, admin pages
    assert client.post("/api/session", json={"mode": "main", "query": {"study": "game/other"}}).status_code == 403
    assert client.post("/api/session", json={"mode": "main"}).status_code == 403
    assert client.post("/api/session", json={"mode": "guest"}).status_code == 403
    assert client.get("/api/admin/results").status_code in (401, 403)
    assert client.get("/api/replay/recordings").status_code in (401, 403)


def test_guests_only_for_the_listed_studies(client):
    r = go(client, sso.sign(claims(), SECRET), next="/app?study=game/other")
    assert "error=sso_guest" in r.headers["location"]
    r = go(client, sso.sign(claims(), SECRET), next="/app")
    assert "error=sso_guest" in r.headers["location"]


def test_guest_and_normal_accounts_never_mix(client):
    assert go(client, sso.sign(claims(sub="77", guest=False), SECRET)).headers["location"] == NEXT
    r = go(client, sso.sign(claims(sub="77"), SECRET))  # a guest token for a normal account
    assert "error=sso_conflict" in r.headers["location"]
    go(client, sso.sign(claims(), SECRET))
    r = go(client, sso.sign(claims(guest=False), SECRET))
    assert "error=sso_conflict" in r.headers["location"]


def test_two_browsers_on_one_invitation_get_their_own_sessions(client):
    from hani2.server import app

    go(client, sso.sign(claims(), SECRET))
    s1 = client.post("/api/session", json={"mode": "main", "query": {"study": GAME}}).json()["sid"]
    with TestClient(app) as other:
        go(other, sso.sign(claims(), SECRET))
        s2 = other.post("/api/session", json={"mode": "main", "query": {"study": GAME}}).json()["sid"]
    assert s1 != s2


def test_the_invited_by_column(client):
    go(client, sso.sign(claims(), SECRET))
    sid = client.post("/api/session", json={"mode": "main", "query": {"study": GAME}}).json()["sid"]
    from hani2.server import hub

    s = hub.get(sid)
    assert s.choose_opponent_kind("ai")["ok"]
    s.start()
    assert wait(lambda: s.phase == "running")
    assert s.end()
    assert wait(lambda: s.phase in ("ended", "questionnaire"))
    with open(s.ss["user_path"] / "results.csv") as fh:
        row = list(csv.DictReader(fh))[-1]
    assert row["invited_by"] == "789"


def test_a_new_hand_off_after_a_game_opens_a_new_negotiation(client):
    go(client, sso.sign(claims(sub="5", guest=False), SECRET), next=f"/app?study={GAME}")
    sid = client.post("/api/session", json={"mode": "main", "query": {"study": GAME}}).json()["sid"]
    from hani2.server import hub

    s = hub.get(sid)
    s.choose_opponent_kind("ai")
    s.start()
    assert wait(lambda: s.phase == "running") and s.end()
    assert wait(lambda: s.phase == "ended")
    client.post("/api/session", json={"mode": "main", "query": {"study": GAME}})  # a reload: the result stays
    time.sleep(0.3)
    assert s.phase == "ended"
    go(client, sso.sign(claims(sub="5", guest=False), SECRET), next=f"/app?study={GAME}")
    client.post("/api/session", json={"mode": "main", "query": {"study": GAME}})
    assert wait(lambda: s.phase == "ready")


def test_a_group_file_can_give_a_player_no_assistant(hani2_home):
    folder = game_study(hani2_home)
    groups = folder / "results" / "groups"
    groups.mkdir(parents=True, exist_ok=True)
    (groups / "solo_x1.json").write_text(json.dumps({"agents": ["human+assistant", "human", "BoulwareTBNegotiator"],
                                                      "assistant": "none"}))
    a = play("alice", query={"group": "solo_x1"})
    assert a.support_agent is None and not a.assistant_error
    b = play("bob")  # with an Assistant: they fit (both take any person)
    assert a.match is not None and a.match is b.match
    assert b.snapshot()["opponent_kind"] == "human"



# --------------------------------------------------------------------------- #
# Invitations: the group file decides the Assistant (HI) or the opponent (HAN) #
# --------------------------------------------------------------------------- #
HELLO, RULES = "level1_hello:HelloAgent", "level2_rules:RulesAgent"


def _study_with_its_own_choices(folder, **neg):
    """The study has its own Assistant pool and lets participants choose the Assistant and the opponent."""
    projects.create_project("game", kind="none", defaults={
        "opponents": ["human+assistant", "human", "BoulwareTBNegotiator"], "assistants": [RULES, "none"],
        "questionnaires": False})
    env = json.loads((folder / "env.json").read_text())
    env["choices"] = {"assistant": True, "opponent": True}
    env["negotiation"].update(neg)
    (folder / "env.json").write_text(json.dumps(env))


def _group(folder, key, **data):
    d = folder / "results" / "groups"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(data))


def test_the_group_files_assistant_always_wins(hani2_home):
    folder = game_study(hani2_home)
    _study_with_its_own_choices(folder)
    _group(folder, "inv_hello", agents=["human+assistant", "human", "BoulwareTBNegotiator"], assistant=HELLO)
    plain = play("carol")
    assert plain.assistant_choice.spec in (RULES, "none")  # the study's own pool, without a group
    for i in range(3):
        s = play(f"p{i}", query={"group": "inv_hello"})
        assert s.assistant_choice.spec == HELLO and type(s.support_agent).__name__ == "HelloAgent"
        assert s.assistant_choice.source == "group"
        assert s.choose("assistant", RULES)["ok"] is False  # no participant pick replaces it
        st = s.snapshot()["choices"]
        assert st is None or not st["assistant"]["options"]
        s.load()  # a new round keeps it
        assert s.assistant_choice.spec == HELLO
        s.close()


def test_the_group_files_assistant_wins_even_when_the_assistant_is_switched_off(hani2_home):
    folder = game_study(hani2_home)
    _group(folder, "inv_hello", assistant=HELLO)
    s = play("dave", query={"group": "inv_hello"}, assistant_settings={"mode": "off"})
    assert type(s.support_agent).__name__ == "HelloAgent"


def test_a_group_file_naming_no_assistant_gives_none(hani2_home):
    folder = game_study(hani2_home)
    _study_with_its_own_choices(folder)
    _group(folder, "inv_none", assistant="none")
    s = play("erin", query={"group": "inv_none"})
    assert s.support_agent is None and s.assistant_choice.spec == "none" and not s.assistant_error
    assert s.choose("assistant", RULES)["ok"] is False


def test_an_invited_agent_is_the_only_opponent(hani2_home):
    folder = game_study(hani2_home, human_opponent_choice=True)
    _study_with_its_own_choices(folder)
    _group(folder, "han_inv", agents=["ConcederTBNegotiator"])
    for i in range(3):
        s = play(f"h{i}", query={"group": "han_inv"})
        assert s.match is None and not s.opponent_choice_pending  # no person, no person/AI screen
        assert s.choose("opponent", "BoulwareTBNegotiator")["ok"] is False
        s.start()
        assert s.wait(lambda: s.phase == "running", 20)
        assert "Conceder" in str(s.ss.get("last_partner_type"))
        assert s.end() and s.wait(lambda: s.phase == "ended", 20)
        s.close()


def test_a_guest_plays_with_the_inviters_assistant(client, hani2_home):
    folder = projects.study_dir(projects.parse_ref(GAME))
    _study_with_its_own_choices(folder)
    _group(folder, "inv_hello", agents=["human+assistant", "human", "BoulwareTBNegotiator"], assistant=HELLO)
    go(client, sso.sign(claims(), SECRET), next=f"/app?study={GAME}&group=inv_hello")
    sid = client.post("/api/session", json={"mode": "main",
                                            "query": {"study": GAME, "group": "inv_hello"}}).json()["sid"]
    from hani2.server import hub

    s = hub.get(sid)
    assert s.assistant_choice.spec == HELLO and type(s.support_agent).__name__ == "HelloAgent"
    assert s.choose("assistant", RULES)["ok"] is False


def test_a_guest_plays_only_the_invited_agent(client, hani2_home):
    folder = projects.study_dir(projects.parse_ref(GAME))
    _study_with_its_own_choices(folder)
    _group(folder, "han_inv", agents=["ConcederTBNegotiator"])
    go(client, sso.sign(claims(), SECRET), next=f"/app?study={GAME}&group=han_inv&opponent_choice=1")
    sid = client.post("/api/session", json={"mode": "main", "query": {"study": GAME, "group": "han_inv",
                                                                      "opponent_choice": "1"}}).json()["sid"]
    from hani2.server import hub

    s = hub.get(sid)
    assert s.match is None and not s.opponent_choice_pending
    assert s.choose("opponent", "BoulwareTBNegotiator")["ok"] is False
    s.start()
    assert wait(lambda: s.phase == "running")
    assert "Conceder" in str(s.ss.get("last_partner_type"))


# --------------------------------------------------------------------------- #
# People-only invitations ("ai_fallback": false in the group file)            #
# --------------------------------------------------------------------------- #
PEOPLE = ["human+assistant", "human"]


def test_a_people_only_group_keeps_waiting_instead_of_an_ai(hani2_home):
    folder = game_study(hani2_home, human_opponent_wait=0.3)
    _group(folder, "inv_people", agents=PEOPLE, ai_fallback=False)
    s = play("alice", query={"group": "inv_people"})
    assert s.people_only() and s.match is not None
    assert not s.snapshot()["can_play_ai_instead"]
    s.start()
    time.sleep(1.5)  # several wait-time expiries
    assert s.phase == "starting" and s.mechanism is None and s.match is not None and s.waiting_for_opponent
    assert matches.LOBBY.n_waiting() == 1
    b = play("bob", query={"group": "inv_people"})  # a person still meets them
    assert b.match is s.match and s.match.paired


def test_without_the_switch_a_people_group_still_falls_back_to_an_ai(hani2_home):
    folder = game_study(hani2_home, human_opponent_wait=0.3)
    for i, extra in enumerate(({}, {"ai_fallback": True})):
        _group(folder, f"inv_any{i}", agents=PEOPLE, **extra)
        s = play(f"p{i}", query={"group": f"inv_any{i}"})
        assert not s.people_only() and s.snapshot()["can_play_ai_instead"]
        s.start()
        assert s.wait(lambda: s.phase == "running", 20) and s.match is None
        assert s.snapshot()["opponent_kind"] == "agent"
        s.close()


def test_a_people_only_group_has_no_choice_screen_and_refuses_an_ai(hani2_home):
    folder = game_study(hani2_home, human_opponent_choice=True)
    _group(folder, "inv_people", agents=PEOPLE, ai_fallback=False)
    s = play("alice", query={"group": "inv_people", "opponent_choice": "1"})
    assert not s.opponent_choice_enabled() and not s.opponent_choice_pending
    assert s.snapshot()["opponent_choice"] is None and s.match is not None
    m = s.match
    r = s.choose_opponent_kind("ai")
    assert r["ok"] is False and "person" in r["error"]
    assert s.match is m and matches.LOBBY.n_waiting() == 1  # still in its waiting room
    s.start()
    assert s.choose_opponent_kind("ai")["ok"] is False
    time.sleep(0.3)
    assert s.phase == "starting" and s.match is m and s.mechanism is None
    other = play("carol", query={"opponent_choice": "1"})  # the same study without the group: unchanged
    assert other.opponent_choice_pending


def test_a_people_only_group_drops_its_ai_entries_and_offers_no_ai_pick(hani2_home):
    folder = game_study(hani2_home)
    _study_with_its_own_choices(folder)
    _group(folder, "inv_mixed", agents=["human", "BoulwareTBNegotiator"], ai_fallback=False)
    s = play("alice", query={"group": "inv_mixed"})
    assert s.opponent_pool() == ["human"] and s.people_only()
    for _ in range(5):
        s.load()
        assert s.match is not None
    st = s.snapshot()["choices"]
    assert st is None or not st["opponent"]["options"]
    assert s.choose("opponent", "BoulwareTBNegotiator")["ok"] is False


def test_a_people_only_group_without_people_is_ignored(hani2_home):
    folder = game_study(hani2_home)
    _group(folder, "inv_ai", agents=["ConcederTBNegotiator"], ai_fallback=False)
    s = play("alice", query={"group": "inv_ai"})
    assert not s.people_only() and s.match is None
    s.start()
    assert s.wait(lambda: s.phase == "running", 20)
    assert "Conceder" in str(s.ss.get("last_partner_type"))


def test_a_people_only_session_never_starts_an_ai_even_without_its_match(hani2_home):
    folder = game_study(hani2_home)
    _group(folder, "inv_people", agents=PEOPLE, ai_fallback=False)
    s = play("alice", query={"group": "inv_people"})
    s._leave_match()  # as if the waiting room were lost: start() would build an AI opponent
    s.ss["match_id"] = None
    s.round_plan = dict(s.round_plan or {}, partner="BoulwareTBNegotiator")
    s.start()
    assert s.wait(lambda: s.match is not None, 10)
    assert s.mechanism is None and s.phase == "ready" and matches.LOBBY.n_waiting() == 1


def test_a_broken_people_only_group_still_offers_no_ai_pick(hani2_home):
    from hani2 import choices

    folder = game_study(hani2_home)
    _study_with_its_own_choices(folder)
    _group(folder, "inv_broken", agents=PEOPLE, members=["human"], ai_fallback=False)  # conflicting keys
    s = play("alice", query={"group": "inv_broken"})
    assert choices.policy(s)["opponent"] is False
    assert s.choose("opponent", "BoulwareTBNegotiator")["ok"] is False


def test_the_server_refuses_an_ai_for_a_people_only_guest(client, hani2_home):
    from hani2.server import _dispatch_msg, hub

    folder = projects.study_dir(projects.parse_ref(GAME))
    _study_with_its_own_choices(folder, human_opponent_choice=True)
    _group(folder, "inv_people", agents=PEOPLE, ai_fallback=False)
    nxt = f"/app?study={GAME}&group=inv_people&opponent_choice=1"
    go(client, sso.sign(claims(), SECRET), next=nxt)
    sid = client.post("/api/session", json={"mode": "main", "query": {
        "study": GAME, "group": "inv_people", "opponent_choice": "1"}}).json()["sid"]
    s = hub.get(sid)
    assert s.match is not None and not s.opponent_choice_pending
    snap = s.snapshot()
    assert not snap["can_play_ai_instead"] and snap["opponent_choice"] is None
    assert _dispatch_msg(s, {"type": "opponent_choice", "kind": "ai"})["ok"] is False
    assert _dispatch_msg(s, {"type": "choose", "kind": "opponent", "value": "BoulwareTBNegotiator"})["ok"] is False
    assert s.match is not None and s.chosen_opponent is None
    _dispatch_msg(s, {"type": "start"})
    assert _dispatch_msg(s, {"type": "opponent_choice", "kind": "ai"})["ok"] is False
    time.sleep(0.3)
    assert s.phase == "starting" and s.mechanism is None and s.match is not None
