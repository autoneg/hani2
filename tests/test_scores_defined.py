"""Scores you define (``hani2.evaluation.scores``): weights that sum to 1, the ``missing`` policies,
``min_coverage`` across entrants, scores inside scores, the checks (cycles, key clashes, directions,
normalisers, the participant-level rule), ``scores:`` / ``scores_enabled`` in project and study files,
``hani2 scores list|show|check|set|remove`` and the admin endpoints. The built-in scores are
definitions now; their values are compared with the formula they had before."""

import math
import random

import pytest
import yaml

from hani2 import projects
from hani2.evaluation import scores as S
from hani2.evaluation.base import num


# --------------------------------------------------------------------------- #
# The built-ins: the same values as before they became definitions             #
# --------------------------------------------------------------------------- #
#: the built-in scores as they were: (name, zero_if, needs_assistant, [(column, weight, rule)])
OLD = [
    ('han_outcome', ['opponent_failed'], False, [('opponent_advantage', 1, 'advantage')]),
    ('han_interaction', [], False, [('scale_opponent_kindness_norm', 1, 'unit'), ('scale_opponent_intelligence_norm', 1, 'unit'), ('scale_opponent_humanlike_norm', 1, 'unit'), ('scale_relationship_norm', 1, 'unit'), ('scale_satisfaction_norm', 0.5, 'unit'), ('jo_overall', 1, 'likert7'), ('jo_communication', 0.5, 'likert7'), ('jo_consistency', 0.5, 'likert7'), ('jo_human_likeness', 0.5, 'likert7'), ('opponent_failed', 1, 'inverse'), ('opponent_irrational_accept', 0.5, 'inverse')]),  # noqa: E501
    ('hi_outcome', [], False, [('human_advantage', 1, 'advantage')]),
    ('hi_assistant', [], True, [('ja_overall', 1, 'likert7'), ('ja_helpfulness', 0.5, 'likert7'), ('ja_autonomy_respect', 0.5, 'likert7'), ('assertions_met', 1, 'unit'), ('task_communicated', 1, 'unit'), ('assistant_critical_errors', 1, 'count'), ('assistant_errors', 0.5, 'count'), ('irrational_suggestions', 1, 'count'), ('fn_success_rate', 0.5, 'unit'), ('unanswered_messages', 0.5, 'count'), ('scale_ueq_pragmatic_norm', 0.5, 'unit'), ('scale_tam_usefulness_norm', 0.5, 'unit'), ('scale_felt_heard_norm', 0.5, 'unit'), ('scale_intention_to_use_norm', 0.5, 'unit')]),  # noqa: E501
    ('hi_team', [], True, [('human_overrode_harmfully', 1, 'count'), ('human_critical_errors', 1, 'count'), ('jh_use_of_assistant', 1, 'likert7'), ('jh_engagement', 0.5, 'likert7'), ('always_follows', 0.5, 'inverse'), ('click_through', 0.5, 'inverse'), ('irrational_accept', 1, 'inverse'), ('welfare_optimality', 0.5, 'unit')]),  # noqa: E501
    ('hi_interaction', [], True, [('hi_assistant', 1, 'unit'), ('hi_team', 1, 'unit')]),
]
OLD_RULES = {
    "unit": lambda x: min(1.0, max(0.0, x)),
    "likert7": lambda x: min(1.0, max(0.0, (x - 1) / 6)),
    "advantage": lambda x: min(1.0, max(0.0, x)),
    "inverse": lambda x: 1.0 - min(1.0, max(0.0, x)),
    "count": lambda x: 1.0 / (1.0 + max(0.0, x)),
}


def old_score_row(row, weights=None, only=None):
    """``score_row`` as it was (weights: ``{score: {column: weight}}`` overrides)."""
    r, out = dict(row), {}
    for name, zero_if, needs, comps in OLD:
        w = {c: float(wt) for c, wt, _ in comps}
        w.update((weights or {}).get(name, {}))
        sel = (only or {}).get(name)
        if needs and str(r.get("support_agent") or "none") == "none":
            v, cov = None, None
        elif any(num(r.get(z)) == 1 for z in zero_if):
            v, cov = 0.0, 1.0
        else:
            total = got = acc = 0.0
            for c, _, rule in comps:
                wt = w.get(c, 0.0)
                if wt <= 0 or (sel is not None and c not in sel):
                    continue
                total += wt
                x = num(r.get(c))
                if x is None:
                    continue
                acc += wt * OLD_RULES[rule](x)
                got += wt
            if got <= 0:
                v, cov = None, (0.0 if total > 0 else None)
            else:
                v, cov = acc / got, got / total
        r[name] = v
        out[name], out[f"{name}_coverage"] = v, cov
    return out


def _random_row(rng):
    row = {"support_agent": rng.choice(["none", "A", None, "B"])}
    for _, _, _, comps in OLD:
        for c, _, rule in comps:
            if c.startswith("hi_") or rng.random() < 0.3:
                continue  # missing
            if rule == "likert7":
                row[c] = rng.choice([1, 2, 4, 6.5, 7, 0, 9, rng.uniform(-3, 10)])
            elif rule == "count":
                row[c] = rng.choice([0, 1, 2, 5, 40, -1, rng.uniform(0, 100)])
            else:
                row[c] = rng.choice([0, 1, 0.5, -0.2, 1.4, rng.random(), float("nan"), "x"])
    return row


