"""Offline tests for nuc/survivor_impact.py (round 502, NUC-integration E).

No network, no ssh, no engine. Everything here runs on synthetic fixtures
except the four `TestThisTree` cases, which read committed artefacts.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import survivor_impact as si  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUBJECT = ROOT / "nuc" / "perturbation.py"
LEDGER = ROOT / "state" / "swe" / "perturbation-mutation-ledger.jsonl"


def latest_report():
    """The NEWEST `state/nuc/round-<NNN>/survivor-impact.json`, by round.

    ROUND 514. This was pinned at `round-502` and the pin is why
    `test_the_committed_report_is_about_the_subject_at_head` stayed red for
    six rounds: round 508 moved the subject, a report at HEAD could only be
    written under a NEW round directory, and the test would have gone on
    reading round 502's no matter how many fresh ones were committed.
    Resolving the newest keeps the gate's teeth -- the newest report still
    has to be about the subject at HEAD -- while letting the fix be a new
    artefact rather than an overwrite of a past round's record.
    """
    cands = sorted(
        (int(p.parent.name.split("-")[-1]), p)
        for p in (ROOT / "state" / "nuc").glob("round-*/survivor-impact.json")
        if p.parent.name.split("-")[-1].isdigit())
    return cands[-1][1] if cands else ROOT / "state" / "nuc" / "none.json"


REPORT = latest_report()


def _row(mid, status="survived", line=1, digest="d0", **kw):
    r = {"id": mid, "status": status, "line": line, "op": "cmp",
         "description": "x", "subject_digest": digest}
    r.update(kw)
    return r


def _ledger(tmp_path, rows):
    p = tmp_path / "ledger.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return str(p)


# ------------------------------------------------------------------ ledger

def test_a_rescore_supersedes_the_earlier_row_because_last_wins(tmp_path):
    """The whole reason round 502 exists as a round. `nodecampaign` APPENDS a
    re-score rather than editing, and `load_ledger` keeps the last row for a
    key -- so any reader that takes the first, or counts rows, reports a
    verdict the campaign itself no longer holds."""
    led = _ledger(tmp_path, [_row("m1", "survived"), _row("m1", "killed")])
    assert si.survivors(led) == []


def test_a_rescore_can_also_go_the_other_way(tmp_path):
    led = _ledger(tmp_path, [_row("m1", "killed"), _row("m1", "survived")])
    assert [r["id"] for r in si.survivors(led)] == ["m1"]


def test_survivors_at_another_subject_digest_are_not_this_subjects(tmp_path):
    """A mutant id is `basename:line:op#i` and `i` is POSITIONAL, so the same
    id against a moved source is a different mutant."""
    led = _ledger(tmp_path, [_row("m1", digest="d0"), _row("m2", digest="d9")])
    assert [r["id"] for r in si.survivors(led, subject_digest="d0")] == ["m1"]
    assert len(si.survivors(led)) == 2


def test_survivors_are_ordered_by_line_then_id(tmp_path):
    led = _ledger(tmp_path, [_row("b", line=9), _row("a", line=2),
                             _row("c", line=2)])
    assert [r["id"] for r in si.survivors(led)] == ["a", "c", "b"]


def test_a_missing_ledger_raises_rather_than_returning_nothing(tmp_path):
    """Returning `[]` would make `--strict` pass on a path that does not
    exist -- round 490's defect, in the module that cites it."""
    with pytest.raises(si.ImpactError):
        si.survivors(str(tmp_path / "nope.jsonl"))


