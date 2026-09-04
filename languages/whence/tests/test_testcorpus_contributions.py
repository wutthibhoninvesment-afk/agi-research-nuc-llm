"""Round 494 (language C): the per-file contribution ledger, and the
assertion that was on the line after the one that always failed first.

THE FINDING. `harness/reddebt.py note` -- round 493's new instrument, and
the reason this round looked here at all -- reported five
`tests/test_testcorpus_census.py` nodes red, NEW, opened by round 492,
owner language(C). `harness/crosstrack-registry.json` recorded WHY, in
round 493's words:

    "the counts moved by exactly one row each (115 <= 114, 68 == 67,
     (992+47)+22 == 1057). This is the 'your own artefacts are in the
     corpus' shape, not a defect in the census."

Both halves of that sentence are wrong, and re-deriving rather than quoting
is what found it. Harvesting `tests/` twice -- once whole, once with only
`test_v49.py` symlinked out -- gives round 492's exact contribution:

    calls               +4      (992 vs 988; NOT "one row", the call sum
                                 moved from 1057 to 1061)
    nonconstant_programs +1
    unresolved_args      +0
    module_calls         +0
    stmt_node_args       +0
    residual rows        +1
    building rows        +0     <-- the row is NOT string-building
    rest rows            +1     <-- 10 -> 11

The one new residual row is `test_v49.py:522`, class `attribute`:
`Interpreter().run(reprsweep.PROBE)`. That is the THIRD instance of the
un-modelled shape round 488 named -- "the program is a module attribute",
which unlike `@pytest.mark.parametrize` is not waiting on a widening,
because a program GENERATED from three live tables has no literal form to
fold to. It is the one thing in the whole delta the census exists to
report.

AND ITS ASSERTION NEVER RAN. In
`test_the_residual_that_is_not_string_building_is_seven_rows_in_three_shapes`
the ten-class `rest` list sat three lines below `assert len(rows) == 114`.
pytest evaluates asserts in source order and stops at the first failure, so
on every corpus addition since round 474 the SIZE assertion -- the one the
file's own comments call noise ("the count below moves whenever the corpus
grows, and the list below it moves only when something genuinely unreadable
arrives", round 482) -- shadowed the SHAPE assertion in the same node. The
signal has been reported by hand, by whichever round happened to read the
rows, in all six instances. Round 492 died at `--max-turns` and read
nothing, so this one was found by nobody until now.

TWO THINGS FOLLOW, and this file is both:

  1. SHAPE MUST NOT SHARE A NODE WITH SIZE.
     `test_the_shape_of_the_residual_is_asserted_where_no_count_can_shadow_it`
     is a structural gate over the census's own source: the node holding the
     class list may not contain a count assertion. It is not advice.

  2. SIZE MUST STOP BEING A WHOLE-TREE NUMBER. A total is blind to
     COMPOSITION -- one file gaining a residual row while another loses one
     moves nothing -- and it is why a corpus addition costs a later round a
     hand-written paragraph and six re-guessed literals in five tests
     (rounds 474, 476, 480, 482, 488, and 492 -> 494; 22 `ROUND NNN:`
     paragraphs in one file). `state/whence/testcorpus-contributions.json`
     makes the FILE the unit: adding a test file is one declared row whose
     numbers are checked against the live harvest, and the census's totals
     are the ledger's sums rather than a number somebody typed twice.

`test_a_compensating_move_is_invisible_to_a_total_and_visible_to_the_ledger`
is the negative control that says the ledger buys something: a synthetic
pair of files in which every census total is IDENTICAL before and after
while the composition is not. Without it, "the ledger is finer" is a claim.

Every Whence program in this file is a whole-program literal on purpose --
see `test_this_file_contributes_no_residual_row_to_the_corpus`. A file that
reports on the residual and then adds to it would be measuring itself, and
this round banked that as a prediction before writing a line of it.
"""

import ast
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import depthcensus as dc                                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CENSUS_SRC = os.path.join(HERE, "test_testcorpus_census.py")

#: The shape assertion's home. Named once so the two structural tests below
#: cannot drift apart, and so a rename of the node is a one-line edit here
#: rather than a silent pass.
SHAPE_NODE = ("test_the_residual_that_is_not_string_building_is_"
              "seven_rows_in_three_shapes")


@pytest.fixture(scope="module")
def live():
    """`stats["by_file"]` over the real `tests/` tree."""
    _progs, stats = dc.harvest_tests(by_file=True, keep_rows=True)
    return stats


@pytest.fixture(scope="module")
def declared():
    return dc.load_contributions()


# ---------------------------------------------------------------------------
# 1. the ledger against the tree
# ---------------------------------------------------------------------------