def _same(a, b):
    assert set(b) <= set(a)
    for k, v in b.items():
        if v is None:
            assert a[k] is None, k
        else:
            assert a[k] == pytest.approx(v, rel=1e-12, abs=1e-12), k


def test_builtins_keep_their_values():
    rng = random.Random(7)
    for _ in range(600):
        row = _random_row(rng)
        _same(S.score_row(row), old_score_row(row))
    # the failing opponent, no Assistant, and the restricted components of a board
    _same(S.score_row({"opponent_advantage": 0.9, "opponent_failed": 1}),
          old_score_row({"opponent_advantage": 0.9, "opponent_failed": 1}))
    only = {"hi_assistant": {"ja_overall", "assistant_errors"}, "hi_team": set(), "hi_interaction": {"hi_assistant"}}
    for _ in range(200):
        row = _random_row(rng)
        _same(S.score_row(row, only=only), old_score_row(row, only=only))


def test_builtins_keep_their_weight_overrides():
    rng = random.Random(3)
    opts = {"scores": {"hi_assistant": {"weights": {"ja_overall": 2, "fn_success_rate": 0}}}}
    for _ in range(200):
        row = _random_row(rng)
        _same(S.score_row(row, opts), old_score_row(row, {"hi_assistant": {"ja_overall": 2, "fn_success_rate": 0}}))


def test_builtins_as_definitions():
    d = S.definition(S.BY_NAME["hi_assistant"])
    assert d["builtin"] and d["needs_assistant"] and d["track"] == "hi"
    assert sum(c["weight"] for c in d["components"]) == pytest.approx(1)
    by = {c["criterion"]: c for c in d["components"]}
    assert by["ja_overall"]["weight"] == pytest.approx(1 / 9.5)
    assert by["ja_overall"]["normaliser"] == {"kind": "bounded", "lo": 1.0, "hi": 7.0}
    assert by["assistant_errors"] == {**by["assistant_errors"], "direction": "lower",
                                      "normaliser": {"kind": "reciprocal", "scale": 1.0}}
    # the built-ins' counts keep a fixed scale: a frozen reference does not change them
    ref = {"criteria": {"assistant_errors": {"scale": 9.0}}}
    row = {"support_agent": "A", "assistant_errors": 1}
    assert S.score_row(row, reference=ref)["hi_assistant"] == pytest.approx(0.5)
    assert S.definition(S.BY_NAME["han_outcome"])["zero_if"] == ["opponent_failed"]
    # utility: the Human side's advantage alone, for any session
    assert S.score_row({"support_agent": "none", "human_advantage": 0.4})["utility"] == pytest.approx(0.4)
    assert S.BY_NAME["utility"].track == "any"


# --------------------------------------------------------------------------- #
# Definitions                                                                  #
# --------------------------------------------------------------------------- #
def _defn(**kw):
    d = {"title": "My score", "track": "hi",
         "components": [{"criterion": "human_advantage", "weight": 0.5}, {"criterion": "ja_overall", "weight": 0.3},
                        {"criterion": "n_offers", "weight": 0.2, "direction": "lower"}]}
    d.update(kw)
    return d


def _resolve(defs, **kw):
    return S.resolve(None, None, project_scores=defs, **kw)


def test_weights_must_sum_to_one():
    sc, p, w = S.parse_definition("mine", _defn())
    assert sc is not None and not p and not w
    bad = _defn(components=[{"criterion": "human_advantage", "weight": 0.5}, {"criterion": "ja_overall", "weight": 0.4}])
    sc, p, _ = S.parse_definition("mine", bad)
    assert sc is None and "sum to 0.9 (90 %), not 1 (100 %)" in p[0]
    # within 1e-6 is fine
    ok = _defn(components=[{"criterion": "human_advantage", "weight": 0.5 + 5e-7}, {"criterion": "ja_overall", "weight": 0.5}])
    assert S.parse_definition("mine", ok)[0] is not None
    # a file being loaded: rescaled, with a warning
    sc, p, w = S.parse_definition("mine", bad, strict=False)
    assert not p and "rescaled" in w[0]
    assert [c.weight for c in sc.components] == [pytest.approx(5 / 9), pytest.approx(4 / 9)]
    # negative weights and a zero sum are never rescaled
    neg = _defn(components=[{"criterion": "human_advantage", "weight": 1.5}, {"criterion": "ja_overall", "weight": -0.5}])
    assert "≥ 0" in " ".join(S.parse_definition("mine", neg, strict=False)[1])
    zero = _defn(components=[{"criterion": "human_advantage", "weight": 0}])
    assert "sum to 0" in S.parse_definition("mine", zero, strict=False)[1][0]
    assert "≥ 0" in S.parse_definition("mine", _defn(components=[{"criterion": "x", "weight": True}]))[1][0]


