"""Round 516 (language C): tests for `checkscope.py`.

The module answers two questions about a gate, and this file is organised
the same way:

  1-3.  `--scope`: which top-level keys of a ledger can its own `--check`
        SEE? Measured by mutation, so the tests here are mostly about the
        apparatus being trustworthy -- a no-op mutation and a broken
        redirect both read as "the gate is blind", and only a control can
        tell them apart.
  4.    `--selfref`: which assertions never leave the document at all?
        The positive control is round 512's own vacuous gate, rebuilt from
        its shape rather than quoted, so the test does not depend on git.
  5.    The three repairs this round made with the measurement in hand.
"""
import ast
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import checkscope as C                                          # noqa: E402
import corpusledger as CL                                       # noqa: E402


# ---------------------------------------------------------------------------
# 1. document_diff -- the predicate that is total in what drifts
# ---------------------------------------------------------------------------

def test_a_key_on_only_one_side_is_a_finding_in_both_directions():
    """The half a hand-written comparison forgets.

    `for k, v in live.items()` is blind to a key that exists only on disk,
    which is how a ledger keeps a field its generator stopped writing."""
    only_disk = C.document_diff({"a": 1, "gone": 2}, {"a": 1})
    only_tree = C.document_diff({"a": 1}, {"a": 1, "new": 2})
    assert [[k for k, _ in only_disk], [k for k, _ in only_tree]] == \
        [["gone"], ["new"]]
    assert "on disk but the tree would not write it" in only_disk[0][1]
    assert "absent from the ledger" in only_tree[0][1]


def test_the_summary_names_what_moved_inside_a_container():
    """Round 512's `_summarise` printed two lists and left the reader to
    diff them; a ledger key here holds 58 rows."""
    d = C.document_diff({"m": {"a": 1, "b": 2}}, {"m": {"a": 9, "c": 3}})
    assert len(d) == 1
    why = d[0][1]
    assert "1 only on disk (b)" in why
    assert "1 only in the tree (c)" in why
    assert "1 value(s) moved (a)" in why

    rows = C.document_diff({"r": [1, 2, 3]}, {"r": [1, 7, 3]})
    assert "1 of 3 row(s) differ, first at index 1" in rows[0][1]
    assert "3 row(s) on disk, 2 in the tree" in \
        C.document_diff({"r": [1, 2, 3]}, {"r": [1, 2]})[0][1]


def test_ignore_is_for_keys_another_finding_already_owns():
    assert C.document_diff({"a": 1, "b": 1}, {"a": 2, "b": 2},
                           ignore=("a",)) == \
        [("b", "ledger 1, tree 2")]


# ---------------------------------------------------------------------------
# 2. the mutations -- an apparatus that can lie
# ---------------------------------------------------------------------------

def test_a_corruption_prefers_a_member_that_is_not_already_empty():
    """THE FIRST THING THIS SWEEP GOT WRONG, kept as a test.

    The first draft dropped `sorted(v)[0]` from a mapping. On
    `builtin-liveness.json` the alphabetically first verdict class holds an
    EMPTY list, so the mutant was semantically identical to the control and
    `by_verdict` was reported BLIND under corruption by a gate that reads
    nothing else. A no-op mutation reads exactly like a blind gate."""
    mut, detail = C.mutate({"k": {"aaa": [], "bbb": [1]}}, "k", C.MUT_CORRUPT)
    assert list(mut["k"]) == ["aaa"]
    assert detail == "dropped member 'bbb'"


def test_a_mutation_that_would_be_a_no_op_is_reported_not_scored():
    mut, why = C.mutate({"k": {}}, "k", C.MUT_CORRUPT)
    assert (mut, why) == (None, "empty mapping -- nothing to drop")
    mut, why = C.mutate({"k": []}, "k", C.MUT_CORRUPT)
    assert (mut, why) == (None, "empty list -- nothing to drop")


def test_delete_and_corrupt_are_different_questions():
    obj = {"n": 3, "keep": 1}
    gone, _ = C.mutate(obj, "n", C.MUT_DELETE)
    bumped, detail = C.mutate(obj, "n", C.MUT_CORRUPT)
    assert [sorted(gone), bumped["n"], detail] == [["keep"], 4, "3 -> 4"]
    assert obj == {"n": 3, "keep": 1}, "mutate must not touch its input"


# ---------------------------------------------------------------------------
# 3. the sweep -- control first, or the row is void
# ---------------------------------------------------------------------------

def _gate_script(tmp_path, body):
    p = tmp_path / "gate.py"
    p.write_text("import json, sys\n"
                 "d = json.load(open(sys.argv[1]))\n" + body + "\n",
                 encoding="utf-8")
    return {"kind": "cli", "verb": "synthetic",
            "argv": ["python3", str(p), "<path>"]}


def _ledger(tmp_path, obj, name="synthetic.json"):
    d = tmp_path / "ledgers"
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return str(d)


