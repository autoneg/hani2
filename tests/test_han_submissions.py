"""HAN agents of the current year from the submitted zips (hani2.han_submissions)."""

import json
import zipfile

import pytest
from conftest import write_settings

from hani2 import agents, han_submissions, projects

AGENT = (
    "from negmas.sao import BoulwareTBNegotiator\n\n"
    "class MyNegotiator(BoulwareTBNegotiator):\n"
    "    VERSION = {version!r}\n"
)


def make_zip(path, package, version="1", body=None, extra=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{package}/__init__.py", "")
        zf.writestr(f"{package}/agent.py", body if body is not None else AGENT.format(version=version))
        for name, text in (extra or {}).items():
            zf.writestr(name, text)
    return path


def _forget_modules():
    import sys

    for name in [m for m in sys.modules if m.split(".")[0] in ("t17_agent", "t18_agent", "stray")]:
        del sys.modules[name]


@pytest.fixture
def subs(hani2_home, tmp_path, monkeypatch):
    """A 2027 submissions folder with two entrants, and env.json naming it as the current year."""
    _forget_modules()  # a module stays loaded once imported: each test imports its own copy
    monkeypatch.setattr("sys.path", list(__import__("sys").path))
    d = tmp_path / "subs" / "2027"
    d.mkdir(parents=True)
    make_zip(d / "t17.zip", "t17_agent")
    make_zip(d / "t18.zip", "t18_agent")
    index = [
        {"entrant": "sub_0981", "team": "t17", "zip": "t17.zip", "class": "t17_agent.agent:MyNegotiator",
         "qualified": True, "finalist": True, "winner": False},
        {"entrant": "sub_0982", "team": "t18", "zip": "t18.zip", "class": "t18_agent.agent:MyNegotiator",
         "qualified": True, "finalist": False, "winner": False},
    ]
    (d / "index.json").write_text(json.dumps(index), encoding="utf-8")
    write_settings(hani2_home, "env.json", {"han": {"current_year": 2027, "submissions": {"2027": {"dir": str(d)}}}})
    # a han-agents package covering 2026 and 2027 (the 2027 entries must NOT be used: 2027 is current)
    monkeypatch.setattr(agents, "han_years", lambda: [2026, 2027])
    for y in (2026, 2027):
        for k in agents.HAN_GROUP_KINDS:
            monkeypatch.setitem(agents.AGENT_GROUPS, f":han{y}-{k}", [f"han_agents.y{y}.pkg.Agent{y}"])
    yield d
    _forget_modules()


def test_import_unpacks_each_zip_into_its_own_folder_and_checks_the_class(subs, hani2_home):
    results, problems = han_submissions.import_year(2027)
    assert problems == []
    assert [r.status for r in results] == ["imported", "imported"], [r.message for r in results]
    sha = han_submissions.sha256_of(subs / "t17.zip")
    folder = hani2_home / "han_submissions" / "2027" / "sub_0981" / sha
    assert (folder / "t17_agent" / "agent.py").is_file()
    cur = han_submissions.current(2027, "sub_0981")
    assert cur["sha256"] == sha and cur["import_ok"] is True and cur["spec"] == "t17_agent.agent.MyNegotiator"
    # importing again changes nothing
    assert [r.status for r in han_submissions.import_year(2027)[0]] == ["unchanged", "unchanged"]


def test_the_current_year_comes_from_the_submissions_other_years_from_han_agents(subs):
    han_submissions.import_year(2027)
    assert agents.expand_agents(":han2027-all") == ["t17_agent.agent.MyNegotiator", "t18_agent.agent.MyNegotiator"]
    assert agents.expand_agents(":han2027-finalists") == ["t17_agent.agent.MyNegotiator"]
    assert agents.expand_agents(":han2027-winners") == []
    assert agents.expand_agents(":han2026-finalists") == ["han_agents.y2026.pkg.Agent2026"]
    assert han_submissions.source_of(2027) == "submissions" and han_submissions.source_of(2026) == "han-agents"
    # the submitted class really loads in this process (its folder is on sys.path)
    cls = agents.get_agent_type("t17_agent.agent.MyNegotiator")
    assert cls.__name__ == "MyNegotiator"


def test_without_current_year_every_year_comes_from_han_agents(subs, hani2_home):
    write_settings(hani2_home, "env.json", {"han": {"submissions": {"2027": {"dir": str(subs)}}}})
    assert han_submissions.current_year() is None
    assert agents.expand_agents(":han2027-all") == ["han_agents.y2027.pkg.Agent2027"]


def test_a_year_no_source_covers_is_refused_on_save_and_reported_on_load(subs, hani2_home):
    projects.create_project("HI2027", kind="assistant", year=2027)
    with pytest.raises(ValueError, match="no agents for 2025"):
        projects.create_study("HI2027/s", opponents=[":han2025-finalists"])
    projects.create_study("HI2027/ok", opponents=[":han2026-finalists", ":han2027-finalists"])
    # a hand-edited file is reported, and the group expands to nothing
    f = projects.study_dir(projects.StudyRef("HI2027", "hand")) / "study.yaml"
    f.parent.mkdir(parents=True)
    f.write_text("opponents: [':han2025-all']\n", encoding="utf-8")
    from hani2 import study_modes

    info = study_modes.resolve("HI2027/hand")
    assert any("no agents for 2025" in e for e in info.errors)
    assert agents.expand_agents(":han2025-all") == []


def test_a_new_upload_is_a_new_version_and_the_old_one_is_kept(subs, hani2_home):
    han_submissions.import_year(2027)
    old = han_submissions.current(2027, "sub_0981")["sha256"]
    make_zip(subs / "t17.zip", "t17_agent", version="2")
    r = {x.entrant: x for x in han_submissions.import_year(2027)[0]}
    assert r["sub_0981"].status == "imported" and r["sub_0982"].status == "unchanged"
    new = han_submissions.current(2027, "sub_0981")["sha256"]
    assert new != old
    base = hani2_home / "han_submissions" / "2027" / "sub_0981"
    assert (base / old).is_dir() and (base / new).is_dir()
    assert json.loads((base / f"{old}.json").read_text())["sha256"] == old


def test_the_index_is_read_tolerantly(subs):
    (subs / "index.json").write_text(json.dumps({"submissions": [
        {"id": "a/../b", "team_name": "x", "file": "t17.zip", "agent_class_name": "t17_agent.agent.MyNegotiator",
         "winner": "yes", "extra_key": 1},
        {"zip": "t18.zip", "class_name": "t18_agent.agent:MyNegotiator", "qualified": "0"},
        {"team": "no-zip-no-class"},
        "not an entry",
    ]}), encoding="utf-8")
    entries, problems = han_submissions.read_index(2027)
    by = {e.entrant: e for e in entries}
    assert set(by) == {"a_.._b".replace("..", "_"), "t18", "no-zip-no-class"}
    win = next(e for e in entries if e.team == "x")
    assert win.sets == ["all", "qualified", "finalists", "winners"]  # winner ⇒ finalist ⇒ qualified
    assert by["t18"].sets == ["all"] and by["t18"].spec == "t18_agent.agent.MyNegotiator"
    assert "no zip" in by["no-zip-no-class"].problems and "no class" in by["no-zip-no-class"].problems
    assert any("entry 4" in p for p in problems)
    # a mapping of entrant id to entry works too
    (subs / "index.json").write_text(json.dumps({"sub_1": {"zip": "t17.zip", "class": "t17_agent.agent:MyNegotiator"}}),
                                     encoding="utf-8")
    assert [e.entrant for e in han_submissions.read_index(2027)[0]] == ["sub_1"]


def test_unsafe_zips_are_refused_and_nothing_is_written_outside(subs, hani2_home, tmp_path):
    with zipfile.ZipFile(subs / "t17.zip", "w") as zf:
        zf.writestr("t17_agent/__init__.py", "")
        zf.writestr("../escape.py", "print('x')")
    r = {x.entrant: x for x in han_submissions.import_year(2027)[0]}
    assert r["sub_0981"].status == "error" and "unsafe" in r["sub_0981"].message
    assert not list((hani2_home / "han_submissions").rglob("escape.py"))
    assert not (hani2_home / "han_submissions" / "2027" / "escape.py").exists()
    assert han_submissions.current(2027, "sub_0981") is None
    # a zip named outside the folder is not used
    (subs / "index.json").write_text(json.dumps([{"entrant": "e", "zip": "../../x.zip", "class": "a.b:C"}]), encoding="utf-8")
    assert han_submissions.import_year(2027)[0][0].status == "error"


def test_a_class_that_does_not_import_is_left_out_and_reported(subs, hani2_home):
    make_zip(subs / "t18.zip", "t18_agent", body="raise ImportError('broken on purpose')\n")
    r = {x.entrant: x for x in han_submissions.import_year(2027)[0]}
    assert r["sub_0982"].status == "error" and "broken on purpose" in r["sub_0982"].message
    assert agents.expand_agents(":han2027-all") == ["t17_agent.agent.MyNegotiator"]
    rep = han_submissions.check_year(2027, import_check=False)
    row = next(x for x in rep["entries"] if x["entrant"] == "sub_0982")
    assert row["imports"] is False


def test_check_reports_unlisted_zips_missing_imports_and_module_clashes(subs):
    make_zip(subs / "stray.zip", "stray")
    make_zip(subs / "t19.zip", "t17_agent")
    idx = json.loads((subs / "index.json").read_text())
    idx.append({"entrant": "sub_0983", "zip": "t19.zip", "class": "t17_agent.agent:MyNegotiator"})
    (subs / "index.json").write_text(json.dumps(idx), encoding="utf-8")
    rep = han_submissions.check_year(2027, import_check=False)
    assert rep["unlisted_zips"] == ["stray.zip"]
    assert all("not imported" in r["problems"] for r in rep["entries"])
    assert rep["module_clashes"] == {"t17_agent": ["sub_0981", "sub_0983"]}


def test_provenance_of_submitted_and_packaged_agents(subs):
    han_submissions.import_year(2027)
    sha = han_submissions.current(2027, "sub_0981")["sha256"]
    got = han_submissions.provenance("t17_agent.agent.MyNegotiator", "han2027-finalists")
    assert got == {"opponent_han_year": 2027, "opponent_han_source": "submissions", "opponent_han_version": sha}
    han_submissions.prime_syspaths()  # as a server does at start
    neg = agents.get_agent_type("t17_agent.agent.MyNegotiator")()
    assert han_submissions.provenance("whatever", negotiator=neg)["opponent_han_version"] == sha
    pkg = han_submissions.provenance("han_agents.y2026.pkg.Agent2026", "han2026-all")
    assert pkg["opponent_han_year"] == 2026 and pkg["opponent_han_source"] == "han-agents"
    assert han_submissions.provenance("BoulwareTBNegotiator") == {
        "opponent_han_year": "", "opponent_han_source": "", "opponent_han_version": ""}


def test_a_game_records_which_build_of_the_agent_it_played(subs, hani2_home):
    import csv

    from hani2.testing import make_session

    han_submissions.import_year(2027)
    sha = han_submissions.current(2027, "sub_0981")["sha256"]
    projects.create_project("HAN2027", kind="opponent", year=2027)
    projects.create_study("HAN2027/play", type="online", opponents=[":han2027-finalists"])
    s = make_session(user="alice", partner=None, study="HAN2027/play", n_steps=4, assistant_settings={"mode": "off"})
    assert s.opponent_pool() == ["t17_agent.agent.MyNegotiator"]
    s.start()
    s.end()
    assert s.wait_until_done(30)
    with open(s.ss["user_path"] / "results.csv") as fh:
        row = list(csv.DictReader(fh))[-1]
    assert row["opponent_han_year"] == "2027" and row["opponent_han_source"] == "submissions"
    assert row["opponent_han_version"] == sha and row["agent_type"] == "t17_agent.agent.MyNegotiator"


def test_cli_han_import_and_check(subs):
    from typer.testing import CliRunner

    from hani2 import cli

    run = CliRunner()
    r = run.invoke(cli.app, ["han", "check", "--no-import-check"])
    assert r.exit_code == 1 and "not imported" in r.output
    r = run.invoke(cli.app, ["han", "import"])
    assert r.exit_code == 0, r.output
    assert "2 of 2 entries ready" in r.output
    r = run.invoke(cli.app, ["han", "check", "--year", "2027"])
    assert r.exit_code == 0, r.output
    assert "sub_0981" in r.output and "all,qualified,finalists" in r.output and "imports" in r.output
    assert run.invoke(cli.app, ["han", "import", "--year", "2030"]).exit_code != 0


def test_han_settings_in_a_project_env_json_are_seen_on_save_and_in_sessions(subs, hani2_home):
    """han.current_year read from the project's own env.json when its files are saved and resolved."""
    write_settings(hani2_home, "env.json", {})
    projects.create_project("HAN2028", kind="opponent", year=2028)
    (projects.project_dir("HAN2028") / "env.json").write_text(json.dumps({"han": {"current_year": 2028}}), encoding="utf-8")
    projects.create_study("HAN2028/play", opponents=[":han2028-all"])  # covered by the project's current year
    from hani2 import study_modes

    assert study_modes.resolve("HAN2028/play").errors == []
    projects.create_project("HAN2028", defaults={"opponents": [":han2028-finalists"]})
    with pytest.raises(ValueError, match="no agents for 2028"):
        projects.create_project("OTHER", kind="opponent", defaults={"opponents": [":han2028-all"]})


def test_a_broken_reupload_keeps_the_earlier_working_version(subs):
    han_submissions.import_year(2027)
    good = han_submissions.current(2027, "sub_0981")["sha256"]
    make_zip(subs / "t17.zip", "t17_agent", body="raise ImportError('new version is broken')\n")
    r = {x.entrant: x for x in han_submissions.import_year(2027)[0]}
    assert r["sub_0981"].status == "error" and "keeps playing" in r["sub_0981"].message
    assert han_submissions.current(2027, "sub_0981")["sha256"] == good
    assert "t17_agent.agent.MyNegotiator" in agents.expand_agents(":han2027-all")
    row = next(x for x in han_submissions.check_year(2027, import_check=False)["entries"] if x["entrant"] == "sub_0981")
    assert any(good[:12] in p and "plays" in p for p in row["problems"])