def test_definition_form_is_checked():
    def problems(d, key="mine"):
        return " ".join(S.parse_definition(key, d)[1])

    assert "track must be" in problems(_defn(track="both"))
    assert "missing must be" in problems(_defn(missing="ignore"))
    assert "min_coverage" in problems(_defn(min_coverage=2))
    assert "unknown key(s) wieght" in problems(_defn(components=[{"criterion": "agreement", "wieght": 1}]))
    assert "non-empty list" in problems(_defn(components=[]))
    assert "given twice" in problems(_defn(components=[{"criterion": "agreement", "weight": 0.5}] * 2))
    assert "direction must be" in problems(_defn(components=[{"criterion": "agreement", "weight": 1, "direction": "up"}]))
    assert "unknown normaliser kind" in problems(
        _defn(components=[{"criterion": "agreement", "weight": 1, "normaliser": {"kind": "log"}}]))
    assert "must be a mapping" in problems([1, 2])
    # keys: no column names, no built-ins (read-only), no questionnaire-like names
    assert "is the name of a column" in problems(_defn(), "agreement")
    assert "is the name of a column" in problems(_defn(), "n_offers_coverage")
    assert "read-only" in problems(_defn(), "hi_team")
    assert "questionnaire" in problems(_defn(), "q_mine")
    assert "use a letter" in problems(_defn(), "1st")
    assert "contains itself" in problems(_defn(components=[{"criterion": "mine", "weight": 1}]))


def test_resolve_fills_in_the_catalogue_and_refuses_what_it_cannot():
    ss = _resolve({"mine": _defn()})
    assert not ss.problems and "mine" in ss.scores and "mine" in ss.enabled
    by = {c.column: c for c in ss.scores["mine"].components}
    assert by["human_advantage"].normaliser == {"kind": "advantage"} and by["human_advantage"].direction == "higher"
    assert by["ja_overall"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 7.0}
    assert by["n_offers"].direction == "lower" and by["n_offers"].normaliser["kind"] == "saturating"
    # a descriptive criterion needs a direction
    ss = _resolve({"mine": _defn(components=[{"criterion": "n_offers", "weight": 1}])})
    assert "mine" not in ss.scores and "has no direction" in ss.problems[0]
    # an unknown criterion
    ss = _resolve({"mine": _defn(components=[{"criterion": "nope", "weight": 1}])})
    assert "unknown criterion" in ss.problems[0] and "mine" not in ss.scores
    # an explicit normaliser wins
    ss = _resolve({"mine": _defn(components=[{"criterion": "n_offers", "weight": 1, "direction": "lower",
                                              "normaliser": {"kind": "clip", "lo": 0, "hi": 10}}])})
    assert S.score_row({"n_offers": 2}, scores=ss.needed(["mine"]))["mine"] == pytest.approx(0.8)
    # strict: weights that do not sum to 1 are refused
    bad = {"mine": _defn(components=[{"criterion": "human_advantage", "weight": 2}])}
    assert "not 1 (100 %)" in S.check(project_scores=bad)[0]
    assert not _resolve(bad).problems and _resolve(bad).warnings


def test_scores_inside_scores_and_cycles():
    defs = {"inner": {"components": [{"criterion": "human_advantage", "weight": 1}]},
            "outer": {"components": [{"criterion": "inner", "weight": 0.5}, {"criterion": "hi_team", "weight": 0.5}]}}
    ss = _resolve(defs)
    assert not ss.problems
    keys = list(ss.scores)
    assert keys.index("inner") < keys.index("outer")
    row = {"support_agent": "A", "human_advantage": 0.4, "irrational_accept": 0}
    out = S.score_row(row, scores=ss.needed(["outer"]))
    assert out["hi_team"] == 1 and out["outer"] == pytest.approx(0.5 * 0.4 + 0.5 * 1)
    assert [s.name for s in ss.needed(["outer"])][-1] == "outer"
    flat = S.flattened("outer", ss.scores)
    assert flat["human_advantage"] == pytest.approx(0.5) and sum(flat.values()) == pytest.approx(1)
    # cycles are refused (and a score that contains one has a problem too)
    cyc = {"a": {"components": [{"criterion": "b", "weight": 1}]},
           "b": {"components": [{"criterion": "a", "weight": 1}]},
           "c": {"components": [{"criterion": "a", "weight": 1}]}}
    ss = _resolve(cyc)
    assert not {"a", "b", "c"} & set(ss.scores)
    assert any("cycle" in p for p in ss.problems) and any("'c' contains 'a'" in p for p in ss.problems)
    assert any("cycle" in p for p in S.file_problems(cyc)[0])


def test_missing_policies():
    comps = [{"criterion": "human_advantage", "weight": 0.5}, {"criterion": "ja_overall", "weight": 0.5}]
    row = {"human_advantage": 0.6}
    vals = {}
    for policy in S.MISSING_POLICIES:
        ss = _resolve({"m": {"components": comps, "missing": policy}})
        out = S.score_row(row, scores=ss.needed(["m"]))
        vals[policy] = (out["m"], out["m_coverage"])
    assert vals["renormalise"] == (pytest.approx(0.6), 0.5)
    assert vals["zero"] == (pytest.approx(0.3), 0.5)
    assert vals["skip_game"] == (None, 0.5)
    # with every value there, the policies agree
    for policy in S.MISSING_POLICIES:
        ss = _resolve({"m": {"components": comps, "missing": policy}})
        assert S.score_row({"human_advantage": 0.6, "ja_overall": 7}, scores=ss.needed(["m"]))["m"] == pytest.approx(0.8)