def test_a_gate_sees_the_key_it_reads_and_is_blind_to_the_one_it_does_not(
        tmp_path):
    gate = _gate_script(tmp_path, "sys.exit(0 if d.get('watched') == 1 else 1)")
    ledgers = _ledger(tmp_path, {"watched": 1, "ignored": 1})
    row = C.scope_one("synthetic.json", gate, ledgers)
    got = dict((c["key"], c["seen"]) for c in row["keys"])
    assert [row["status"], got] == ["ok", {"watched": True, "ignored": False}]


def test_a_control_that_does_not_pass_voids_every_verdict_below_it(tmp_path):
    """DESIGN DECISION 2. A gate that fails on an UNMUTATED copy is not
    reading the copy -- and then every BLIND below it is the apparatus,
    not the gate."""
    gate = _gate_script(tmp_path, "sys.exit(1)")
    ledgers = _ledger(tmp_path, {"a": 1})
    row = C.scope_one("synthetic.json", gate, ledgers)
    assert [row["status"], row["keys"]] == [C.UNTESTABLE, []]
    assert "UNMUTATED copy" in row["why"]


def test_a_traceback_is_a_crash_and_not_a_sees(tmp_path):
    """A verb that raises on a malformed ledger HAS noticed something, and
    reporting that as SEES would credit it with a check it does not have.
    `subjprov.check_ledger` read `declared["totals"]` by subscript."""
    gate = _gate_script(tmp_path, "sys.exit(0 if d['need'] == 1 else 1)")
    ledgers = _ledger(tmp_path, {"need": 1})
    row = C.scope_one("synthetic.json", gate, ledgers)
    cell = row["keys"][0]
    assert [cell["verdicts"][C.MUT_DELETE], cell["verdicts"][C.MUT_CORRUPT]] \
        == [C.CRASH, C.SEES]
    assert cell["seen"] is True


def test_a_gate_that_reacts_to_the_encoding_is_confounded_not_total(tmp_path):
    """THE SECOND THING THIS SWEEP GOT WRONG, kept as a test.

    The first run wrote every mutant with `indent=2` and reported
    `testcorpus-contributions.json` as the one gate in this tree TOTAL over
    its own document. That gate contains a node byte-comparing the file
    against its generator's own encoding, so every re-serialised mutant
    failed it whichever key was touched, and every key scored SEES. A gate
    that appears to see everything because it is looking at the whitespace
    is this module's own subject arriving in its own apparatus."""
    d = tmp_path / "ledgers"
    d.mkdir()
    # Hand-formatted, so no `json.dumps` spelling reproduces it and the
    # mutants must fall back to this module's default encoding.
    (d / "synthetic.json").write_text('{"a": 1,\n     "b": 2}\n',
                                      encoding="utf-8")
    gate = _gate_script(
        tmp_path,
        "raw = open(sys.argv[1]).read()\n"
        "sys.exit(0 if raw == '{\"a\": 1,' + chr(10) + '     \"b\": 2}'"
        " + chr(10) else 1)")
    row = C.scope_one("synthetic.json", gate, str(d))
    assert row["status"] == C.CONFOUNDED
    assert "reacting to the file's encoding" in row["why"]
    assert [row["keys"], row["encoding"]["reproduces_the_file"]] == [[], False]


def test_the_mutant_is_written_in_the_ledgers_own_encoding(tmp_path):
    """...which is what makes the CONFOUNDED verdict above a real property
    of the gate rather than of this module's `json.dump` defaults."""
    p = tmp_path / "l.json"
    obj = {"b": 1, "a": {"z": 2}}
    p.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n",
                 encoding="utf-8")
    kw, tail, exact = C.detect_encoding(str(p), obj)
    assert [kw["indent"], kw["sort_keys"], tail, exact] == \
        [1, True, "\n", True]

    q = tmp_path / "round.json"
    C.write_as(obj, str(q), (kw, tail, exact))
    assert q.read_text(encoding="utf-8") == p.read_text(encoding="utf-8")


def test_an_encoding_that_cannot_be_reproduced_is_reported_not_assumed(
        tmp_path):
    p = tmp_path / "l.json"
    p.write_text('{"a":1}   \n\n', encoding="utf-8")
    _kw, _tail, exact = C.detect_encoding(str(p), {"a": 1})
    assert exact is False


def test_every_real_ledgers_encoding_is_reproducible():
    """All five, so a CONFOUNDED verdict on this tree is never the fallback
    encoding's fault."""
    bad = []
    for name in sorted(C.GATES):
        path = os.path.join(C.LEDGER_DIR, name)
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
        if not C.detect_encoding(path, obj)[2]:
            bad.append(name)
    assert bad == []


def test_every_generated_ledger_has_a_gate_and_no_gate_is_an_orphan():
    """DESIGN DECISION 1. `GATES` is the one hand-typed table in this
    round's work, so it is pinned against the table that is not: a ledger
    that appears in `corpusledger.registry()` and not here is a silent
    coverage hole, which is the defect the whole round is about."""
    ungated, orphan = C.gate_gaps()
    assert [ungated, orphan] == [[], []]


