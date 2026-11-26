"""``hani2 human-trial`` prepares its own home with a human-against-human study (hani2.trial)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from hani2 import projects, trial
from hani2.cli import app


def test_prepare_writes_a_human_against_human_study(tmp_path):
    t = trial.prepare(tmp_path)
    assert t.study_dir == tmp_path.resolve() / "projects" / "trial" / "studies" / "versus"
    project = projects.read_yaml(tmp_path / "projects" / "trial" / "project.yaml")
    assert project["defaults"]["opponents"] == ["human"]
    assert project["defaults"]["questionnaires"] is False
    assert projects.read_yaml(t.study_dir / "study.yaml")["type"] == "lab"
    env = json.loads((t.study_dir / "env.json").read_text())
    assert env["negotiation"]["human_opponent_wait"] == 0
    assert json.loads((t.study_dir / "assistant_settings.json").read_text())["mode"] == "off"
    assert "another participant" in (t.study_dir / "announcements.md").read_text()
    # two participants, one match code, both in each link
    a, b = t.path(0), t.path(1)
    assert a != b and f"match={t.match}" in a and f"match={t.match}" in b
    assert a.startswith("/s/trial/versus/play?participant=")


def test_prepare_with_the_assistant_and_options(tmp_path):
    trial.prepare(tmp_path)
    t = trial.prepare(tmp_path, assistant=True, wait=30, time_limit=600)
    project = projects.read_yaml(tmp_path / "projects" / "trial" / "project.yaml")
    assert project["defaults"]["opponents"] == ["human+assistant"]
    env = json.loads((t.study_dir / "env.json").read_text())["negotiation"]
    assert env["human_opponent_wait"] == 30 and env["time_limit"] == 600
    assert json.loads((t.study_dir / "assistant_settings.json").read_text())["mode"] == "on"
    assert not (t.study_dir / "autopilot_settings.json").exists()
    # every run gets new participants, so a rerun never continues an old one
    assert trial.prepare(tmp_path).participants != t.participants


def test_the_command_is_listed():
    r = CliRunner().invoke(app, ["human-trial", "--help"])
    assert r.exit_code == 0 and "--assistant" in r.output and "--wait" in r.output