def test_min_coverage_drops_a_component_for_everyone():
    comps = [{"criterion": "human_advantage", "weight": 0.5}, {"criterion": "q_x", "weight": 0.5}]
    from hani2.evaluation import criteria as crit
    forms = {"per_negotiation": {"questions": [{"id": "x", "type": "likert5", "text": "X?", "direction": "higher"}]}, "post_session": None}
    cat = crit.catalogue(forms=forms)
    ss = S.resolve(None, None, project_scores={"m": {"track": "hi", "components": comps, "min_coverage": 0.5}},
                   criteria=cat)
    assert not ss.problems
    rows = ([{"support_agent": "A", "human_advantage": 0.5, "q_x": 5}] * 4
            + [{"support_agent": "B", "human_advantage": 0.5, "q_x": 5}]
            + [{"support_agent": "B", "human_advantage": 0.5}] * 3)
    scored = S.score_rows(rows, ss, names=["m"], group=lambda r: r["support_agent"])
    # B answered in 1 of 4 games (< 0.5): q_x is dropped for A too, so both are scored on the advantage
    assert {r["m"] for r in scored} == {0.5} and {r["m_coverage"] for r in scored} == {1.0}
    active = S.active_components(rows, ss.needed(["m"]), lambda r: r["support_agent"])
    assert active["m"] == {"human_advantage"}
    # without the drop, A's games use the answer
    plain = S.score_rows(rows, ss, names=["m"])
    assert plain[0]["m"] == pytest.approx(0.75)
    assert S.weights_in_effect(ss.scores["m"], active["m"]) == {"human_advantage": 1.0}


def test_participant_level_rule():
    from hani2.evaluation import criteria as crit
    forms = {"per_negotiation": None, "post_session": {"questions": [{"id": "o", "type": "likert7", "text": "O?", "direction": "higher"}]}}
    comps = [{"criterion": "human_advantage", "weight": 0.5}, {"criterion": "post_q_o", "weight": 0.5}]
    one = [{"participant": "p1", "support_agent": "A", "post_q_o": 5}, {"participant": "p1", "support_agent": "A"}]
    two = one + [{"participant": "p2", "support_agent": "A"}, {"participant": "p2", "support_agent": "B"}]
    for track, rows, ok in (("hi", one, True), ("hi", two, False), ("han", two, True), ("hi", None, True)):
        cat = crit.catalogue(forms=forms)
        ss = S.resolve(None, None, project_scores={"m": {"track": track, "components": comps}}, criteria=cat, rows=rows)
        assert ("m" in ss.scores) is ok, (track, ss.problems)
        if not ok:
            assert "post-session answer cannot be used in an HI score" in ss.problems[0]


# --------------------------------------------------------------------------- #
# project.yaml and study.yaml                                                  #
# --------------------------------------------------------------------------- #
def test_defaults_keys():
    assert {"scores", "scores_enabled", "normalisation"} <= set(projects.DEFAULT_KEYS)


@pytest.fixture
def proj(hani2_home):
    projects.create_project("HI2027", kind="assistant", scores={"hi_score": _defn()})
    projects.create_study("HI2027/play", type="online")
    return "HI2027"


def test_scores_in_project_and_study_files(proj):
    pr = projects.load_project("HI2027")
    assert "hi_score" in pr.defaults["scores"] and not pr.errors
    ss = S.resolve("HI2027")
    assert "hi_score" in ss.scores and ss.scores["hi_score"].origin == "project"
    # by default every built-in and every defined score is enabled
    assert set(ss.enabled) == set(S.BY_NAME) | {"hi_score"} and ss.enabled_set_by == "default"
    # a study adds one, redefines one by key (merged key by key) and picks the enabled ones
    projects.create_study("HI2027/play", scores={
        "study_only": {"components": [{"criterion": "agreement", "weight": 1}]},
        "hi_score": _defn(title="Redefined")}, scores_enabled=["hi_score", "utility", "study_only"])
    ss = S.resolve("HI2027", "play")
    assert ss.scores["hi_score"].title == "Redefined" and ss.scores["hi_score"].origin == "study"
    assert ss.enabled == ["hi_score", "utility", "study_only"] and ss.enabled_set_by == "study"
    assert "study_only" not in S.resolve("HI2027").scores
    # the study's key: null removes the project's score
    projects.create_study("HI2027/play", scores={"hi_score": None})
    st = projects.load_study("HI2027/play")
    assert "hi_score" not in st.overrides["scores"]  # create_study merges per key: None deletes the study's own
    f = projects.study_dir(projects.StudyRef("HI2027", "play")) / projects.STUDY_FILE
    data = yaml.safe_load(f.read_text())
    data["scores"]["hi_score"] = None  # written by hand: the study drops the project's score
    f.write_text(yaml.safe_dump(data))
    assert not projects.load_study("HI2027/play").errors
    assert "hi_score" not in S.resolve("HI2027", "play").scores and "hi_score" in S.resolve("HI2027").scores
    # updating a project merges scores per key too
    projects.create_project("HI2027", scores={"second": {"components": [{"criterion": "agreement", "weight": 1}]}})
    assert set(projects.load_project("HI2027").defaults["scores"]) == {"hi_score", "second"}
    projects.create_project("HI2027", scores={"second": None})
    assert set(projects.load_project("HI2027").defaults["scores"]) == {"hi_score"}


