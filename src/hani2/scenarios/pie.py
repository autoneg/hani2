"""Scenarios adapted from MBA negotiation cases used by the PieArena benchmark (2026).

PieArena pits language agents against MBA students on job offers, an IP
license with a payment that depends on regulatory approval, and price quotes
for a service. The stories and numbers here are our own.

The texts, issues and roles of every type are in its template folder,
``hani2/sample_scenarios/Default/<Type>/`` (YAML, editable without code); this
module only holds the functions that draw each role's preferences.
"""

from __future__ import annotations

from . import simple
from .story import Side, Story, down, peak, scores, up, weights


# --------------------------------------------------------------------------- #
# JobOffer: a recruiter and a candidate                                       #
# --------------------------------------------------------------------------- #
SALARIES = [90000, 97500, 105000, 112500, 120000]
BONUSES = [0, 5000, 10000, 15000, 20000]
STARTS = ["In 2 weeks", "In 1 month", "In 2 months", "In 3 months"]
OFFICES = ["Headquarters", "Regional office", "Mostly remote"]
VACATIONS = [15, 20, 25, 30]

# kind: (favourite office, favourite start)
_CANDIDATE_KINDS = {"family": (2, 1), "relocating": (1, 0), "career": (0, 2), "notice": (1, 3)}
_RECRUITER_KINDS = {"urgent": 2, "budget": 1, "culture": 0, "growth": 1}  # favourite office
_OFFICE_SCORES = {0: [1.0, 0.5, 0.0], 1: [0.4, 1.0, 0.6], 2: [0.0, 0.4, 1.0]}


def _candidate(rng, ctx):
    kind = rng.choice(list(_CANDIDATE_KINDS))
    office, start = _CANDIDATE_KINDS[kind]
    return Side(
        values={
            "Salary": up(SALARIES, rng),
            "Signing bonus": up(BONUSES, rng),
            "Start date": peak(STARTS, start, rng, (0.3, 0.6), (0.15, 0.35)),
            "Location": scores(OFFICES, _OFFICE_SCORES[office], rng),
            "Vacation days": up(VACATIONS, rng),
        },
        weights=weights(rng, Salary=(3, 5) if kind == "career" else (2, 3.5),
                        **{"Signing bonus": (1.5, 3) if kind == "notice" else (0.5, 1.5),
                           "Start date": (1, 2.5) if kind == "notice" else (0.3, 1.2),
                           "Location": (2, 3.5) if kind in ("family", "relocating") else (0.8, 2),
                           "Vacation days": (1.5, 3) if kind == "family" else (0.5, 1.5)}),
    )


def _recruiter(rng, ctx):
    kind = rng.choice(list(_RECRUITER_KINDS))
    office = _RECRUITER_KINDS[kind]
    return Side(
        values={
            "Salary": down(SALARIES, rng),
            "Signing bonus": down(BONUSES, rng),
            "Start date": down(STARTS, rng, (1.0, 2.5) if kind == "urgent" else (0.4, 1.0)),
            "Location": scores(OFFICES, _OFFICE_SCORES[office], rng),
            "Vacation days": down(VACATIONS, rng),
        },
        weights=weights(rng, Salary=(3.5, 5) if kind == "budget" else (2, 4),
                        **{"Signing bonus": (0.5, 1.2) if kind == "budget" else (1, 2.5),
                           "Start date": (2.5, 4) if kind == "urgent" else (0.5, 1.5),
                           "Location": (2, 3.5) if kind in ("culture", "growth") else (0.5, 1.5),
                           "Vacation days": (1.5, 3) if kind == "growth" else (0.5, 1.5)}),
    )


JOB_OFFER = Story.from_folder("JobOffer", roles={"Candidate": _candidate, "Recruiter": _recruiter})

# --------------------------------------------------------------------------- #
# License: an inventor licenses a medical device to a firm                    #
# --------------------------------------------------------------------------- #
UPFRONT = [0.5, 1.0, 1.5, 2.0, 2.5]  # million dollars
APPROVAL = [0, 2, 4, 6, 8]  # million dollars, paid only if approved
ROYALTY = [0, 2, 4, 6]  # percent of sales
EXCLUSIVITY = ["Non-exclusive", "Exclusive in one region", "Worldwide exclusive"]