def test_the_ledger_covers_exactly_the_files_in_the_tree(live, declared):
    """MISSING and EXTRA are different failures and are reported as such.
    A single "69 != 70" is the shape this round is here to remove."""
    missing = sorted(set(live["by_file"]) - set(declared))
    extra = sorted(set(declared) - set(live["by_file"]))
    assert missing == [], (
        "test file(s) in the tree with no ledger row -- add one row per "
        "file with `python3 depthcensus.py --by-file`: %s" % missing)
    assert extra == [], (
        "ledger row(s) naming a file that is not in the tree: %s" % extra)


def test_every_declared_contribution_matches_the_live_harvest(live, declared):
    """The check that replaces six re-guessed literals. Its failure names
    the FILE and the KEY, so "somebody added a test file" and "an existing
    file's contribution changed" are different rows rather than one total
    moving by a number nobody can attribute.

    `check_contributions` also re-derives each live row's two internal
    identities -- `residual == unresolved_args + nonconstant_programs` and
    `residual == building + rest` -- because a ledger that can only be
    compared against itself proves nothing."""
    bad = dc.check_contributions(declared, live["by_file"])
    assert bad == [], "\n".join(
        "  %-40s %-34s declared=%s live=%s" % row for row in bad)


def test_the_ledger_sums_to_the_live_totals(live, declared):
    """CLOSURE. Every counter in the ledger is a partition of the tree by
    file, so the sums must be the whole-tree numbers exactly -- not a bound,
    not a floor. If this ever fails while the per-file check above passes,
    `harvest_tests` has a counter it increments outside the per-file loop."""
    tot = dc.contribution_totals(declared)
    assert tot["calls"] == live["calls"]
    assert tot["module_calls"] == live["module_calls"]
    assert tot["stmt_node_args"] == live["stmt_node_args"]
    assert tot["unresolved_args"] == live["unresolved_args"]
    assert tot["nonconstant_programs"] == live["nonconstant_programs"]
    assert tot["forwarded_args"] == live["forwarded_args"]
    assert tot["rows"] == live["programs_before_dedup"]
    assert tot["dup_cross_file"] == live["dup_cross_file"]
    assert tot["programs"] == live["programs"]
    resid = [r for r in live["rows"] if r["kind"] == "residual"]
    assert tot["residual"] == len(resid)
    assert tot["building"] == len([r for r in resid
                                   if dc.is_building(r["cls"])])
    assert tot["rest"] == tot["residual"] - tot["building"]


def test_the_ledger_agrees_with_the_two_identities_it_could_have_faked(
        declared):
    """The declared side's own arithmetic, checked separately from the live
    side. `check_contributions` verifies the identities against LIVE on
    purpose -- so that a ledger hand-edited to be internally consistent and
    wrong still fails there. This test closes the other direction: a ledger
    whose own rows do not add up is malformed regardless of the tree."""
    bad = [(f, row) for f, row in sorted(declared.items())
           if row["residual"] != row["unresolved_args"] +
           row["nonconstant_programs"]
           or row["residual"] != row["building"] + row["rest"]
           or row["programs"] != row["rows"] - row["dup_cross_file"]]
    assert bad == [], bad


# ---------------------------------------------------------------------------
# 2. what the ledger buys: the compensating move
# ---------------------------------------------------------------------------

_RUNNER = ("import sys\n"
           "sys.path.insert(0, '..')\n"
           "from whence.interp import Interpreter\n"
           "def run(src):\n"
           "    return Interpreter().run(src)\n")

#: A call the folder CAN read -- a whole-program literal. Contributes a
#: program and no residual.
_READABLE = "def t_ok():\n    run('let a = 1\\n')\n"

#: A call the folder CANNOT read -- the argument is a module attribute,
#: which is precisely `test_v49.py:522`'s class and has no literal form.
_RESIDUAL = ("import othermod\n"
             "def t_bad():\n"
             "    run(othermod.PROBE)\n")


def _write(directory, name, body):
    with open(os.path.join(directory, name), "w", encoding="utf-8") as fh:
        fh.write(_RUNNER + body)