def test_the_report_carries_its_own_regeneration_command():
    rows = [{"ledger": "x", "status": "ok", "verb": "v",
             "keys": [{"key": "a", "seen": True, "total": True,
                       "partial": False, "prose": False,
                       "verdicts": {C.MUT_DELETE: C.SEES,
                                    C.MUT_CORRUPT: C.SEES}},
                      {"key": "b", "seen": False, "total": False,
                       "partial": False, "prose": False,
                       "verdicts": {C.MUT_DELETE: C.BLIND,
                                    C.MUT_CORRUPT: C.BLIND}}]}]
    rep = C.build_report(rows)
    assert rep["totals"] == {
        "keys": 2, "seen": 1, "seen_under_every_applicable_mutation": 1,
        "partial": 0, "blind": 1, "crash_only": 0}
    assert rep["_regenerate"].endswith("--scope --json <this file>")
    assert "sees 1/2 key(s), total over 1" in C.render_scope(rows)


# ---------------------------------------------------------------------------
# 4. --selfref -- the other way a gate is vacuous
# ---------------------------------------------------------------------------

ROUND_512_SHAPE = '''
import pytest
import assertshadow as A
import subjprov as S


@pytest.fixture(scope="module")
def live():
    rows, helpers = S.compare_with_census()
    return rows, helpers, S.guard_rows()


def test_every_census_pair_finds_its_assertion(live):
    rows, _helpers, _guards = live
    assert [len(rows), A.load_census()["totals"]["pairs"]] == [57, 57]


def test_a_pin_against_a_literal_is_not_vacuous():
    d = A.load_census()
    assert d["totals"]["pairs"] == 58


def test_one_live_operand_is_enough(live):
    _rows, _helpers, guards = live
    assert len(guards) == A.load_census()["totals"]["pairs"]
'''


def _tests_dir(tmp_path, source, name="test_shape.py"):
    d = tmp_path / "tests"
    d.mkdir(exist_ok=True)
    (d / name).write_text(source, encoding="utf-8")
    return str(d)


def test_the_positive_control_is_round_512s_own_vacuous_gate(tmp_path):
    """Rebuilt from its SHAPE, not quoted from git, so the control still
    works after the history scrolls away.

    Everything that makes it hard is in these four lines: the fixture
    returns a tuple mixing a JOIN, an opaque map and a genuinely LIVE
    scan; the test unpacks it; and `len(rows)` looks live and counts
    census pairs. Classify the join as live and this is missed."""
    found = C.selfref_asserts(_tests_dir(tmp_path, ROUND_512_SHAPE))
    assert [f["func"] for f in found] == \
        ["test_every_census_pair_finds_its_assertion"]
    assert found[0]["join"] is True
    ops = found[0]["operands"]
    assert len(ops) == 2
    assert any("load_census" in o and "(declared)" in o for o in ops)
    assert any(o.startswith("len(rows)") and "(join)" in o for o in ops)


def test_a_pin_against_a_literal_is_not_reported(tmp_path):
    """One declared expression against a constant is a PIN. The constant
    is external information a human typed; the assertion is not vacuous."""
    found = C.selfref_asserts(_tests_dir(tmp_path, ROUND_512_SHAPE))
    assert "test_a_pin_against_a_literal_is_not_vacuous" not in \
        [f["func"] for f in found]


def test_one_live_operand_is_enough_to_clear_an_assertion(tmp_path):
    found = C.selfref_asserts(_tests_dir(tmp_path, ROUND_512_SHAPE))
    assert "test_one_live_operand_is_enough" not in [f["func"] for f in found]


def test_a_fixture_is_classified_by_its_body_not_by_its_name(tmp_path):
    """A fixture called `live` is not evidence that it is live."""
    src = ("import pytest\nimport subjprov as S\n\n"
           "@pytest.fixture\ndef live():\n"
           "    rows, helpers = S.compare_with_census()\n"
           "    return rows, helpers, S.guard_rows()\n")
    import ast
    origins = C._fixture_origins(ast.parse(src))
    assert origins == {"live": [C.JOIN, C.JOIN, C.LIVE]}


def test_the_live_tree_reports_the_two_nodes_named_for_this_shape():
    """Content-pinned by NAME rather than by count: the two nodes this
    tree has are called `..._are_the_sums_of_its_own_rows`, they say in
    their own docstrings that they are internal identities, and they are
    legitimate. The analysis publishes rather than filters, so they are
    expected to appear -- and a THIRD name appearing is a round's work."""
    names = set("%s::%s" % (f["file"], f["func"])
                for f in C.selfref_asserts())
    assert "test_subjprov.py::test_the_ledger_totals_are_the_sums_of_its_" \
           "own_rows" in names
    assert "test_assertshadow.py::test_the_ledgers_totals_are_the_sums_of_" \
           "its_own_rows" in names


