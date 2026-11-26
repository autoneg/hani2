"""``hani2 human-trial``: try a human-against-human negotiation on one machine.

It prepares a home folder of its own (never the normal settings folder) with one study whose opponents
are other participants, and gives two links, one per participant. Each link carries its own
``?participant=<id>`` (a ``lab`` study keys its sessions on it, not on the browser's cookies), so the two
sides can be two tabs of one browser. Both links share a ``?match=<code>``, so they pair with each other
and nobody else.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

PROJECT = "trial"
STUDY = "versus"

#: environment variables of the normal server that would change what the trial study does
INHERITED = ("HANI2_STUDY", "HANI2_EXPERIMENT", "HANI2_OPPONENTS", "HANI2_AGENTS", "HANI2_ASSISTANTS",
             "HANI2_SUPPORT_AGENT", "HANI2_SUPPORT_AGENT_CLASS", "HANI2_SETTINGS_OVERRIDES", "HANI2_SCENARIO_SET",
             "HANI2_SCENARIOS_BASE")


WELCOME = """### Welcome

You are about to negotiate with **another participant**. Read your **Preferences** and the
**Scenario Info** first: they tell you what each possible deal is worth to you. The other participant
sees only their own side.

Press **Start** when you are ready; the negotiation begins once you both have. Make offers, accept your
opponent's offer, or end the negotiation. Ending without agreement gives you your *value on disagreement*.
"""


def default_home() -> Path:
    return Path.home() / "negmas" / "hani2-trial"


@dataclass
class Trial:
    home: Path
    study_dir: Path
    match: str
    participants: tuple[str, str]

    def path(self, i: int) -> str:
        """The page of participant ``i`` (0 or 1), relative to the server."""
        return f"/s/{PROJECT}/{STUDY}/play?participant={self.participants[i]}&match={self.match}"


def prepare(home: Path, *, assistant: bool = False, wait: float = 0, time_limit: int | None = None) -> Trial:
    """Write the trial project and study under ``home`` (rewritten on every run) and choose the links.

    ``assistant``: both participants have the Assistant (opponents ``human+assistant``), else neither.
    ``wait``: seconds to wait for the other participant before an AI opponent takes over (0: forever).
    """
    home = Path(home).expanduser().resolve()
    project = home / "projects" / PROJECT
    study = project / "studies" / STUDY
    study.mkdir(parents=True, exist_ok=True)
    (project / "project.yaml").write_text(
        "full_name: Human against human trial\n"
        "kind: none\n"
        "defaults:\n"
        "  practice: false\n"
        "  questionnaires: false\n"
        f"  opponents: [{'human+assistant' if assistant else 'human'}]\n",
        encoding="utf-8",
    )
    (study / "study.yaml").write_text("type: lab\ntitle: Human against human\n", encoding="utf-8")
    # the bundled welcome text speaks of an AI opponent
    (study / "announcements.md").write_text(WELCOME, encoding="utf-8")
    negotiation: dict = {"human_opponent_wait": wait, "human_opponent_absent": 600}
    if time_limit is not None:
        negotiation["time_limit"] = time_limit
    (study / "env.json").write_text(json.dumps({"negotiation": negotiation}, indent=2), encoding="utf-8")
    (study / "assistant_settings.json").write_text(json.dumps({"mode": "on" if assistant else "off"}, indent=2),
                                                    encoding="utf-8")
    if not assistant:
        (study / "autopilot_settings.json").write_text(json.dumps({"allowed": False}, indent=2), encoding="utf-8")
    else:
        (study / "autopilot_settings.json").unlink(missing_ok=True)
    run = secrets.token_hex(3)
    return Trial(home=home, study_dir=study, match=run, participants=(f"a-{run}", f"b-{run}"))
