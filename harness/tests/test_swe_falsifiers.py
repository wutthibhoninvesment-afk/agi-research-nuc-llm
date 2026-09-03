"""`swe.falsifiers` — the per-TEST falsification audit.

Round 473 (SWE-loop D). Subject: round 472's next-step 1, *"mutation-test the
falsifiers … three tests that could not have gone red for ANY code change"*.
`swe.mutation` scores the CODE; this module scores the TESTS, by giving every
MUTANT run its own `--junitxml` and attributing each kill to the nodes that
actually went red.

Three halves, for the reason `test_swe_sandbox_evidence.py` states:

* pure-function pins (`function_ranges`, `main_guard_spans`, `select_sites`,
  `pytest_cmd`) — no subprocess, milliseconds;
* a TOY-PROJECT half whose test file contains one deliberately vacuous test,
  so the end-to-end pipeline is pinned against a known answer;
* a REAL-SUBJECT half over this repo's own modules and over the campaign
  reports round 473 banked, so neither the `__main__`-guard rule nor the
  reports can rot into something that parses and says nothing.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, REPO_ROOT)

from swe import falsifiers as F                                   # noqa: E402
from swe.mutation import BaselineNotGreen, generate               # noqa: E402

ROUND_473 = os.path.join(REPO_ROOT, "state", "swe", "round-473")

MOD_SRC = textwrap.dedent('''
    """A toy subject with exactly two behaviours worth asserting."""


    def classify(n):
        if n > 10:
            return "big"
        return "small"


    def total(xs):
        return sum(xs) + 1


    if __name__ == "__main__":
        print(classify(3))
''')

TEST_SRC = textwrap.dedent('''
    import mod


    def test_classify_has_a_boundary_at_ten():
        assert mod.classify(11) == "big"
        assert mod.classify(10) == "small"


    def test_total_carries_the_offset():
        assert mod.total([1, 2]) == 4


    def test_the_module_can_be_imported():
        """Vacuous ON PURPOSE: no mutant of mod.py can make this red."""
        assert mod is not None
''')


def _toy(tmp_path, mod_src=MOD_SRC, test_src=TEST_SRC):
    """A minimal project: `mod.py`, a root conftest so `import mod` resolves,
    and `tests/test_mod.py`. Returns the project root."""
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "mod.py").write_text(mod_src, encoding="utf-8")
    # An EMPTY root conftest is what puts the project root on sys.path under
    # pytest's `prepend` import mode; without it `import mod` fails and every
    # mutant below would be a collection error rather than a verdict.
    (root / "conftest.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_mod.py").write_text(test_src, encoding="utf-8")
    return str(root)


# --------------------------------------------------------------------------
# pure functions
# --------------------------------------------------------------------------

def test_function_ranges_uses_dotted_names_for_methods_and_nested_defs():
    src = textwrap.dedent('''
        class C:
            def m(self):
                def inner():
                    pass
                return inner


        def free():
            pass
    ''')
    r = F.function_ranges(src)
    assert set(r) == {"C", "C.m", "C.m.inner", "free"}
    assert r["C"][0] < r["C.m"][0] < r["C.m.inner"][0]


def test_a_decorated_function_starts_at_its_decorator():
    src = "import functools\n\n@functools.cache\ndef f():\n    return 1\n"
    lo, hi = F.function_ranges(src)["f"]
    assert lo == 3 and hi == 5


def test_main_guard_spans_finds_the_guard_and_nothing_that_merely_resembles_it():
    src = textwrap.dedent('''
        name = "x"
        if name == "__main__":
            pass
        if __name__ == "__notmain__":
            pass
        if __name__ == "__main__":
            run()
            run()
    ''')
    assert F.main_guard_spans(src) == [(7, 9)]


def test_a_module_with_no_guard_has_no_spans():
    assert F.main_guard_spans("x = 1\n") == []


def test_the_main_guard_is_excluded_by_default_and_counted_not_dropped_silently():
    mutants = generate(MOD_SRC, "mod.py")
    spans = F.main_guard_spans(MOD_SRC)
    kept, sel = F.select_sites(mutants, guard_spans=[("mod.py", spans)])
    assert sel["generated"] == len(mutants)
    # THREE, not two: the `ifneg` on the `If`, the `cmp` (Eq -> NotEq) on the
    # comparison, and the `const` on the `3` in `print(classify(3))`. The
    # exclusion is over the guard's whole SPAN, body included — a mutant of
    # the body is no more evidence about the suite than a mutant of the test.
    excluded = [m for m in mutants if m not in kept]
    assert sorted(m.op for m in excluded) == ["cmp", "const", "ifneg"]
    assert sel["main_guard_excluded"] == 3
    assert len(kept) == len(mutants) - 3
    assert not any(spans[0][0] <= m.lineno <= spans[0][1] for m in kept)


def test_a_guard_span_only_filters_its_own_file():
    mutants = generate(MOD_SRC, "mod.py")
    _, sel = F.select_sites(mutants, guard_spans=[("other.py",
                                                   F.main_guard_spans(MOD_SRC))])
    assert sel["main_guard_excluded"] == 0


def test_funcs_scopes_the_campaign_and_an_unknown_name_is_an_error():
    mutants = generate(MOD_SRC, "mod.py")
    ranges = F.function_ranges(MOD_SRC)
    kept, sel = F.select_sites(mutants, funcs=["total"], ranges=ranges)
    assert kept and all(ranges["total"][0] <= m.lineno <= ranges["total"][1]
                        for m in kept)
    assert sel["funcs"] == ["total"]
    with pytest.raises(KeyError):
        F.select_sites(mutants, funcs=["no_such_function"], ranges=ranges)


def test_sample_is_evenly_spaced_and_limit_is_head_biased_and_says_so():
    mutants = generate(MOD_SRC, "mod.py")
    assert len(mutants) >= 8, "toy subject got too small to distinguish these"
    sampled, s_sel = F.select_sites(mutants, sample=4)
    limited, l_sel = F.select_sites(mutants, limit=4)
    assert s_sel["head_biased"] is False and l_sel["head_biased"] is True
    assert limited == mutants[:4]
    # The whole point: a sample reaches the LAST site, a head-limit cannot.
    assert sampled[-1] is mutants[-1]
    assert sampled[0] is mutants[0]


def test_sample_of_one_does_not_divide_by_zero():
    mutants = generate(MOD_SRC, "mod.py")
    kept, _ = F.select_sites(mutants, sample=1)
    assert len(kept) == 1


def test_a_sample_larger_than_the_site_list_is_the_whole_list():
    mutants = generate(MOD_SRC, "mod.py")
    kept, _ = F.select_sites(mutants, sample=len(mutants) + 50)
    assert kept == mutants


def test_the_runner_carries_junitxml_and_never_dash_x():
    cmd = F.pytest_cmd(["tests/test_mod.py"], "/tmp/r.xml")
    assert any(c.startswith("--junitxml=") for c in cmd)
    # Under `-x` the report names ONE red node per mutant and attribution
    # becomes a measurement of collection order. This pin is the reason
    # `mutation.DEFAULT_TEST_CMD` could not simply be reused.
    assert "-x" not in cmd
    assert "--exitfirst" not in cmd


# --------------------------------------------------------------------------
# report arithmetic, with no subprocess
# --------------------------------------------------------------------------

class _M(object):
    def __init__(self, mid, status):
        self.id, self.status = mid, status
        self.path, self.lineno, self.end_lineno = "mod.py", 1, 1
        self.op, self.description, self.seconds, self.detail = "cmp", "d", 0.0, ""

    def as_dict(self):
        return {"id": self.id, "status": self.status}


def _report(attrs, passed=("a", "b", "c"), skipped=(), n_nodes=None):
    statuses = {k: "passed" for k in passed}
    statuses.update({k: "skipped" for k in skipped})
    base = F.Baseline(0, False, 1.0, statuses, {"verdict": "ok"}, "")
    return F.FalsifierReport("u", ["mod.py"], ["tests/test_mod.py"], base,
                             attrs, {"generated": len(attrs)}, 1.0)


def test_kills_carries_a_zero_for_every_baseline_node_no_red_set_mentions():
    rep = _report([F.Attribution(_M("m1", "killed"), {"a"}, True, 3)])
    assert rep.kills["a"] == 1
    assert rep.kills["b"] == 0 and rep.kills["c"] == 0
    assert rep.never_red == ["b", "c"]


def test_a_node_skipped_at_baseline_is_not_accused_of_being_unfalsifiable():
    rep = _report([F.Attribution(_M("m1", "killed"), {"a"}, True, 4)],
                  passed=("a", "b"), skipped=("s",))
    assert "s" not in rep.never_red
    assert rep.baseline.skipped == ["s"]


def test_an_unattributed_kill_makes_the_campaign_unsound():
    rep = _report([F.Attribution(_M("m1", "killed"), {"a"}, True, 3),
                   F.Attribution(_M("m2", "timeout"), set(), False, 0)])
    assert [a.mutant.id for a in rep.unattributed_kills] == ["m2"]
    assert rep.attribution_coverage == 0.5
    assert rep.sound is False
    assert rep.verdict == F.V_UNSOUND


def test_an_errored_mutant_makes_the_campaign_unsound():
    rep = _report([F.Attribution(_M("m1", "killed"), {"a"}, True, 3),
                   F.Attribution(_M("m2", "error"), set(), True, 3)])
    assert rep.sound is False and rep.verdict == F.V_UNSOUND


def test_a_mutant_that_collected_fewer_nodes_than_the_baseline_is_node_loss():
    rep = _report([F.Attribution(_M("m1", "killed"), {"a"}, True, 3),
                   F.Attribution(_M("m2", "survived"), set(), True, 2)])
    assert [a.mutant.id for a in rep.node_loss] == ["m2"]
    assert rep.sound is False and rep.verdict == F.V_UNSOUND


def test_an_errored_run_is_not_also_counted_as_node_loss():
    """It is already counted once, and a run that produced NO evidence is
    not a run that produced SOME and lost the rest."""
    rep = _report([F.Attribution(_M("m1", "error"), set(), True, 0)])
    assert rep.node_loss == []
    assert [a.mutant.id for a in rep.errored] == ["m1"]


def test_a_sound_campaign_with_every_node_red_at_least_once_is_all_falsifiable():
    rep = _report([F.Attribution(_M("m1", "killed"), {"a", "b"}, True, 3),
                   F.Attribution(_M("m2", "killed"), {"c"}, True, 3)])
    assert rep.sound is True
    assert rep.never_red == []
    assert rep.verdict == F.V_ALL_FALSIFIABLE


def test_a_campaign_that_killed_nothing_reports_no_kills_not_never_red():
    """Every node is trivially never-red when no mutant died; saying
    `never_red` there would accuse the tests of the engine's silence."""
    rep = _report([F.Attribution(_M("m1", "survived"), set(), True, 3)])
    assert rep.sound is True
    assert rep.verdict == F.V_NO_KILLS
    assert rep.attribution_coverage == 1.0