# ---------------------------------------------------------------------------
# 5. the three repairs
# ---------------------------------------------------------------------------

def test_both_builtin_ledgers_now_declare_their_own_regeneration():
    """Round 512's next-step #3. `corpusledger.UNDECLARED` is empty and the
    registry reads every command out of the artefact."""
    rows = dict((r["name"], r["source"]) for r in CL.registry())
    assert CL.UNDECLARED == {}
    assert [rows["builtin-liveness.json"], rows["builtin-runtime.json"]] == \
        ["self", "self"]


def test_the_declaration_survives_its_own_regeneration(tmp_path):
    """The refuted reason `corpusledger.UNDECLARED` used to carry.

    `ledger_view` is a pure function of the census, so the constant it
    emits comes back byte-for-byte -- and the ledger's own `check` does not
    trip over a key it does not know."""
    import builtinlive as BL
    p = str(tmp_path / "l.json")
    c = BL.census(programs=[{"origin": "example", "where": "a.lang",
                             "src": "print(1)"}])
    BL._write(p, BL.ledger_view(c))
    once = open(p, encoding="utf-8").read()
    BL._write(p, BL.ledger_view(c))
    again = json.load(open(p, encoding="utf-8"))
    assert open(p, encoding="utf-8").read() == once
    assert again["_regenerate"].endswith("--write --ledger <this file>")
    assert BL.check(c, p)[0] == []


def test_subjprov_check_now_sees_a_key_its_two_codes_do_not(tmp_path):
    """Round 512's next-step #4, as a falsification.

    `_helpers_ignoring_arguments` is one of the nine keys `S001`/`S002`
    never ranged over, and round 512 found this ledger stale in exactly
    that region while `--check` printed "0 finding(s)"."""
    import subjprov as S
    rows, helpers = S.compare_with_census()
    guards = S.guard_rows()
    good = S.build_ledger(rows, helpers, guards)
    assert S.check_ledger(good, rows, guards, helpers) == []

    mutant, _why = C.mutate(good, "_helpers_ignoring_arguments",
                            C.MUT_CORRUPT)
    found = S.check_ledger(mutant, rows, guards, helpers)
    assert [f[:2] for f in found] == \
        [("S003", "_helpers_ignoring_arguments")]


def test_a_total_missing_from_the_tree_is_no_longer_invisible():
    """S001 used to iterate the LIVE totals alone, so a total that exists
    on disk and no longer exists in the tree could not be reported."""
    import subjprov as S
    rows, helpers = S.compare_with_census()
    guards = S.guard_rows()
    good = S.build_ledger(rows, helpers, guards)
    stale = json.loads(json.dumps(good))
    stale["totals"]["a_total_the_tree_stopped_publishing"] = 1
    assert [f[1] for f in S.check_ledger(stale, rows, guards, helpers)] == \
        ["a_total_the_tree_stopped_publishing"]


def test_subjprov_check_no_longer_raises_on_a_ledger_without_totals():
    import subjprov as S
    rows, helpers = S.compare_with_census()
    guards = S.guard_rows()
    good = S.build_ledger(rows, helpers, guards)
    mutant, _ = C.mutate(good, "totals", C.MUT_DELETE)
    codes = [f[0] for f in S.check_ledger(mutant, rows, guards, helpers)]
    assert codes[0] == "S001" and "S003" not in codes


def test_assertshadow_check_now_sees_its_own_headline_totals():
    """Round 512's next-step #6. The three numbers the CLI prints as its
    headline had drifted 72 -> 76 files, 1935 -> 2029 test functions and
    3908 -> 4122 asserts, and nothing compared them to anything."""
    import assertshadow as A
    funcs = A.scan_tree()
    good = A.build_census(funcs)
    assert A._residual(good, funcs) == []

    mutant, _ = C.mutate(good, "totals", C.MUT_CORRUPT)
    assert [k for k, _ in A._residual(mutant, funcs)] == ["totals"]
    mutant, _ = C.mutate(good, "by_file", C.MUT_CORRUPT)
    assert [k for k, _ in A._residual(mutant, funcs)] == ["by_file"]


def test_the_assertshadow_residual_does_not_fire_on_a_history_census():
    """A total gate that reports a spurious finding on every run is a gate
    that gets deleted. `--history` runs `git log -L` per pair, so the
    residual rebuilds with the SAME shape as the document it is given."""
    import assertshadow as A
    funcs = A.scan_tree()
    with_history = A.build_census(funcs, history=True)
    assert "_history" in with_history
    assert A._residual(with_history, funcs) == []
    assert A._residual(A.build_census(funcs, history=False), funcs) == []


@pytest.mark.parametrize("verb,flag", [("subjprov.py", "--ledger"),
                                       ("assertshadow.py", "--census")])
