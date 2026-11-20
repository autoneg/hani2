"""Write the scenario catalog page (docs/guide/scenario-sets.md) from the
registered scenario stories and the bundled scenario sets.

Run it again whenever a scenario text (title, descriptions, roles, issues) or a
bundled set changes::

    .venv/bin/python scripts/make_scenario_catalog.py docs/guide/scenario-sets.md

Without an argument it writes to docs/guide/scenario-sets.md next to this script.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
from hani2 import scenario_sets
from hani2.scenarios import registry

INTRO = {
 "HAN2026": "The scenarios of the ANAC 2026 Human-Agent Negotiation league.",
 "MIT2025": "Adapted from the MIT AI Negotiation Competition (2025): a used-furniture sale, a rental contract and a consulting contract.",
 "PieArena2026": "Adapted from the MBA negotiation cases of the PieArena benchmark (2026): a job offer, a license with a payment on regulatory approval, and a service quote.",
 "ANL": "Adapted from domains of the ANAC Automated Negotiation League (2010-2026), plus the HAN2026 and other types that match ANL domains (Grocery, Trade as the target-quantity case of 2025, JobOffer as the job hunt of 2025, Lease as the rental house of 2012).",
 "ANL2010": "ANL 2010 (the first ANAC): the bicycle-parts supply and tobacco-control fund domains.",
 "ANL2011": "ANL 2011: the acquisition, energy, car, city-trip (Amsterdam) and grocery domains.",
 "ANL2012": "ANL 2012: the 2010 and 2011 domains plus housekeeping and the rental house.",
 "ANL2013": "ANL 2013: the acquisition and housekeeping domains.",
 "ANL2025": "ANL 2025 (multi-deal): the bilateral cores of the target-quantity and job-hunt scenarios.",
 "ANL2026": "ANL 2026 (deception): the reused 2011 domains.",
 "IAGO": "Item splits in the style of the IAGO human-agent negotiation platform.",
 "HI2027": "Made of the set HAN2027.",
 "ANAC2027": "Made of the sets HAN2027 and HI2027 (duplicates dropped).",
 "HAN2027": "A short list with the most varied structures: an apartment lease with an issue both sides may agree on, a supply contract, a startup acquisition, a license with a contingent payment, sharing chores, matching a power profile, splitting piles of different sizes, and planning a trip together.",
}
BUILTIN = {
 "Trade": "A buyer and a seller agree on a quantity and a unit price. Each has a target quantity, penalties for too little or too much, and a non-linear value for money.",
 "Island": "Two people stranded on an island divide eight survival items.",
 "Grocery": "Two people who bought fruit together divide it.",
}
sets, default = scenario_sets.load_sets()
out = ["# Scenario sets", "",
 "HANI2 groups its scenario types into *scenario sets*. This page lists every bundled set and every scenario in it. See [Scenarios](scenarios.md#scenario-sets) for how the active set is chosen and how to define your own sets.", "",
 "Every scenario type has a fixed story: the same title, descriptions, issues and roles in every generated scenario. What changes from one scenario to the next is the utility functions: how much each issue matters to each side and how each side values the options, always in the direction the story gives. Each side's hints show its most and least important issues, its ideal deal and any drawn facts (such as an estimate or a power need).", ""]
for name, types in sets.items():
    if name == "Custom":
        continue
    out += [f"## {name}", "", INTRO.get(name, ""), "", "| Type | Title | Roles (participant first) |", "|------|-------|-------|"]
    for t in types:
        st = registry.get(t)
        if st.story is None:
            title, roles = {"Trade": ("Simple Trading Scenario", "Buyer or Seller (index 1)"), "Island": ("Island Survival Scenario", "human, agent"), "Grocery": ("Groceries Distribution", "human, agent")}[t]
            out.append(f"| [`{t}`](#{t.lower()}) | {title} | {roles} |")
        else:
            s = st.story
            roles = sorted(s.roles, key=lambda r: r != s.human_role)
            out.append(f"| [`{t}`](#{t.lower()}) | {s.title} | {', '.join(roles)} |")
    out.append("")


def _parts(s):
    """``(domain, no deal, source)`` of a story. A story read from a template folder keeps them in
    its full ``long_description`` (domain, standard paragraphs, then an optional ``*source*`` line)."""
    if s.base_info is None:
        return s.long_description.strip(), s.disagreement, s.source
    text = s.long_description.strip()
    domain, _, rest = text.partition("\n\n**The Roles**")
    if not rest:
        return text, "", ""
    _, _, tail = rest.partition("**Value on Disagreement (Reservation Value)** ")
    no_deal = tail.split(" Your reservation value is", 1)[0].strip()
    last = rest.rstrip().rsplit("\n\n", 1)[-1].strip()
    source = last[1:-1] if last.startswith("*") and last.endswith("*") and not last.startswith("**") else ""
    return domain.strip(), no_deal, source


out += ["## The scenarios", ""]
seen = []
for name, types in sets.items():
    for t in types:
        if t in seen or name == "Custom":
            continue
        seen.append(t)
        st = registry.get(t)
        out += [f"### {t}", ""]
        if st.story is None:
            out += [BUILTIN[t], "", "See the generator's own description in the *Scenario Info* tool.", ""]
            continue
        s = st.story
        domain, no_deal, source = _parts(s)
        out += [f"**{s.title}.** {s.short_description}", "", domain, ""]
        out += ["| Role | Description |", "|------|-------------|"]
        for r in sorted(s.roles):
            mark = " (participant by default)" if r == s.human_role else ""
            out.append(f"| {r}{mark} | {s.role_descriptions.get(r, '')} |")
        out += ["", "| Issue | Options | Description |", "|-------|---------|-------------|"]
        for i in s.issues:
            vals = []
            for v in i.values:
                try:
                    vals.append(i.fmt.format(v))
                except Exception:
                    vals.append(str(v))
            out.append(f"| {i.name} | {', '.join(vals)} | {i.description} |")
        if no_deal:
            out += ["", f"*No deal:* {no_deal}"]
        out += [""]
        if source:
            out += [f"*Source:* {source}", ""]
target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "docs" / "guide" / "scenario-sets.md"
target.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print(f"wrote {target}")