def _license_setup(rng):
    step = 0.1 if simple.active() else 0.01  # simple scenarios: round estimates
    return {"p_inventor": simple.snap(rng.uniform(0.5, 0.85), step), "p_firm": simple.snap(rng.uniform(0.1, 0.4), step)}


def _inventor(rng, ctx):
    p = ctx["p_inventor"]
    other_deals = rng.random() < 0.5
    # Expected value in millions: the upfront payment is certain, the approval payment counts with probability p.
    return Side(
        values={
            "Upfront payment": up(UPFRONT, rng, (0.8, 1.2)),
            "Approval payment": up(APPROVAL, rng, (0.8, 1.2)),
            "Royalty": up(ROYALTY, rng),
            "Exclusivity": scores(EXCLUSIVITY, [1.0, 0.6, 0.0] if other_deals else [0.5, 0.8, 1.0], rng),
        },
        weights={"Upfront payment": 2.0, "Approval payment": 8.0 * p, "Royalty": rng.uniform(1.0, 2.5),
                 "Exclusivity": rng.uniform(1.0, 2.5) if other_deals else rng.uniform(0.2, 0.6)},
        hints={"Your estimate of approval": f"{p:.0%}"},
    )


def _firm(rng, ctx):
    p = ctx["p_firm"]
    return Side(
        values={
            "Upfront payment": down(UPFRONT, rng, (0.8, 1.2)),
            "Approval payment": down(APPROVAL, rng, (0.8, 1.2)),
            "Royalty": down(ROYALTY, rng),
            "Exclusivity": up(EXCLUSIVITY, rng),
        },
        weights={"Upfront payment": 2.0, "Approval payment": 8.0 * p, "Royalty": rng.uniform(1.0, 2.5),
                 "Exclusivity": rng.uniform(1.0, 2.5)},
        hints={"Your estimate of approval": f"{p:.0%}"},
    )


LICENSE = Story.from_folder("License", roles={"Firm": _firm, "Inventor": _inventor}, setup=_license_setup)

# --------------------------------------------------------------------------- #
# HomeRepair: a homeowner and a contractor                                    #
# --------------------------------------------------------------------------- #
PRICES = [4000, 4500, 5000, 5500, 6000, 6500]
WHEN = ["This week", "Next week", "In two weeks", "Next month"]
WARRANTY = ["No warranty", "6 months", "1 year", "2 years"]
CLEANUP = ["Homeowner clears up", "Contractor clears up"]


def _homeowner(rng, ctx):
    urgent = rng.random() < 0.5
    return Side(
        values={
            "Price": down(PRICES, rng),
            "Start": down(WHEN, rng, (1.2, 2.5)) if urgent else down(WHEN, rng, (0.3, 0.8)),
            "Warranty": up(WARRANTY, rng),
            "Cleanup": {"Homeowner clears up": 0.0, "Contractor clears up": 1.0},
        },
        weights=weights(rng, Price=(3, 5), Start=(2.5, 4) if urgent else (0.5, 1.5), Warranty=(1, 2.5),
                        Cleanup=(0.3, 1)),
    )


def _contractor(rng, ctx):
    busy = rng.random() < 0.5
    return Side(
        values={
            "Price": up(PRICES, rng),
            "Start": up(WHEN, rng) if busy else down(WHEN, rng),
            "Warranty": down(WARRANTY, rng),
            "Cleanup": {"Homeowner clears up": 1.0, "Contractor clears up": rng.uniform(0.3, 0.7)},
        },
        weights=weights(rng, Price=(3, 5), Start=(1, 2.5), Warranty=(1, 2.5), Cleanup=(0.3, 1)),
    )


HOME_REPAIR = Story.from_folder("HomeRepair", roles={"Contractor": _contractor, "Homeowner": _homeowner})

STORIES = [JOB_OFFER, LICENSE, HOME_REPAIR]