def test_each_check_verb_can_be_pointed_at_a_candidate_file(verb, flag,
                                                            tmp_path):
    """WHY NOBODY HAD MEASURED THIS. Before round 516 the only way to run
    either verb against a candidate was to overwrite the real ledger."""
    name = ("subject-provenance.json" if verb == "subjprov.py"
            else "assert-shadow-census.json")
    src = os.path.join(C.LEDGER_DIR, name)
    dest = str(tmp_path / name)
    with open(src, encoding="utf-8") as fh:
        obj = json.load(fh)
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    r = subprocess.run([sys.executable, verb, "--check", flag, dest],
                       cwd=os.path.dirname(HERE), capture_output=True,
                       text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]


# ---------------------------------------------------------------------------
# 6. round 518 -- the headline was an OR, and the module's own import edge
# ---------------------------------------------------------------------------

def test_a_key_seen_under_only_one_mutation_kind_is_partial_not_total(
        tmp_path):
    """`seen` is an OR over `delete` and `corrupt`, and round 516's
    published coverage counted it. A gate that notices a key CHANGE and
    not a key VANISH has a hole, and the OR reports it as covered."""
    gate = _gate_script(tmp_path,
                        "sys.exit(0 if d.get('k') in (1, None) else 1)")
    ledgers = _ledger(tmp_path, {"k": 1})
    row = C.scope_one("synthetic.json", gate, ledgers)
    cell = row["keys"][0]
    assert [cell["verdicts"][C.MUT_DELETE],
            cell["verdicts"][C.MUT_CORRUPT]] == [C.BLIND, C.SEES]
    assert [cell["seen"], cell["total"], cell["partial"]] == \
        [True, False, True]
    cov = C.coverage([row])
    assert [cov["keys"], cov["seen"], cov["total"], cov["partial"]] == \
        [1, 1, 0, 1]


def test_a_no_op_mutation_is_not_an_applicable_kind(tmp_path):
    """Totality is over the APPLICABLE kinds. An empty list cannot be
    corrupted, so a gate that sees its deletion is total over it -- the
    alternative punishes a gate for a mutation the apparatus declined to
    make."""
    gate = _gate_script(tmp_path, "sys.exit(0 if 'k' in d else 1)")
    ledgers = _ledger(tmp_path, {"k": []})
    row = C.scope_one("synthetic.json", gate, ledgers)
    cell = row["keys"][0]
    assert cell["verdicts"][C.MUT_CORRUPT] == "n/a"
    assert [cell["applicable"], cell["total"], cell["partial"]] == \
        [[C.MUT_DELETE], True, False]


def test_the_report_publishes_both_numbers_and_marks_the_partial_cell(
        tmp_path):
    gate = _gate_script(tmp_path,
                        "sys.exit(0 if d.get('k') in (1, None) else 1)")
    ledgers = _ledger(tmp_path, {"k": 1})
    row = C.scope_one("synthetic.json", gate, ledgers)
    text = C.render_scope([row])
    assert "sees 1/1 key(s), total over 0" in text
    assert "PARTIAL" in text and "total gates: NONE" in text
    rep = C.build_report([row])
    assert rep["totals"]["seen"] == 1
    assert rep["totals"]["seen_under_every_applicable_mutation"] == 0
    assert rep["totals"]["partial"] == 1


def test_the_live_partial_cell_is_the_assertshadow_history_shape_key():
    """THE ONE ON THIS TREE, and it is the residual's own design.

    `assertshadow._residual` rebuilds the census with the DECLARED
    document's history shape (`history="_history" in declared`) so that a
    `--check` run, which does not walk `git log -L`, does not report
    `_history` as drift on every invocation. The cost is that DELETING
    `_history` changes the shape of the live document to match, and the
    two agree about a key that is gone."""
    import assertshadow as A                          # noqa: PLC0415
    funcs = []
    declared = A.build_census(funcs, history=True)
    assert "_history" in declared
    without = dict(declared)
    del without["_history"]
    assert A._residual(without, funcs) == [], (
        "deleting the shape key is invisible -- the live side loses it too")
    corrupted, _why = C.mutate(declared, "_history", C.MUT_CORRUPT)
    assert [k for k, _w in A._residual(corrupted, funcs)] == ["_history"]


# --- who else imports this module (round 516's next-step #4) ----------------

def test_every_module_that_imports_checkscope_touches_only_the_pure_differ():
    """ROUND 516's NEXT-STEP #4 -- "benign, but a real edge and nothing
    tests for it". Four of the five gates this module MEASURES now import
    it. That is safe for exactly one attribute, and this is what says so."""
    rows = C.importers()
    got = dict((r["module"], r) for r in rows)
    assert set(got) >= {"assertshadow.py", "builtinlive.py", "runlive.py",
                        "subjprov.py"}, sorted(got)
    for name, r in sorted(got.items()):
        assert r["unsafe"] == [], (name, r)
        assert r["attributes"] == ["document_diff"], (name, r)
        assert r["scope"] == "function", (
            "%s imports the instrument at module scope; an instrument a "
            "gate needs at import time is a dependency, not a helper"
            % name)