def test_the_summary_shouts_when_the_campaign_cannot_support_its_own_list():
    rep = _report([F.Attribution(_M("m1", "timeout"), set(), False, 0)])
    text = rep.summary()
    assert "NOT SOUND" in text and "UPPER BOUND" in text


def test_as_dict_is_json_serialisable_and_keeps_the_scope_of_the_claim():
    rep = _report([F.Attribution(_M("m1", "killed"), {"a"}, True, 3)])
    d = json.loads(json.dumps(rep.as_dict()))
    assert d["subject_paths"] == ["mod.py"] and d["test_paths"] == ["tests/test_mod.py"]
    assert d["never_red"] == ["b", "c"] and d["verdict"] == F.V_NEVER_RED


# --------------------------------------------------------------------------
# toy project, end to end
# --------------------------------------------------------------------------

@pytest.mark.swe_slow
def test_the_audit_finds_the_deliberately_vacuous_test_and_only_it(tmp_path):
    root = _toy(tmp_path)
    rep = F.audit(root, ["mod.py"], ["tests/test_mod.py"], unit="toy",
                  timeout_s=90.0)
    assert rep.baseline.green and len(rep.baseline.passed) == 3
    assert rep.killed, "no mutant died; the attribution cannot be exercised"
    never = [n.rsplit("::", 1)[-1] for n in rep.never_red]
    assert never == ["test_the_module_can_be_imported"]
    assert rep.verdict == F.V_NEVER_RED
    assert rep.selection["main_guard_excluded"] == 3