def test_a_compensating_move_is_invisible_to_a_total_and_visible_to_the_ledger(
        tmp_path):
    """THE NEGATIVE CONTROL FOR THE WHOLE ROUND.

    Two synthetic test files. In arrangement A the residual row is in
    `test_aa.py`; in arrangement B it is in `test_bb.py` and `test_aa.py`
    has the readable call instead. Nothing about the tree's SIZE differs:
    every whole-tree counter the five census nodes assert on is identical.
    The composition is completely different, and only the per-file ledger
    says so.

    This is why "the census reddens on every corpus addition" and "the
    census is a good instrument" were both true and neither was the point:
    it is sensitive to the change that carries no information and blind to
    the change that does."""
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()
    _write(str(a), "test_aa.py", _RESIDUAL)
    _write(str(a), "test_bb.py", _READABLE)
    _write(str(b), "test_aa.py", _READABLE)
    _write(str(b), "test_bb.py", _RESIDUAL)

    _pa, sa = dc.harvest_tests(str(a), by_file=True, keep_rows=True)
    _pb, sb = dc.harvest_tests(str(b), by_file=True, keep_rows=True)

    # The arrangement is only interesting if it really does contain a
    # residual and a program -- a pair of files that harvest to nothing
    # would satisfy the totals trivially.
    assert sa["nonconstant_programs"] == 1, sa["nonconstant_programs"]
    assert sa["programs"] >= 1, sa["programs"]

    # EVERY whole-tree counter the census asserts on: identical.
    for k in ("files", "calls", "module_calls", "stmt_node_args",
              "unresolved_args", "nonconstant_programs", "programs",
              "programs_before_dedup", "dup_cross_file"):
        assert sa[k] == sb[k], (k, sa[k], sb[k])
    resid_a = [r for r in sa["rows"] if r["kind"] == "residual"]
    resid_b = [r for r in sb["rows"] if r["kind"] == "residual"]
    assert len(resid_a) == len(resid_b) == 1
    assert sorted(r["cls"] for r in resid_a) == \
        sorted(r["cls"] for r in resid_b)

    # The ledger is not.
    assert sa["by_file"] != sb["by_file"]
    bad = dc.check_contributions(sa["by_file"], sb["by_file"])
    assert sorted(set(f for f, _k, _d, _l in bad)) == \
        ["test_aa.py", "test_bb.py"], bad
    assert ("test_aa.py", "nonconstant_programs", 1, 0) in bad, bad
    assert ("test_bb.py", "nonconstant_programs", 0, 1) in bad, bad


def test_a_missing_row_and_an_extra_row_are_different_failures(tmp_path):
    """`check_contributions`' `"*"` key. A ledger with no row for a file
    that exists, and a row for a file that does not, must not reduce to the
    same message -- the first is "declare your new test file", the second is
    "a file was deleted and the ledger was not"."""
    d = tmp_path / "T"
    d.mkdir()
    _write(str(d), "test_aa.py", _READABLE)
    _p, s = dc.harvest_tests(str(d), by_file=True)
    live = s["by_file"]

    missing = dc.check_contributions({}, live)
    assert [(f, k) for f, k, _d, _l in missing] == [("test_aa.py", "*")]
    assert missing[0][2] is None and missing[0][3] is not None

    extra = dc.check_contributions({"test_zz.py": dict(live["test_aa.py"])},
                                   live)
    keys = sorted((f, k) for f, k, _d, _l in extra)
    assert ("test_zz.py", "*") in keys, keys
    assert ("test_aa.py", "*") in keys, keys


def test_a_ledger_that_agrees_on_every_total_and_no_file_still_fails(tmp_path):
    """The failure mode a SUM check cannot have. Swap two files' rows in an
    otherwise correct ledger: `contribution_totals` is unchanged, so the
    closure test above passes, and the per-file check reports both files."""
    d = tmp_path / "T"
    d.mkdir()
    _write(str(d), "test_aa.py", _RESIDUAL)
    _write(str(d), "test_bb.py", _READABLE)
    _p, s = dc.harvest_tests(str(d), by_file=True)
    live = s["by_file"]
    swapped = {"test_aa.py": dict(live["test_bb.py"]),
               "test_bb.py": dict(live["test_aa.py"])}
    assert dc.contribution_totals(swapped) == dc.contribution_totals(live)
    bad = dc.check_contributions(swapped, live)
    assert sorted(set(f for f, _k, _d, _l in bad)) == \
        ["test_aa.py", "test_bb.py"], bad


# ---------------------------------------------------------------------------
# 3. the structural gate: a count may not shadow a shape
# ---------------------------------------------------------------------------

def _census_functions():
    tree = ast.parse(open(CENSUS_SRC, encoding="utf-8").read())
    return dict((n.name, n) for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef))


def _count_asserts(fn):
    """Assertions of the form `len(...) == <int>` or `<name>[...] == <int>`
    -- a whole-tree magnitude compared to a literal. These are the
    assertions that move on every corpus addition and carry no information
    about what changed."""
    out = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assert):
            continue
        t = node.test
        if not isinstance(t, ast.Compare) or len(t.comparators) != 1:
            continue
        if not isinstance(t.ops[0], (ast.Eq, ast.LtE, ast.Lt,
                                     ast.GtE, ast.Gt)):
            continue
        rhs = t.comparators[0]
        if isinstance(rhs, ast.Constant) and isinstance(rhs.value, int) \
                and not isinstance(rhs.value, bool):
            out.append((node.lineno, ast.unparse(t)))
    return out


