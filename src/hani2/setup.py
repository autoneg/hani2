"""``hani2 setup``: create the settings folder with sensible defaults."""

from __future__ import annotations

import json
import shutil

from hani2.config import DEFAULT_SCENARIOS, DEFAULT_SETTINGS_DIR, settings_dir

#: old names of settings files: an install that already has the old file keeps
#: it (and gets no new file that would override it)
OLD_NAMES = {"assistant_settings.json": "support_agent_settings.json"}

FILES = [
    "env.json",
    "llm_settings.json",
    "assistant_settings.json",
    "autopilot_settings.json",
    "consent.md",
    "announcements.md",
    "scenario_order.txt",
]


def run_setup(force: bool = False, admin_password: str | None = None, quiet: bool = False) -> None:
    from hani2 import auth

    def say(msg: str) -> None:
        if not quiet:
            print(msg)

    sdir = settings_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src, dst = DEFAULT_SETTINGS_DIR / name, sdir / name
        if not src.exists():
            continue
        if dst.exists() and not force:
            say(f"  kept     {dst}")
            continue
        old = sdir / OLD_NAMES[name] if name in OLD_NAMES else None
        if old is not None and old.exists() and not dst.exists() and not force:
            say(f"  kept     {old} (old name of {name})")
            continue
        shutil.copyfile(src, dst)
        say(f"  created  {dst}")
    if admin_password:
        env = json.loads((sdir / "env.json").read_text(encoding="utf-8"))
        env.setdefault("admin", {})["password"] = admin_password
        (sdir / "env.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    qdir = sdir / "questionnaires"
    if not (qdir / "per_negotiation.example.yaml").exists():
        qdir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEFAULT_SETTINGS_DIR / "questionnaires" / "per_negotiation.yaml",
                        qdir / "per_negotiation.example.yaml")
    # The samples go to an "Examples" category: they can be picked explicitly
    # (admin scenario picker / scenario_order.txt) but do not replace the
    # freshly generated Trade / Island / Grocery scenarios.
    scen = sdir / "scenarios" / "Examples"
    for d in sorted(p for p in DEFAULT_SCENARIOS.iterdir() if p.is_dir()):
        dst = scen / d.name
        if dst.exists() and not force:
            continue
        shutil.copytree(d, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        say(f"  scenario {dst}")
    created = auth.ensure_default_users(admin_password)
    if admin_password and "admin" not in created:
        auth.set_password("admin", admin_password)
    if created:
        say(f"  users    {', '.join(created)} (passwords: admin/{admin_password or 'adminpass'}, user/userpass)")
    say(f"\nSettings are in {sdir}")