def test_the_differ_reads_no_path_or_environment_derived_state():
    """WHY the edge is benign, stated so it can be falsified. If
    `document_diff` ever reads `LEDGER_DIR`, a gate importing it would
    read whatever directory the sweep pointed the module at."""
    reads = C.function_reads("document_diff")
    assert sorted(reads) == ["_short", "_summarise"], reads
    assert set(reads.values()) == {"function"}


def test_the_module_state_a_gate_must_not_reach_for_is_named_not_assumed():
    """AND IT IS NOT HYPOTHETICAL: `run_gate` SETS `AGI_RESEARCH_ROOT` to
    the mirror root while a pytest gate is measured, and `ROOT` /
    `LEDGER_DIR` are computed from it at import. A gate reading
    `checkscope.LEDGER_DIR` would be handed the MUTANT directory by the
    instrument grading it."""
    import ast                                        # noqa: PLC0415
    with open(os.path.join(os.path.dirname(HERE), "checkscope.py"),
              encoding="utf-8") as fh:
        bindings = C._module_bindings(ast.parse(fh.read()))
    assert [bindings["ROOT"], bindings["LEDGER_DIR"]] == ["path", "path"]
    assert "LEDGER_DIR" not in C.SAFE_ATTRIBUTES
    import inspect                                    # noqa: PLC0415
    assert "AGI_RESEARCH_ROOT" in inspect.getsource(C.run_gate)


def test_an_importer_that_reaches_past_the_differ_is_reported_unsafe(
        tmp_path):
    (tmp_path / "g.py").write_text(
        "import checkscope\n\n\ndef f():\n    return checkscope.LEDGER_DIR\n",
        encoding="utf-8")
    rows = C.importers(str(tmp_path))
    assert [rows[0]["module"], rows[0]["scope"], rows[0]["unsafe"]] == \
        ["g.py", "module", ["LEDGER_DIR"]]
    assert C.main(["--importers", "--strict", "--src", str(tmp_path)]) == 1
    assert C.main(["--importers", "--src", str(tmp_path)]) == 0


def test_a_lazy_import_inside_a_function_body_is_still_an_importer(tmp_path):
    (tmp_path / "g.py").write_text(
        "def f(a, b):\n"
        "    import checkscope\n"
        "    return checkscope.document_diff(a, b)\n", encoding="utf-8")
    rows = C.importers(str(tmp_path))
    assert [rows[0]["scope"], rows[0]["attributes"], rows[0]["unsafe"]] == \
        ["function", ["document_diff"], []]


def test_a_from_import_names_the_attribute_without_an_alias(tmp_path):
    (tmp_path / "g.py").write_text(
        "from checkscope import document_diff, LEDGER_DIR\n", encoding="utf-8")
    rows = C.importers(str(tmp_path))
    assert [rows[0]["attributes"], rows[0]["unsafe"]] == \
        [["LEDGER_DIR", "document_diff"], ["LEDGER_DIR"]]


def test_a_pytest_gate_can_reach_the_crash_class_at_all(tmp_path):
    """`_verdict` calls a run a CRASH by looking for the CPython traceback
    header. pytest's own traceback styles never print it, so for the one
    `pytest`-kind gate in the table a node that RAISED was scored SEES --
    indistinguishable from one that reported the drift. `--tb=native`
    prints the real header and the class means the same thing for both
    gate kinds."""
    t = tmp_path / "test_boom.py"
    t.write_text("def test_boom():\n    raise KeyError('gone')\n",
                 encoding="utf-8")
    def run(*extra):
        p = subprocess.run([sys.executable, "-m", "pytest", "-q",
                            "-p", "no:cacheprovider"] + list(extra) + [str(t)],
                           cwd=str(tmp_path), capture_output=True, text=True)
        return C._verdict(p.returncode, (p.stdout or "") + (p.stderr or ""))
    assert run() == C.SEES
    assert run("--tb=native") == C.CRASH
    import inspect                                    # noqa: PLC0415
    assert "--tb=native" in inspect.getsource(C.run_gate)


# ---------------------------------------------------------------------------
# 6. round 519 -- the population `--selfref` could not read
#
# Three separate blindnesses, found by running round 516's next-step #5
# ("the query is mechanical") against `harness/tests/` and `skills/`:
#
#   a. the walk was a non-recursive `os.listdir`, so `--tests skills` read
#      0 of the 17 test files under it;
#   b. the unit was `ast.Assert`, so a `unittest` suite had a population of
#      ZERO -- `skills/skill-authoring/scripts` is 1 026 test functions and
#      1 863 `self.assert*` calls with no bare `assert` anywhere;
#   c. DECLARED-ness was a list of six helper NAMES, so the document read
#      the plain way (`open` / `json.load`) was invisible -- round 518's
#      next-step #3.
#
# ...and in every one of them the report printed
# "none -- every one has an operand measured from the tree", a claim about
# assertions it had never read.
# ---------------------------------------------------------------------------