def test_the_census_shape_node_exists_under_the_name_this_file_pins():
    """A structural gate that silently passes because the node was renamed
    is worse than no gate. Checked before the gate that uses it.

    The name is round 468's and says SEVEN; the list it guards has said TEN
    since round 488 and says ELEVEN after round 492's `test_v49.py:522`.
    The name is kept anyway, deliberately: it is cited by
    `test_the_widening_did_not_move_the_other_residual_half`'s docstring and
    by `harness/crosstrack-registry.json`, and round 474 set the precedent
    for keeping a stale name so its citations keep landing. A count in a
    test's NAME is the same defect one level up as a count in a test's
    assertion, and this round records it rather than renaming a red node
    mid-episode."""
    assert SHAPE_NODE in _census_functions()


def test_the_shape_of_the_residual_is_asserted_where_no_count_can_shadow_it():
    """THE GATE. pytest stops a test at its first failing assert, so a
    count assertion above a shape assertion in the same function makes the
    shape assertion unreachable on exactly the rounds it matters -- every
    round that adds a test file.

    Measured, not argued: at round 494's start
    `test_the_residual_that_is_not_string_building_is_seven_rows_in_three_
    shapes` held `assert len(rows) == 114` and `assert len(building) == 104`
    three lines above the ten-class `rest` list, `rows` was 115, and the
    class list -- which had gone from ten entries to eleven, the first
    genuinely new residual shape since round 488 -- was never evaluated by
    any of the six rounds that hit this.

    This gate is why that cannot recur. It fails if anybody puts a
    magnitude-vs-literal comparison back into the shape node."""
    fn = _census_functions()[SHAPE_NODE]
    shadowing = _count_asserts(fn)
    assert shadowing == [], (
        "count assertion(s) inside the shape node -- a failing count here "
        "makes the class list below it unreachable: %s" % shadowing)


def test_the_gate_would_fire_on_the_shape_node_as_round_492_left_it():
    """A gate nobody has seen go red is a gate nobody has tested. The exact
    two assertions this round moved out, fed back through `_count_asserts`
    in a synthetic function of the same shape."""
    fn = ast.parse(
        "def f(rows, building, rest):\n"
        "    assert len(rows) == 114, len(rows)\n"
        "    assert len(building) == 104, len(building)\n"
        "    assert sorted(r['cls'] for r in rest) == ['attribute']\n"
    ).body[0]
    found = _count_asserts(fn)
    assert [line for line, _txt in found] == [2, 3], found
    assert "len(rows) == 114" in found[0][1]


def test_the_gate_does_not_fire_on_the_shape_assertion_itself():
    """The other half of the falsification: a list-equality assertion is
    not a count assertion, and a `> 0` positivity assertion is not one
    either. Without this the gate could be satisfied by a predicate that
    rejects everything."""
    fn = ast.parse(
        "def f(rest, stats):\n"
        "    assert sorted(r['cls'] for r in rest) == ['a', 'b']\n"
        "    assert stats['unresolved_args'] > 0\n"
    ).body[0]
    assert [txt for _l, txt in _count_asserts(fn)] == \
        ["stats['unresolved_args'] > 0"]


# ---------------------------------------------------------------------------
# 4. this file's own footprint
# ---------------------------------------------------------------------------

def test_this_file_contributes_no_residual_row_to_the_corpus(live):
    """Round 494 banked this as prediction P10 before writing the file:
    an instrument that reports on the corpus's residual and then adds to it
    is measuring itself. Every Whence program above is a whole-program
    literal, and the two synthetic PYTHON sources are `_RUNNER + body`
    string concatenations that the harvester reads as ordinary text -- they
    are written to a tmp_path and never appear in `tests/`.

    Note what this does NOT claim: the file contributes CALLS and PROGRAMS,
    which is a corpus addition like any other and is declared in the ledger
    like any other. What it must not contribute is a row nobody can read."""
    mine = live["by_file"].get("test_testcorpus_contributions.py")
    assert mine is not None, sorted(live["by_file"])
    assert mine["residual"] == 0, mine
    assert mine["rest"] == 0, mine
    assert mine["unresolved_args"] == 0 and mine["nonconstant_programs"] == 0


def test_the_ledger_on_disk_round_trips_through_its_own_encoding():
    """`state/whence/testcorpus-contributions.json` is regenerated by
    `python3 depthcensus.py --by-file --json <path>`, which writes
    `indent=1, sort_keys=True` and a trailing newline. Pinned because a
    regeneration with different defaults reformats every one of the ~69
    rows and buries the one that changed -- the reformat hazard this
    program has now paid twice (round 493, 42 lines then 1 027)."""
    path = dc.contributions_path()
    raw = open(path, encoding="utf-8").read()
    obj = json.load(open(path, encoding="utf-8"))
    again = json.dumps({"_generated_by": obj["_generated_by"],
                        "files": obj["files"]},
                       indent=1, sort_keys=True) + "\n"
    assert raw == again, "ledger is not in its generator's own encoding"