def test_saving_refuses_and_loading_rescales(proj, capsys):
    bad = {"bad": {"components": [{"criterion": "agreement", "weight": 0.5}, {"criterion": "human_advantage", "weight": 0.25}]}}
    with pytest.raises(ValueError, match=r"not 1 \(100 %\)"):
        projects.create_project("HI2027", scores=bad)
    with pytest.raises(ValueError, match="cycle"):
        projects.create_study("HI2027/play", scores={"a": {"components": [{"criterion": "a2", "weight": 1}]},
                                                     "a2": {"components": [{"criterion": "a", "weight": 1}]}})
    with pytest.raises(ValueError, match="scores_enabled"):
        projects.create_study("HI2027/play", scores_enabled="hi_score")
    # a hand-edited file: rescaled on load, with a warning in the log and in the errors
    f = projects.project_dir("HI2027") / projects.PROJECT_FILE
    data = yaml.safe_load(f.read_text())
    data["scores"].update(bad)
    f.write_text(yaml.safe_dump(data))
    pr = projects.load_project("HI2027")
    assert any(e.startswith("warning: ") and "rescaled" in e for e in pr.errors)
    assert "WARNING" in capsys.readouterr().out
    ss = S.resolve("HI2027")
    assert "bad" in ss.scores and sum(c.weight for c in ss.scores["bad"].components) == pytest.approx(1)
    assert ss.warnings and not ss.problems
    # a score with a problem in a file is left out, and named
    data["scores"]["broken"] = {"components": [{"criterion": "nope", "weight": 1}]}
    f.write_text(yaml.safe_dump(data))
    ss = S.resolve("HI2027")
    assert "broken" not in ss.scores and any("'broken'" in p for p in ss.problems)


def test_normalisation_is_a_project_default(proj):
    projects.create_project("HI2027", normalisation={"reference": {"studies": ["play"], "end": "2027-03-31"}})
    pr = projects.load_project("HI2027")
    assert pr.defaults["normalisation"]["reference"]["studies"] == ["play"] and "normalisation" not in pr.extra
    from hani2.evaluation import criteria

    assert criteria.reference_setting("HI2027") == {"studies": ["play"], "end": "2027-03-31"}
    with pytest.raises(ValueError, match="must be a date"):
        projects.create_project("HI2027", normalisation={"reference": {"end": "March"}})
    with pytest.raises(ValueError, match="project setting"):
        projects.create_study("HI2027/play", normalisation={"reference": {"studies": ["play"]}})


def test_enabled_scores_are_checked(proj):
    ss = S.resolve("HI2027", project_enabled=["hi_score", "nope"])
    assert ss.enabled == ["hi_score"] and "unknown score(s) nope" in ss.problems[0]
    # an enabled score is computed with the scores inside it
    projects.create_project("HI2027", scores={"outer": {"components": [{"criterion": "hi_score", "weight": 1}]}},
                            scores_enabled=["outer"])
    ss = S.resolve("HI2027")
    assert [s.name for s in ss.needed()] == ["hi_score", "outer"]
    # defined scores are criteria of the catalogue
    from hani2.evaluation import criteria

    by = criteria.by_id(criteria.catalogue("HI2027"))
    assert by["outer"].source == "score" and by["hi_score"].cost == "judge"


def test_score_rows_with_a_reference(proj):
    ss = S.resolve("HI2027")
    ref = {"criteria": {"n_offers": {"scale": 4.0}}}
    row = {"support_agent": "A", "human_advantage": 1.0, "ja_overall": 7, "n_offers": 4}
    out = S.score_rows([row], ss, names=["hi_score"], reference=ref)[0]
    assert out["hi_score"] == pytest.approx(0.5 + 0.3 + 0.2 * 0.5)
    assert not math.isnan(out["hi_score_coverage"])