UNITTEST_SHAPE = '''
import json
import unittest
import assertshadow as A


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.d = A.load_census()

    def test_the_totals_are_their_own_rows(self):
        self.assertEqual(self.d["totals"]["pairs"], len(self.d["rows"]))

    def test_a_pin_against_a_literal_is_not_vacuous(self):
        self.assertEqual(self.d["totals"]["pairs"], 58)

    def test_a_live_operand_clears_it(self):
        self.assertEqual(A.scan_tree(), self.d["totals"]["pairs"])

    def test_a_raise_is_not_a_comparison(self):
        with self.assertRaises(KeyError):
            self.d["nope"]
'''

ROUNDTRIP_SHAPE = '''
import json


def test_the_ledger_round_trips_through_its_own_encoding():
    path = ledger_path()
    raw = open(path, encoding="utf-8").read()
    obj = json.load(open(path, encoding="utf-8"))
    again = json.dumps(obj, indent=1, sort_keys=True) + "\\n"
    assert raw == again


def test_a_source_file_of_the_tree_is_a_live_measurement():
    script = os.path.join(HERE, "run_driver.sh")
    text = open(script, encoding="utf-8").read()
    assert text.index("SLOWTIER") < text.index("WHENCESLOW")


def test_a_fixture_this_function_wrote_is_its_own_data(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"a": 1}), encoding="utf-8")
    raw = open(str(p), encoding="utf-8").read()
    obj = json.load(open(str(p), encoding="utf-8"))
    assert raw == json.dumps(obj)
'''


def _names(found):
    return [f["func"] for f in found]


def test_a_unittest_assertion_is_an_assertion(tmp_path):
    """(b). The whole skills corpus turned on this one `isinstance`.

    `assertEqual`'s first two arguments are the compared expressions, and
    the same three exits have to hold for them as for a bare `assert`: a
    pin against a literal is not reported, one live operand clears it, and
    `assertRaises` is not a comparison at all."""
    rows, census = C.selfref_scan(_tests_dir(tmp_path, UNITTEST_SHAPE))
    assert _names(rows) == ["test_the_totals_are_their_own_rows"]
    assert rows[0]["form"] == "assertEqual"
    assert census["bare"] == 0 and census["unittest"] == 3
    assert census["skipped_pin"] == 1 and census["skipped_live"] == 1


def test_a_setup_bound_attribute_reaches_the_method(tmp_path):
    """The half of (b) that a name-keyed environment forgets: `unittest`
    binds its document in `setUp`, so the only `ast.Name` in either
    operand of the reported assertion above is `self`."""
    rows, _c = C.selfref_scan(_tests_dir(tmp_path, UNITTEST_SHAPE))
    assert any(o.startswith('self.d["totals"]') for o in rows[0]["operands"])


def test_the_walk_is_recursive(tmp_path):
    """(a). `--tests skills` read zero files and reported a clean tree;
    `skills/` has 17 test files and none of them at its top level."""
    d = tmp_path / "tree"
    (d / "sub" / "deeper").mkdir(parents=True)
    (d / "sub" / "deeper" / "test_x.py").write_text(
        "import assertshadow as A\n"
        "def test_x():\n"
        "    d = A.load_census()\n"
        "    assert d['a'] == d['b']\n", encoding="utf-8")
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "test_x.py").write_text("x = 1\n", encoding="utf-8")
    rows, census = C.selfref_scan(str(d))
    assert census["files"] == 1                     # not 2: __pycache__ out
    assert _names(rows) == ["test_x"]


def test_a_round_trip_through_the_files_own_encoding_is_reported(tmp_path):
    """(c), and round 518's next-step #3 by name. `raw == json.dumps(
    json.load(open(path)))` is `x == f(x)`: it can only ever see the
    ENCODING, and it was the ONLY node reading `_generated_by`."""
    rows, _c = C.selfref_scan(_tests_dir(tmp_path, ROUNDTRIP_SHAPE))
    assert "test_the_ledger_round_trips_through_its_own_encoding" in \
        _names(rows)
    row = [r for r in rows
           if r["func"].startswith("test_the_ledger_round")][0]
    assert row["operands"] == ["again(declared)", "raw(declared)"]
    assert row["reads"] == ["unresolved"]           # `ledger_path()`: a call


def test_reading_a_source_file_of_the_tree_is_not_a_self_reference(tmp_path):
    """The correction the first draft of (c) needed, measured rather than
    reasoned: 'reads a file from disk' is not 'reads the declared
    document'. Fifteen of the first draft's harness rows were
    `src = open(DRIVER_SRC).read(); assert src.index(a) < src.index(b)`,
    which IS a fresh measurement of the tree."""
    rows, _c = C.selfref_scan(_tests_dir(tmp_path, ROUNDTRIP_SHAPE))
    assert "test_a_source_file_of_the_tree_is_a_live_measurement" not in \
        _names(rows)
    assert C._read_target(
        ast.parse('open(os.path.join(H, "run_driver.sh"))').body[0].value,
        {}) == "source"
    assert C._read_target(
        ast.parse('open(os.path.join(H, "ledger.json"))').body[0].value,
        {}) == "data"