@pytest.mark.swe_slow
def test_a_red_suite_refuses_to_produce_a_campaign(tmp_path):
    root = _toy(tmp_path, test_src=TEST_SRC + "\n\ndef test_broken():\n"
                                              "    assert mod.total([]) == 99\n")
    with pytest.raises(BaselineNotGreen):
        F.audit(root, ["mod.py"], ["tests/test_mod.py"], timeout_s=90.0)


@pytest.mark.swe_slow
def test_the_cli_exit_code_says_which_of_the_three_answers_it_gave(tmp_path):
    root = _toy(tmp_path)
    out = tmp_path / "r.json"
    rc = subprocess.call(
        [sys.executable, os.path.join(REPO_ROOT, "harness", "swe", "falsifiers.py"),
         "audit", "--root", root, "--subject", "mod.py",
         "--tests", "tests/test_mod.py", "--quiet", "--timeout-s", "90",
         "--json", str(out)],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert rc == 1, "a never-red node must exit 1, not 0"
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["sound"] is True
    assert [n.rsplit("::", 1)[-1] for n in d["never_red"]] == \
        ["test_the_module_can_be_imported"]


def test_the_functions_subcommand_lists_ranges_and_site_counts():
    out = subprocess.check_output(
        [sys.executable, os.path.join(REPO_ROOT, "harness", "swe", "falsifiers.py"),
         "functions", "harness/swe/scoreaudit.py"], cwd=REPO_ROOT, text=True)
    assert "classify_recorded" in out and "site(s)" in out


# --------------------------------------------------------------------------
# real subject
# --------------------------------------------------------------------------

def test_this_repo_really_does_pay_the_main_guard_tax_on_its_own_modules():
    """Not a hypothesis: `harness/swe/scoreaudit.py` offers exactly two
    mutation sites inside its `__main__` guard, and both make the module run
    its own CLI at import time."""
    path = os.path.join(REPO_ROOT, "harness", "swe", "scoreaudit.py")
    src = open(path, encoding="utf-8").read()
    spans = F.main_guard_spans(src)
    assert len(spans) == 1
    inside = [m for m in generate(src, "harness/swe/scoreaudit.py")
              if spans[0][0] <= m.lineno <= spans[0][1]]
    assert sorted(m.op for m in inside) == ["cmp", "ifneg"]


def test_the_banked_campaign_reports_keep_never_red_inside_the_baseline():
    """The invariant every published `never_red` list rests on: a node
    accused of never going red must be one the baseline actually RAN."""
    paths = sorted(p for p in os.listdir(ROUND_473) if p.endswith(".json")) \
        if os.path.isdir(ROUND_473) else []
    assert paths, "round 473 banked no campaign report; the audit is unpinned"
    for name in paths:
        with open(os.path.join(ROUND_473, name), encoding="utf-8") as fh:
            d = json.load(fh)
        assert set(d["never_red"]) <= set(d["kills"]), name
        assert d["baseline"]["n_passed"] >= len(d["never_red"]), name
        assert d["killed"] + d["survived"] + d["errored"] == d["total"], name
        assert d["subject_paths"] and d["test_paths"], name