# --------------------------------------------------------------------------- #
# Saving, the command line and the admin API                                   #
# --------------------------------------------------------------------------- #
def test_save_delete_enable_duplicate(proj):
    S.save_score("HI2027", None, "two", {"components": [{"criterion": "agreement", "weight": 1}]})
    assert "two" in S.resolve("HI2027").scores
    with pytest.raises(ValueError, match="not 1"):
        S.save_score("HI2027", None, "two", {"components": [{"criterion": "agreement", "weight": 0.9}]})
    with pytest.raises(ValueError, match="no direction"):
        S.save_score("HI2027", None, "two", {"components": [{"criterion": "n_offers", "weight": 1}]})
    with pytest.raises(ValueError, match="read-only"):
        S.save_score("HI2027", None, "hi_team", {"components": [{"criterion": "agreement", "weight": 1}]})
    # a score that another contains, or that is enabled, cannot be removed
    S.save_score("HI2027", None, "outer", {"components": [{"criterion": "two", "weight": 1}]})
    with pytest.raises(ValueError, match="'outer', component 'two'"):
        S.delete_score("HI2027", None, "two")
    assert S.save_enabled("HI2027", None, ["outer", "utility"]) == ["outer", "utility"]
    with pytest.raises(ValueError, match="unknown score"):
        S.save_enabled("HI2027", None, ["outer", "nope"])
    with pytest.raises(ValueError, match="unknown score"):
        S.delete_score("HI2027", None, "outer")
    S.save_enabled("HI2027", None, None)
    S.delete_score("HI2027", None, "outer")
    S.delete_score("HI2027", None, "two")
    with pytest.raises(KeyError):
        S.delete_score("HI2027", None, "two")
    # a problem that is there already does not block another change
    f = projects.project_dir("HI2027") / projects.PROJECT_FILE
    data = yaml.safe_load(f.read_text())
    data["scores"]["broken"] = {"components": [{"criterion": "nope", "weight": 1}]}
    f.write_text(yaml.safe_dump(data))
    S.save_score("HI2027", None, "three", {"components": [{"criterion": "agreement", "weight": 1}]})
    # a study's file: under overrides when it keeps them there
    sf = projects.study_dir(projects.StudyRef("HI2027", "play")) / projects.STUDY_FILE
    sd = yaml.safe_load(sf.read_text())
    sd["overrides"] = {"scores": {}}
    sf.write_text(yaml.safe_dump(sd))
    S.save_score("HI2027", "play", "local", {"components": [{"criterion": "agreement", "weight": 1}]})
    assert "local" in yaml.safe_load(sf.read_text())["overrides"]["scores"]
    # duplicating a built-in: editable, rescaled to sum to 1, the same values
    S.duplicate("HI2027", None, "hi_assistant", "my_assistant")
    ss = S.resolve("HI2027")
    mine = ss.scores["my_assistant"]
    assert mine.origin == "project" and sum(c.weight for c in mine.components) == pytest.approx(1, abs=1e-9)
    row = {"support_agent": "A", "ja_overall": 6, "assistant_critical_errors": 1, "fn_success_rate": 0.5}
    assert S.score_row(row, scores=ss.needed(["my_assistant"]))["my_assistant"] == pytest.approx(S.score_row(row)["hi_assistant"])
    with pytest.raises(KeyError):
        S.duplicate("HI2027", None, "nope", "x")


def test_scores_cli(proj, tmp_path):
    from typer.testing import CliRunner

    from hani2 import cli

    run = CliRunner().invoke
    r = run(cli.app, ["scores", "list", "HI2027"])
    assert r.exit_code == 0, r.output
    assert "* hi_score" in r.output and "project" in r.output and "* hi_team" in r.output
    r = run(cli.app, ["scores", "show", "HI2027", "hi_score"])
    assert r.exit_code == 0, r.output
    assert "50.00 %  human_advantage" in r.output and "advantage" in r.output and "components:" in r.output
    r = run(cli.app, ["scores", "show", "HI2027", "hi_interaction"])
    assert "flattened to criteria" in r.output
    assert run(cli.app, ["scores", "show", "HI2027", "nope"]).exit_code == 1
    r = run(cli.app, ["scores", "check", "HI2027/play"])
    assert r.exit_code == 0 and "ok:" in r.output
    # set: refused unless the weights sum to 1
    r = run(cli.app, ["scores", "set", "HI2027", "x", "--json",
                      '{"components": [{"criterion": "agreement", "weight": 0.4}]}'])
    assert r.exit_code == 1 and "not 1 (100 %)" in r.output
    f = tmp_path / "d.yaml"
    f.write_text(yaml.safe_dump({"title": "X", "components": [{"criterion": "agreement", "weight": 1}]}))
    r = run(cli.app, ["scores", "set", "HI2027/play", "x", "-f", str(f)])
    assert r.exit_code == 0, r.output
    assert "x" in S.resolve("HI2027", "play").scores and "x" not in S.resolve("HI2027").scores
    r = run(cli.app, ["scores", "enable", "HI2027/play", "x,utility"])
    assert r.exit_code == 0 and "x, utility" in r.output
    assert run(cli.app, ["scores", "enable", "HI2027/play", "nope"]).exit_code == 1
    assert run(cli.app, ["scores", "remove", "HI2027/play", "x"]).exit_code == 1  # still enabled
    assert run(cli.app, ["scores", "enable", "HI2027/play", "--default"]).exit_code == 0
    assert run(cli.app, ["scores", "remove", "HI2027/play", "x"]).exit_code == 0
    assert run(cli.app, ["scores", "remove", "HI2027/play", "x"]).exit_code == 1
    r = run(cli.app, ["scores", "duplicate", "HI2027", "hi_team", "my_team"])
    assert r.exit_code == 0, r.output
    # check fails on a hand-edited file whose weights do not sum to 1 (loading rescales it)
    pf = projects.project_dir("HI2027") / projects.PROJECT_FILE
    data = yaml.safe_load(pf.read_text())
    data["scores"]["hand"] = {"components": [{"criterion": "agreement", "weight": 3}]}
    pf.write_text(yaml.safe_dump(data))
    r = run(cli.app, ["scores", "check", "HI2027"])
    assert r.exit_code == 1 and "'hand'" in r.output and "not 1" in r.output
    out = tmp_path / "s.json"
    assert run(cli.app, ["scores", "list", "HI2027", "-o", str(out)]).exit_code == 0
    import json

    body = json.loads(out.read_text())
    assert any(s["key"] == "hand" for s in body["scores"]) and body["warnings"]


@pytest.fixture
def client(hani2_home):
    from fastapi.testclient import TestClient

    from hani2.server import app

    with TestClient(app) as c:
        yield c