def test_blank_lines_in_the_ledger_are_skipped(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text(json.dumps(_row("m1")) + "\n\n\n")
    assert [r["id"] for r in si.survivors(str(p))] == ["m1"]


# --------------------------------------------------------------- structure

SRC = textwrap.dedent('''
    import os

    def alpha():
        return 1

    def beta():
        return alpha() + os.getpid()

    @staticmethod
    def gamma():
        x = 1
        return x

    class C:
        def method(self):
            return 2
''')


def test_owner_of_returns_the_innermost_def():
    defs = si.enclosing_defs(SRC)
    names = {si.owner_of(defs, n) for n in range(1, len(SRC.splitlines()) + 1)}
    assert "C.method" in names
    assert "C" in names
    assert "alpha" in names
    # NOT `.index("            return 2")` -- round 502 wrote the literal with
    # the indentation it has in THIS file, and `textwrap.dedent` strips the
    # common four-space prefix off SRC before `ast` ever sees it. Anchor on the
    # stripped line instead, so the fixture can be re-indented without the
    # assertion silently becoming a ValueError. (Round 503, inheriting.)
    body = next(i + 1 for i, ln in enumerate(SRC.splitlines())
                if ln.strip() == "return 2")
    assert si.owner_of(defs, body) == "C.method"   # not "C"


def test_a_decorator_line_belongs_to_the_function_it_decorates():
    """`@dataclass(frozen=True)` is a mutation site one line ABOVE the `def`,
    and two of this subject's survivors are exactly that. If the decorator
    were attributed to module level the reason field would be wrong."""
    defs = si.enclosing_defs(SRC)
    deco = SRC.splitlines().index("@staticmethod") + 1
    assert si.owner_of(defs, deco) == "gamma"
    lo, hi = si.span_of(defs, deco)
    assert lo == deco


def test_span_of_is_none_at_module_level():
    assert si.span_of(si.enclosing_defs(SRC), 2) is None
    assert si.owner_of(si.enclosing_defs(SRC), 2) is None


def test_called_names_finds_plain_and_attribute_calls():
    names = si.called_names(SRC)
    assert "alpha" in names       # beta() calls it
    assert "getpid" in names      # os.getpid()


def test_a_function_nothing_calls_is_absent_from_called_names():
    """The `orphan_function` verdict rests entirely on this."""
    assert "beta" not in si.called_names(SRC)
    assert "gamma" not in si.called_names(SRC)


def test_called_names_errs_toward_LIVE_and_that_direction_is_deliberate():
    """Name-based, not scope-aware: a same-named call anywhere makes this
    module say the function is live. A false positive can only ever SUPPRESS
    an `orphan_function` verdict, never manufacture one."""
    src = "def beta():\n    return 1\n\nclass Other:\n    def f(self, o):\n        return o.beta()\n"
    assert "beta" in si.called_names(src)


# ---------------------------------------------------------------- diffing

def _out(rc=0, stdout="a\nb\n"):
    import hashlib
    return {"rc": rc, "stdout": stdout, "stdout_bytes": len(stdout),
            "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
            "stderr_tail": []}


def test_identical_outputs_diff_to_nothing():
    base = {n: _out() for n, _ in si.BATTERY}
    assert si.battery_diff(base, dict(base)) == []


def test_a_returncode_change_is_reported_before_stdout_is_compared():
    base = {n: _out() for n, _ in si.BATTERY}
    other = dict(base)
    first = si.BATTERY[0][0]
    other[first] = _out(rc=1, stdout="totally different\n")
    d = si.battery_diff(base, other)
    assert len(d) == 1 and d[0]["kind"] == "returncode"
    assert d[0]["before"] == 0 and d[0]["after"] == 1


def test_a_stdout_change_names_the_first_differing_line():
    """A diff that only says "something moved" is what let round 502's first
    run report 32 of 32 as findings. The witness is the fix."""
    base = {n: _out() for n, _ in si.BATTERY}
    other = dict(base)
    first = si.BATTERY[0][0]
    other[first] = _out(stdout="a\nCHANGED\n")
    d = si.battery_diff(base, other)
    assert d[0]["kind"] == "stdout"
    assert d[0]["first_diff"] == {"line_no": 2, "before": "b", "after": "CHANGED"}


def test_a_shorter_stdout_diffs_against_eof_rather_than_indexing_off_the_end():
    base = {n: _out() for n, _ in si.BATTERY}
    other = dict(base)
    first = si.BATTERY[0][0]
    other[first] = _out(stdout="a\n")
    d = si.battery_diff(base, other)
    assert d[0]["first_diff"]["after"] == "<eof>"


def test_a_battery_entry_missing_from_one_side_is_reported_not_ignored():
    base = {n: _out() for n, _ in si.BATTERY}
    other = dict(base)
    other.pop(si.BATTERY[0][0])
    d = si.battery_diff(base, other)
    assert d[0]["kind"] == "missing"


# ---------------------------------------------------------------- sandbox

def _mini_project(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    (d / "sib.py").write_text("VALUE = 7\n")
    (d / "subj.py").write_text(
        "import sib\nimport sys\nprint(sib.VALUE)\nsys.exit(0)\n")
    return d


def test_the_sandbox_keeps_sibling_modules_importable(tmp_path):
    """THE REGRESSION, as a test. `nuc/perturbation.py` imports
    `swap_analysis`; round 502's first run put the mutant alone in a temp
    directory, every battery entry died with `ModuleNotFoundError`, and the
    output-digest oracle read that as "the published number moved" for all 32
    survivors."""
    proj = _mini_project(tmp_path)
    box = tmp_path / "box"
    box.mkdir()
    dst = si.make_sandbox(str(proj / "subj.py"), str(box))
    (box / "subj.py").write_text((proj / "subj.py").read_text())
    p = subprocess.run([sys.executable, dst], capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout.strip() == "7"


def test_without_the_sandbox_the_same_module_dies_on_the_import(tmp_path):
    """The control for the control: the failure mode is real, not imagined."""
    proj = _mini_project(tmp_path)
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "subj.py").write_text((proj / "subj.py").read_text())
    p = subprocess.run([sys.executable, str(bare / "subj.py")],
                       capture_output=True, text=True)
    assert p.returncode != 0 and "ModuleNotFoundError" in p.stderr


def test_the_sandbox_does_not_link_the_subject_itself(tmp_path):
    """If it did, writing the mutant would write THROUGH the symlink into the
    real tree -- round 497's `_write_mutant` finding, in a new place."""
    proj = _mini_project(tmp_path)
    box = tmp_path / "box"
    box.mkdir()
    si.make_sandbox(str(proj / "subj.py"), str(box))
    assert not (box / "subj.py").exists()
    assert (box / "sib.py").is_symlink()
    (box / "subj.py").write_text("print('mutant')\n")
    assert "import sib" in (proj / "subj.py").read_text()


def test_the_sandbox_skips_pycache(tmp_path):
    proj = _mini_project(tmp_path)
    (proj / "__pycache__").mkdir()
    box = tmp_path / "box"
    box.mkdir()
    si.make_sandbox(str(proj / "subj.py"), str(box))
    assert not (box / "__pycache__").exists()


# ----------------------------------------------------------------- strict

def _rep(**kw):
    r = {"n_survivors_standing": 3, "n_lines_executed_by_battery": 100,
         "control_identity_clean": True, "moves_published_number": []}
    r.update(kw)
    return r


def test_strict_passes_only_when_every_condition_holds():
    assert si.strict_fails(_rep()) == []


def test_strict_fails_when_nothing_was_audited():
    """Round 490's rule, stated in this module's own docstring: a gate that
    passes on an input it never read is worse than one that fails."""
    assert si.strict_fails(_rep(n_survivors_standing=0))


def test_strict_fails_when_the_battery_executed_no_line_of_the_subject():
    assert si.strict_fails(_rep(n_lines_executed_by_battery=0))


def test_strict_fails_when_the_identity_control_did_not_reproduce():
    bad = si.strict_fails(_rep(control_identity_clean=False))
    assert any("control" in b for b in bad)


def test_strict_fails_when_a_survivor_moves_a_published_number():
    bad = si.strict_fails(_rep(moves_published_number=["x:1:cmp#1"]))
    assert any("x:1:cmp#1" in b for b in bad)


def test_a_report_with_no_control_field_at_all_fails_strict():
    r = _rep()
    r.pop("control_identity_clean")
    assert any("control" in b for b in si.strict_fails(r))


def test_tally_ignores_none_and_sorts():
    assert si._tally(["b", "a", None, "a"]) == {"a": 2, "b": 1}


# --------------------------------------------------------------- tracing

def test_settrace_resolves_individual_lines_of_a_multi_line_expression():
    """The measurement the whole `unreached_by_battery` verdict rests on.
    Twelve of this subject's survivors live in ONE four-line f-string, and a
    statement-granular tracer would call all four executed whichever branch
    ran. Pinned against `power_floor`, whose `why` has two branches:
    `testable` non-empty takes 1657-1659, empty takes 1655.

    ROUND 508: these are LINE PINS in a subject that other rounds edit, and
    they moved by +4 when round 508 rewrote the `CHANNEL_MIN_BYTES` refusal
    message 236 lines above them. That is the pin doing its job -- a tracer
    test that silently kept passing against different lines would be worse --
    but a round that shifts `perturbation.py` must expect to re-pin here."""
    sys.path.insert(0, str(ROOT / "nuc"))
    import perturbation as pt
    target = str(SUBJECT)
    for args, want_in, want_out in (((1145, 31, 16), 1658, 1655),
                                    ((218, 1, 16), 1655, 1658)):
        seen = set()

        def tr(frame, event, arg):
            if frame.f_code.co_filename != target:
                return None
            if event == "line":
                seen.add(frame.f_lineno)
            return tr

        sys.settrace(tr)
        try:
            pt.power_floor(*args)
        finally:
            sys.settrace(None)
        assert want_in in seen
        assert want_out not in seen


# ------------------------------------------------------------- this tree

class TestThisTree:
    """Reads committed artefacts. These go red when the tree moves, which is
    the point."""

    def _rep(self):
        if not REPORT.exists():
            pytest.skip("round 502's report has not been built")
        return json.loads(REPORT.read_text())

    def test_the_committed_report_is_about_the_subject_at_head(self):
        import hashlib
        rep = self._rep()
        assert rep["subject_digest"] == hashlib.sha256(
            SUBJECT.read_bytes()).hexdigest()

    def test_the_committed_report_passed_its_own_identity_control(self):
        assert self._rep()["control_identity_clean"] is True

    def test_every_moving_verdict_carries_a_witness(self):
        """A `moves_published_number` with no diff is the false headline round
        502's first run produced 32 times."""
        for r in self._rep()["results"]:
            if r["verdict"] == "moves_published_number":
                assert r["diffs"], r["id"]

    def test_every_unreached_verdict_carries_one_of_the_three_reasons(self):
        """ROUND 526 -- the rule now reads `raw_verdict`, and that is the
        whole point of the change rather than an accommodation of it.

        `reason` has always been a fact about what the BATTERY did: which of
        the three ways the line failed to execute. Round 526 lets a cited
        proof overwrite `verdict` with `provably_unreachable`, and if this
        gate went on keying off `verdict` it would demand `reason is None` for
        exactly the rows whose reason is most worth keeping. `raw_verdict`
        preserves the measurement under the upgrade; both are published.
        """
        for r in self._rep()["results"]:
            raw = r.get("raw_verdict", r["verdict"])
            if raw == "unreached_by_battery":
                assert r["reason"] in ("orphan_function", "branch_not_taken",
                                       "function_not_entered"), r["id"]
            else:
                assert r.get("reason") is None, r["id"]

    def test_the_committed_report_names_the_battery_THAT_EXISTS_NOW(self):
        """ROUND 514, and it would have been red the day round 508 landed.

        Round 508 rewrote `BATTERY` -- it put `reclaim` and `gap` in (both had
        been listed as unrunnable) and gave `wsweep_swap` the `--channel swap`
        it had never passed -- and did not regenerate the report. The digest
        gate caught the subject moving. NOTHING caught the INSTRUMENT moving,
        so the committed report went on advertising five verbs and a
        `battery_gap` naming two of the seven that now run.
        """
        rep = self._rep()
        assert rep["battery"] == [n for n, _ in si.BATTERY]
        assert rep["battery_gap"] == dict(si.BATTERY_GAP)

    def test_the_committed_report_agrees_with_the_ledger_it_READ(self):
        """ROUND 514's flattest finding. Round 502's report says
        `n_survivors_standing: 32`; the commit that landed it says in its own
        message "the ledger goes 55 killed / 32 survived -> 82 / 5", and the
        ledger in that same commit stands at 5. The report was stale against
        its own input BEFORE it was ever committed, for twelve rounds, and the
        four gates over it all passed because none of them re-read the ledger.

        `survivors()` is last-wins, so this is not a re-run: it is the same
        one-line question the report answered, asked again at HEAD.
        """
        rep = self._rep()
        standing = si.survivors(str(LEDGER),
                                subject_digest=rep["subject_digest"])
        assert rep["n_survivors_standing"] == len(standing)
        assert sorted(r["id"] for r in rep["results"]) == sorted(
            r["id"] for r in standing), "the report audits a different set"

    def test_classify_bucket_is_still_called_by_nothing_in_the_module(self):
        """The round's flattest finding, as a live gate. `classify_bucket` was
        added at round 394 and `git log -S 'classify_bucket('` returns that
        one commit: it has never had a caller inside `perturbation.py`. Eight
        of the 32 survivors sit in it, and `nodecampaign.R491_RANGES` names it
        as one of "the functions the published numbers run through". If this
        test goes GREEN-to-RED somebody wired it up, which is good news and
        means the range comment is finally true."""
        assert "classify_bucket" not in si.called_names(SUBJECT.read_text())


# --------------------------------------------------------------------------
# ROUND 526 (NUC-integration E) -- THE PROVEN REGISTRY.
#
# Every verdict this module produced before round 526 was a fact about the
# battery. `unreached_by_battery/branch_not_taken` is documented in the module
# docstring as "the only one of the three that is evidence about the box", and
# round 520 spent it on two mutants inside a branch that is arithmetically
# unreachable -- evidence about nothing but the shape of `best_case_p`.
#
# `PROVEN` is the fourth answer, and these tests are the fence around it: a
# registry that lets a survivor be graded "nothing can kill this" is exactly
# the place a future round would be tempted to file an inconvenient one.
# --------------------------------------------------------------------------

def test_every_proven_entry_is_well_formed():
    for mid, e in si.PROVEN.items():
        assert e["class"] in si.PROVEN_CLASSES, mid
        assert len(e["subject_digest"]) == 64, mid
        assert "::" in e["proof"], mid
        assert e["proof"].split("::")[0].endswith(".py"), mid
        assert len(e["why"]) > 60, mid


def test_every_proven_entry_cites_a_test_that_actually_exists():
    """A citation nobody can run is a comment. This COLLECTS the cited
    nodeids -- cheap, no execution -- so the registry cannot survive a rename
    of the test that proves it."""
    nodeids = sorted({e["proof"] for e in si.PROVEN.values()})
    pr = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider", *nodeids],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert pr.returncode == 0, pr.stdout[-2000:] + pr.stderr[-2000:]
    for nid in nodeids:
        assert nid.split("::")[-1] in pr.stdout, nid


def test_proof_for_governs_only_at_the_digest_it_was_proved_at():
    """Round 520's finding about stale ledger rows, applied to this registry.
    A mutant id is generated by walking a specific file; at another digest the
    same id names a different line, or nothing at all."""
    mid, e = next(iter(si.PROVEN.items()))
    entry, status = si.proof_for(mid, e["subject_digest"])
    assert status == "at_this_digest" and entry is e
    entry, status = si.proof_for(mid, "0" * 64)
    assert status == "at_another_digest" and entry is e
    assert si.proof_for("perturbation.py:1:cmp#999999", e["subject_digest"]) \
        == (None, None)


def test_strict_fails_when_a_proven_mutant_turns_out_to_be_killable():
    """The measurement beats the registry. If the battery kills a mutant the
    registry calls unkillable, the entry is FALSE and must not be quietly
    downgraded to a passing report."""
    bad = si.strict_fails(_rep(proven_registry={
        "contradicted": ["perturbation.py:1660:const#1547"],
        "ids_at_another_digest": [], "unused_at_this_digest": []}))
    assert len(bad) == 1
    assert "KILLED it" in bad[0]


def test_strict_fails_on_an_entry_proved_at_another_digest():
    bad = si.strict_fails(_rep(proven_registry={
        "contradicted": [], "unused_at_this_digest": [],
        "ids_at_another_digest": ["perturbation.py:1586:cmp#162"]}))
    assert len(bad) == 1 and "different subject digest" in bad[0]


def test_strict_fails_on_a_registry_entry_that_grades_nobody():
    """Only when the FULL population was audited -- with `--only`, an unused
    entry is the flag doing its job, not a defect."""
    reg = {"contradicted": [], "ids_at_another_digest": [],
           "unused_at_this_digest": ["perturbation.py:1586:cmp#162"]}
    assert si.strict_fails(_rep(proven_registry=reg,
                                audited_full_population=True))
    assert si.strict_fails(_rep(proven_registry=reg,
                                audited_full_population=False)) == []


def test_strict_fails_when_the_cited_proofs_did_not_pass():
    assert si.strict_fails(_rep(proof_verification={"ok": True})) == []
    bad = si.strict_fails(_rep(proof_verification={
        "ok": False, "returncode": 1, "tail": ["1 failed"]}))
    assert len(bad) == 1 and "cited tests did not pass" in bad[0]


def test_strict_is_silent_about_proofs_when_verification_was_not_asked_for():
    """`--verify-proofs` is opt-in and costs a pytest run; a report without it
    must not be graded as if the proofs had failed."""
    assert si.strict_fails(_rep()) == []


def test_verify_proofs_runs_the_real_citations_and_they_pass():
    d = next(iter(si.PROVEN.values()))["subject_digest"]
    out = si.verify_proofs(str(ROOT), digest=d, timeout_s=600)
    assert out["ok"] is True, out
    assert out["n_entries_checked"] == len(si.PROVEN)
    assert out["skipped_at_another_digest"] == []


def test_verify_proofs_refuses_to_pass_when_it_ran_nothing():
    """Round 490's rule: a gate that passes on an input it never read is
    worse than one that fails."""
    out = si.verify_proofs(str(ROOT), digest="0" * 64)
    assert out["ok"] is False
    assert out["nodeids"] == []
    assert sorted(out["skipped_at_another_digest"]) == sorted(si.PROVEN)


class TestThisTreeProven:
    """The committed report, read against the registry that produced it."""

    def _rep(self):
        if not REPORT.exists():
            pytest.skip("no survivor-impact report has been built")
        return json.loads(REPORT.read_text())

    def test_the_headline_number_is_decomposed_and_the_parts_add_up(self):
        """`n_survivors_standing` pooled two populations: survivors a test
        could still kill, and survivors no test will ever kill. Round 526's
        two new tests moved 2 of the 5 out of the first population by killing
        them; the other 3 were never in it."""
        rep = self._rep()
        assert (rep["n_survivors_provably_dead"]
                + rep["n_survivors_unexplained"]) == rep["n_survivors_standing"]

    def test_every_proven_row_kept_the_measurement_it_was_upgraded_over(self):
        for r in self._rep()["results"]:
            if r.get("proven"):
                assert r["verdict"] == r["proven"]
                assert r["raw_verdict"] in ("reached_but_identical",
                                            "unreached_by_battery"), r["id"]
                assert r["proof"] and "::" in r["proof"], r["id"]
                assert r["proof_status"] == "at_this_digest", r["id"]

    def test_no_row_is_graded_proven_without_a_registry_entry(self):
        """The negative control: the upgrade is driven by the registry, not by
        the verdict text."""
        for r in self._rep()["results"]:
            if r.get("proven") is None:
                assert r["verdict"] == r.get("raw_verdict", r["verdict"])
            else:
                assert r["id"] in si.PROVEN, r["id"]

    def test_the_committed_report_ran_its_proofs(self):
        rep = self._rep()
        pv = rep.get("proof_verification")
        assert pv is not None, "regenerate with --verify-proofs"
        assert pv["ok"] is True and pv["returncode"] == 0