def test_a_fixture_the_test_wrote_itself_is_not_reported(tmp_path):
    """The other guard. A round trip over data the test created is a
    legitimate encoding test, not a gate that believes it checks the tree.
    Measured guard-off -> guard-on: whence 30 -> 25, harness 70 -> 40."""
    rows, _c = C.selfref_scan(_tests_dir(tmp_path, ROUNDTRIP_SHAPE))
    assert "test_a_fixture_this_function_wrote_is_its_own_data" not in \
        _names(rows)


def test_an_empty_population_is_not_a_clean_tree(tmp_path):
    """THE ROUND'S FINDING, held open. Two directories with nothing to
    report for two DIFFERENT reasons, and the old renderer printed the
    same sentence for both -- "none -- every one has an operand measured
    from the tree", quantified over the empty set."""
    empty = tmp_path / "empty"
    empty.mkdir()
    rows, census = C.selfref_scan(str(empty))
    text = C.render_selfref(rows, census)
    assert "EMPTY POPULATION" in text and "fact about the directory" in text

    d = _tests_dir(tmp_path, "import unittest\n\n\nclass T(unittest.TestCase):"
                             "\n    def test_a(self):\n        pass\n")
    rows2, census2 = C.selfref_scan(d)
    text2 = C.render_selfref(rows2, census2)
    assert census2["functions"] == 1 and census2["assertions"] == 0
    assert "EMPTY POPULATION" in text2 and "fact about the analysis" in text2

    # ...and a directory with real assertions and no findings says so
    # WITHOUT claiming the population was empty.
    d3 = _tests_dir(tmp_path, "def test_a():\n    assert 1 == 1\n",
                    name="test_ok.py")
    rows3, census3 = C.selfref_scan(d3)
    assert "EMPTY POPULATION" not in C.render_selfref(rows3, census3)


def test_the_census_partitions_every_assertion_it_read(tmp_path):
    """The conservation invariant. Every assertion leaves by exactly one
    of four doors, so a future exit that forgets to count itself makes the
    arithmetic fail rather than quietly shrinking the denominator."""
    for src in (UNITTEST_SHAPE, ROUNDTRIP_SHAPE, ROUND_512_SHAPE):
        _rows, c = C.selfref_scan(_tests_dir(tmp_path, src))
        assert c["assertions"] == c["bare"] + c["unittest"]
        assert c["assertions"] == (c["reported"] + c["skipped_live"]
                                   + c["skipped_pin"]
                                   + c["skipped_no_declared"])


def test_selfref_strict_reddens_on_an_empty_population(tmp_path):
    """A run that examined nothing and exited 0 is the failure that looks
    like a pass. `--strict` now says so; findings still do not redden,
    because the module publishes rather than filters."""
    empty = tmp_path / "nothing"
    empty.mkdir()
    root = os.path.dirname(HERE)
    def run(d, *extra):
        return subprocess.run(
            [sys.executable, os.path.join(root, "checkscope.py"),
             "--selfref", "--tests", str(d)] + list(extra),
            capture_output=True, text=True, cwd=root)
    assert run(empty).returncode == 0
    assert run(empty, "--strict").returncode == 1
    p = run(os.path.join(root, "tests"), "--strict")
    assert p.returncode == 0
    #: a FLOOR, not the count: this tree grows every language(C) round.
    n = int(p.stdout.split("population: ")[1].split(" file(s)")[0])
    assert n >= 70, p.stdout


def test_the_three_live_trees_all_have_a_readable_population():
    """The measurement round 516's next-step #5 asked for, kept as a
    regression. FLOORS, not equalities: these are live corpora and they
    grow. What must not come back is a ZERO -- the skills tree reported
    0 assertions out of 1 026 test functions before this round."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    for rel, min_files, min_asserts in (("harness/tests", 90, 4500),
                                        ("skills", 15, 2000),
                                        ("languages/whence/tests", 70, 4000)):
        _rows, c = C.selfref_scan(os.path.join(root, rel))
        assert c["files"] >= min_files, rel
        assert c["assertions"] >= min_asserts, rel


def test_the_skills_corpus_is_unittest_and_has_no_bare_assert():
    """Why (b) mattered here and not in the tree it was written for. The
    analysis was authored against `languages/whence/tests`, which is
    pytest and 100% bare `assert`; the checker corpus one directory over
    is `unittest` and 0% bare `assert`. The blindness is invisible from
    inside the tree the instrument was built in."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    _r, c = C.selfref_scan(os.path.join(root, "skills/skill-authoring/scripts"))
    assert c["bare"] == 0
    assert c["unittest"] >= 1800
    _r2, c2 = C.selfref_scan(os.path.join(root, "languages/whence/tests"))
    assert c2["unittest"] == 0
    assert c2["bare"] >= 4000