def test_admin_score_endpoints(client, proj):
    assert client.get("/api/admin/scores", params={"project": "HI2027"}).status_code in (401, 403)
    assert client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
    r = client.get("/api/admin/scores", params={"project": "HI2027"})
    assert r.status_code == 200, r.text
    by = {s["key"]: s for s in r.json()["scores"]}
    assert by["hi_team"]["builtin"] and by["hi_team"]["origin"] == "builtin"
    assert sum(c["weight"] for c in by["hi_team"]["components"]) == pytest.approx(1)
    assert by["hi_score"]["origin"] == "project" and by["hi_score"]["enabled"]
    assert client.get("/api/admin/scores", params={"project": "nope"}).status_code == 404
    assert client.get("/api/admin/scores", params={"study": "HI2027/nope"}).status_code == 404
    assert client.get("/api/admin/scores", params={"project": "../x"}).status_code == 400
    # save: 400 unless the weights sum to 1 and every check passes
    bad = {"components": [{"criterion": "agreement", "weight": 0.5}]}
    r = client.put("/api/admin/projects/HI2027/scores/mine", json=bad)
    assert r.status_code == 400 and "not 1 (100 %)" in r.json()["detail"]
    r = client.put("/api/admin/projects/HI2027/scores/agreement", json={"components": [{"criterion": "human_advantage", "weight": 1}]})
    assert r.status_code == 400 and "name of a column" in r.json()["detail"]
    r = client.put("/api/admin/projects/HI2027/scores/mine",
                   json={"components": [{"criterion": "n_offers", "weight": 1}]})
    assert r.status_code == 400 and "no direction" in r.json()["detail"]
    good = {"title": "Mine", "components": [{"criterion": "agreement", "weight": 0.25},
                                            {"criterion": "hi_score", "weight": 0.75}]}
    r = client.put("/api/admin/projects/HI2027/scores/mine", json=good)
    assert r.status_code == 200, r.text
    assert any(s["key"] == "mine" for s in r.json()["scores"])
    # a cycle
    r = client.put("/api/admin/projects/HI2027/scores/hi_score",
                   json={"components": [{"criterion": "mine", "weight": 1}]})
    assert r.status_code == 400 and "cycle" in r.json()["detail"]
    # study: add, redefine by key, enable, delete
    r = client.put("/api/admin/projects/HI2027/studies/play/scores/hi_score",
                   json={"title": "Play's", "components": [{"criterion": "agreement", "weight": 1}]})
    assert r.status_code == 200, r.text
    r = client.get("/api/admin/scores", params={"study": "HI2027/play"})
    assert {s["key"]: s for s in r.json()["scores"]}["hi_score"]["origin"] == "study"
    r = client.put("/api/admin/projects/HI2027/studies/play/scores_enabled", json={"enabled": ["mine", "utility"]})
    assert r.status_code == 200 and r.json()["enabled"] == ["mine", "utility"]
    r = client.put("/api/admin/projects/HI2027/studies/play/scores_enabled", json={"enabled": ["nope"]})
    assert r.status_code == 400
    r = client.put("/api/admin/projects/HI2027/scores_enabled", json={"enabled": None})
    assert r.status_code == 200
    # removing a score that another contains: 409
    assert client.delete("/api/admin/projects/HI2027/scores/hi_score").status_code == 409
    assert client.delete("/api/admin/projects/HI2027/studies/play/scores/hi_score").status_code == 200
    assert client.delete("/api/admin/projects/HI2027/studies/play/scores/hi_score").status_code == 404
    # duplicate a built-in
    r = client.post("/api/admin/projects/HI2027/scores/my_han/duplicate", json={"from": "han_interaction"})
    assert r.status_code == 200, r.text
    assert client.post("/api/admin/projects/HI2027/scores/x/duplicate", json={"from": "nope"}).status_code == 404
    # whole-file saves get the same checks
    r = client.get("/api/admin/projects/HI2027").json()
    data = {k: v for k, v in r.items() if k in ("name", "kind", "defaults")}
    data["defaults"]["scores"]["mine"]["components"][0]["criterion"] = "nope"
    r = client.put("/api/admin/projects/HI2027", json={"data": data})
    assert r.status_code == 400 and "unknown criterion" in r.json()["detail"]
    r = client.put("/api/admin/projects/HI2027/studies/play", json={"yaml": "type: online\nscores:\n  s1:\n    components:\n"
                                                                          "      - {criterion: n_offers, weight: 1}\n"})
    assert r.status_code == 400 and "no direction" in r.json()["detail"]
    r = client.put("/api/admin/projects/HI2027/studies/newone", json={"yaml": "type: online\nscores:\n  s1:\n    components:\n"
                                                                            "      - {criterion: agreement, weight: 0.5}\n"})
    assert r.status_code == 400 and "not 1" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# zero_if and needs_assistant: part of the format, kept when duplicating        #
# --------------------------------------------------------------------------- #
def test_duplicates_of_the_builtins_give_the_same_values(proj):
    """A copy of every built-in keeps its rules (0 when the opponent failed, empty without an
    Assistant), so it gives the same value and coverage as the original on every row."""
    for s in S.SCORES:
        S.duplicate("HI2027", None, s.name, f"copy_{s.name}")
    ss = S.resolve("HI2027")
    assert not ss.problems, ss.problems
    names = [f"copy_{s.name}" for s in S.SCORES]
    lst = ss.needed(names)
    for s in S.SCORES:
        c = ss.scores[f"copy_{s.name}"]
        assert (c.zero_if, c.needs_assistant, c.same_assistant) == (s.zero_if, s.needs_assistant, s.same_assistant), s.name
    assert ss.scores["copy_utility"].same_assistant == "skip"  # boards leave same-Assistant games out of utility
    rng = random.Random(11)
    rows = [_random_row(rng) for _ in range(400)]
    rows += [{"support_agent": "none", "opponent_advantage": 0.9, "opponent_failed": 1},  # the opponent failed
             {"support_agent": "A", "opponent_advantage": 0.7, "opponent_failed": 1, "ja_overall": 6},
             {"support_agent": "none", "ja_overall": 6, "human_advantage": 0.4, "irrational_accept": 0},  # no Assistant
             {"ja_overall": 5, "jh_engagement": 4, "human_advantage": 0.2},  # no support_agent at all
             {"support_agent": "A", "ja_overall": 6, "irrational_accept": 1, "opponent_failed": 0}]
    for row in rows:
        orig, copy = S.score_row(row), S.score_row(row, scores=lst)
        for s in S.SCORES:
            for suffix in ("", "_coverage"):
                a, b = orig[s.name + suffix], copy[f"copy_{s.name}" + suffix]
                if a is None:
                    assert b is None, (s.name + suffix, row)
                else:
                    assert b == pytest.approx(a, rel=1e-9, abs=1e-12), (s.name + suffix, row)
    # the copies' file entries say so; han_interaction has no rules, so its copy has none
    defs = yaml.safe_load((projects.project_dir("HI2027") / projects.PROJECT_FILE).read_text())["scores"]
    assert defs["copy_han_outcome"]["zero_if"] == ["opponent_failed"]
    assert defs["copy_hi_team"]["needs_assistant"] is True
    assert "zero_if" not in defs["copy_han_interaction"] and "needs_assistant" not in defs["copy_han_interaction"]


def test_zero_if_and_needs_assistant_in_definitions():
    ss = _resolve({"s": _defn(zero_if=["opponent_failed"], needs_assistant=True)})
    s = ss.scores["s"]
    assert not ss.problems and s.zero_if == ["opponent_failed"] and s.needs_assistant
    row = {"support_agent": "A", "human_advantage": 0.8, "ja_overall": 7, "n_offers": 0}
    assert S.compute(s, row)[0] > 0
    assert S.compute(s, {**row, "opponent_failed": 1}) == (0.0, 1.0)
    assert S.compute(s, {**row, "support_agent": "none"}) == (None, None)
    d = S.definition(s)
    assert d["zero_if"] == ["opponent_failed"] and d["needs_assistant"] is True
    # the defaults: no rules, and definition() says so
    d = S.definition(_resolve({"s": _defn()}).scores["s"])
    assert d["zero_if"] == [] and d["needs_assistant"] is False
    # checked: a list of known criteria, and a true/false
    for bad, msg in (({"zero_if": "opponent_failed"}, "zero_if must be a list"),
                     ({"zero_if": [1]}, "zero_if must be a list"),
                     ({"zero_if": ["nope"]}, "zero_if 'nope': unknown criterion"),
                     ({"needs_assistant": "yes"}, "needs_assistant must be true or false")):
        ss = _resolve({"s": _defn(**bad)})
        assert "s" not in ss.scores and any(msg in p for p in ss.problems), (bad, ss.problems)


def test_zero_if_and_needs_assistant_through_cli_and_api(client, proj):
    from typer.testing import CliRunner

    from hani2 import cli

    run = CliRunner().invoke
    r = run(cli.app, ["scores", "set", "HI2027", "safe", "--json",
                      '{"components": [{"criterion": "human_advantage", "weight": 1}], '
                      '"zero_if": ["opponent_failed"], "needs_assistant": true}'])
    assert r.exit_code == 0, r.output
    r = run(cli.app, ["scores", "show", "HI2027", "safe"])
    assert "rules: 0 when opponent_failed is 1; empty without an Assistant" in r.output
    assert "  zero_if:\n  - opponent_failed" in r.output and "needs_assistant: true" in r.output
    r = run(cli.app, ["scores", "duplicate", "HI2027", "han_outcome", "my_han_outcome"])
    assert r.exit_code == 0, r.output
    assert "rules: 0 when opponent_failed is 1" in run(cli.app, ["scores", "show", "HI2027", "my_han_outcome"]).output
    assert client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
    r = client.put("/api/admin/projects/HI2027/scores/team2",
                   json={"components": [{"criterion": "human_advantage", "weight": 1}], "needs_assistant": True})
    assert r.status_code == 200, r.text
    by = {s["key"]: s for s in r.json()["scores"]}
    assert by["team2"]["needs_assistant"] is True and by["team2"]["zero_if"] == []
    assert by["safe"]["zero_if"] == ["opponent_failed"]
    r = client.post("/api/admin/projects/HI2027/scores/my_hi/duplicate", json={"from": "hi_interaction"})
    assert r.status_code == 200, r.text
    assert {s["key"]: s for s in r.json()["scores"]}["my_hi"]["needs_assistant"] is True
    r = client.put("/api/admin/projects/HI2027/scores/bad", json={"components": [{"criterion": "human_advantage", "weight": 1}],
                                                                  "needs_assistant": "maybe"})
    assert r.status_code == 400 and "needs_assistant" in r.json()["detail"]
