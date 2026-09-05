"""Round 500 (language C). Tests for `subjprov.py`, and the two gates that
keep round 498's next-step #2 from having to be re-derived.

    "The `tree_derived` axis is the weakest thing in the instrument and it
    is the one that decides what gets fixed... the honest version is
    dataflow (does the magnitude's subject trace to a value the function
    constructs, or to one it is handed) and nobody has costed that."

ORDER, and it is the same argument round 494 and round 498 both used:

  1. the lattice and the resolution rules, falsified in BOTH directions on
     synthetic input, one test per rung;
  2. the three refinements that each cost this round a wrong answer before
     they existed -- argument-sensitive readers, ordered write-then-read,
     and the recursive-helper fixpoint -- each pinned against the exact
     construct that broke it;
  3. the assumption's falsifier, `reaches_tree_regardless`;
  4. the live tree: the join with the census must be TOTAL, the two axes'
     disagreements must be exactly the three this round published, and the
     residual must be a real residual rather than a lookup failure;
  5. `assertshadow.check_coordinates`, the gate this round added after
     finding round 498's ledger five pairs out of date;
  6. this file's own footprint, swept by the instrument round 498 built.

Every assertion is written shape-first. Section 6 is what stops that being
a claim.
"""

import ast
import json
import os
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import assertshadow as A                                       # noqa: E402
import curecheck as _C                                         # noqa: E402
import subjprov as S                                           # noqa: E402


def _resolve(src, func="t", line=None):
    """`(prov, {name: prov})` for the LAST assert in `func` of `src`."""
    tree = ast.parse(textwrap.dedent(src))
    mod = S.ModuleIndex(tree, "<synth>")
    res = S.Resolver(mod)
    fn = [n for n in ast.walk(tree)
          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
          and n.name == func][0]
    asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    node = ([a for a in asserts if a.lineno == line] or asserts)[-1]
    return res.assertion(fn, node.test)


def _prov(src, func="t", line=None):
    return _resolve(src, func, line)[0]


# ---------------------------------------------------------------------------
# 1. the lattice and the rungs
# ---------------------------------------------------------------------------

def test_the_lattice_is_ordered_by_drift_risk_and_join_takes_the_worst():
    """`join` is a max over `PROV_ORDER`, and the ORDER is the claim.

    `unknown` sits between `scratch` and `handed` deliberately: it must
    beat the two clean rungs, so a residual can never be reported as
    clean, and it must LOSE to the two derived rungs, so a resolved
    finding is never downgraded to a residual by an unrelated name in the
    same assertion."""
    assert list(S.PROV_ORDER) == \
        ["local", "scratch", "unknown", "handed", "tree"]
    assert sorted(S.DERIVED) == ["handed", "tree"]
    assert [S.join([]), S.join(["local", "tree"]),
            S.join(["scratch", "unknown"]), S.join(["unknown", "handed"]),
            S.join(["handed", "tree"])] == \
        ["local", "tree", "unknown", "handed", "tree"]
    assert "unknown" not in S.DERIVED


def test_each_rung_is_reached_by_its_own_construct():
    """One synthetic function per rung, and every one of them is a shape
    assertion so this test cannot contribute a shadow of its own."""
    local = """
        def t():
            rows = [1, 2, 3]
            assert rows == [1, 2, 3]
        """
    scratch = """
        def t(tmp_path):
            rows = tmp_path
            assert rows == []
        """
    handed = """
        def t(lib):
            rows = lib
            assert rows == []
        """
    tree = """
        def t():
            rows = open("x").read()
            assert rows == []
        """
    unknown = """
        def t():
            rows = whatever()
            assert rows == []
        """
    assert [_prov(local), _prov(scratch), _prov(handed),
            _prov(tree), _prov(unknown)] == \
        ["local", "scratch", "handed", "tree", "unknown"]


def test_a_module_level_constant_is_local_and_a_parameter_is_not():
    """The distinction round 498's axis could not draw. Both functions take
    NO fixture and call nothing in the name list, so `tree_derived` answers
    False for both; the assertions have opposite provenance."""
    src = """
        CASES = ['a', 'b']

        def t():
            xs = CASES
            assert xs == ['a', 'b']

        def u(corpus):
            xs = corpus
            assert xs == ['a', 'b']
        """
    assert [_prov(src, "t"), _prov(src, "u")] == ["local", "handed"]


def test_a_subscript_or_attribute_chain_reduces_to_its_root():
    src = """
        def t(fixture):
            assert fixture['a'].b[0] == ['x']
        """
    prov, per = _resolve(src)
    assert [prov, sorted(per)] == ["handed", ["fixture"]]


def test_dunder_file_is_the_tree():
    """`ROOT = os.path.dirname(os.path.abspath(__file__))` is how every
    test file in this tree reaches the repo. Resolving `__file__` any other
    way makes `ROOT` a local string and every `subprocess.run([..., ROOT +
    '/bench/x.py'])` look like a value the test built for itself."""
    src = """
        import os
        ROOT = os.path.dirname(os.path.abspath(__file__))

        def t():
            out = open(os.path.join(ROOT, 'thing.py')).read()
            assert out == []
        """
    assert _prov(src) == "tree"


def test_an_import_is_neither_a_subject_nor_a_receiver():
    """`assert DC.depth_of(v) == 3` is about `v`.

    Resolving `DC` as a value answered `unknown`, and that `unknown` then
    won the join over a perfectly resolved `local`. Five of this module's
    eleven starting residuals were this and nothing else."""
    src = """
        import depthcensus as DC

        def t():
            v = [1, 2]
            assert DC.spine_of(v) == ['int']
        """
    prov, per = _resolve(src)
    assert [prov, sorted(per)] == ["local", ["v"]]


def test_subjects_and_the_two_name_lists_agree_with_assertshadow():
    """Three predicates are duplicated rather than imported, so that this
    module reads on its own. A duplicate that is allowed to drift is worse
    than an import; these fail the day one does."""
    src = "def t():\n    assert len(sorted(rows)) == 3\n"
    node = [n for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Assert)][0]
    assert [sorted(S._subject_names(node.test)),
            S.NEUTRAL == A._NEUTRAL,
            S.SCRATCH_FIXTURES == A._PYTEST_BUILTINS] == \
        [["rows"], True, True]


# ---------------------------------------------------------------------------
# 2. the three refinements, each against the construct that broke it
# ---------------------------------------------------------------------------

def test_a_reader_is_argument_sensitive_and_this_is_the_whole_point():
    """SAME READER, opposite verdicts, decided by the argument.

    `dc.harvest_tests()` walks `languages/whence/tests/` -- the corpus,
    which grows every round for reasons that have nothing to do with the
    node asserting on it. `dc.harvest_tests(str(a))` with `a` under
    `tmp_path` walks two files the test wrote four lines earlier, and
    cannot drift at all. Round 498's name-list axis reports the same
    verdict for both, because it never looks at a call's arguments."""
    corpus = """
        import depthcensus as dc

        def t():
            _p, stats = dc.harvest_tests()
            assert stats == {}
        """
    own = """
        import depthcensus as dc

        def t(tmp_path):
            _p, stats = dc.harvest_tests(str(tmp_path))
            assert stats == {}
        """
    assert [_prov(corpus), _prov(own)] == ["tree", "scratch"]


def test_opening_a_path_for_writing_is_not_reading_the_tree():
    src = """
        import os
        HERE = os.path.dirname(os.path.abspath(__file__))

        def t():
            with open(os.path.join(HERE, 'x.py'), 'w') as fh:
                fh.write('hello')
            assert fh == []
        """
    calls = [n for n in ast.walk(ast.parse(textwrap.dedent(src)))
             if isinstance(n, ast.Call)]
    opens = [c for c in calls
             if isinstance(c.func, ast.Name) and c.func.id == "open"]
    assert [S._is_write_open(o) for o in opens] == [True]


def test_a_file_this_function_wrote_holds_this_functions_own_data():
    """`_harvest_source(src, tag)` writes a synthetic module into `tests/`
    and harvests it straight back. The PATH is in the tree -- it is
    `os.path.join(HERE, name)` and `HERE` comes from `__file__` -- but the
    CONTENT is a string literal from the caller, and the content is what
    the assertion is about."""
    src = """
        import os
        import depthcensus as dc
        HERE = os.path.dirname(os.path.abspath(__file__))

        def harvest(text, name):
            path = os.path.join(HERE, name)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(text)
            try:
                return dc.harvest_file(path)
            finally:
                os.remove(path)

        def t():
            rows, stats = harvest('CASES = []\\n', '__tmp.py')
            assert stats == {}
        """
    assert _prov(src) == "local"


def test_the_write_back_rule_is_ORDERED_and_a_read_before_a_write_is_a_read():
    """`test_v10.py` READS a file and then sabotages it:

        s = open(p).read()
        open(p, 'w').write(s.replace(old, new))

    A flow-insensitive write-back rule resolves the read to what the later
    write carried, chases `s` back to the same read, and recurses forever
    -- the first version of this rule died with a RecursionError on exactly
    this shape. Ordering the writes fixes the ANSWER as well as the crash:
    the read predates the write, so it is a tree read, and `test_v10.py`
    stays costly."""
    src = """
        import os
        HERE = os.path.dirname(os.path.abspath(__file__))

        def t():
            p = os.path.join(HERE, 'interp.py')
            s = open(p).read()
            open(p, 'w').write(s.replace('a', 'b'))
            assert [s] == ['x']
        """
    assert _prov(src) == "tree"


def test_a_recursive_helper_settles_to_a_fixpoint_and_not_to_the_residual():
    """`test_v30.py`'s `h` is `host(src)`; `host` returns `deep(payload)`;
    and `deep` walks a value recursively. Answering `unknown` at the
    recursive edge -- which is what the first version did -- put the one
    node round 498 had correctly hand-declared a false positive into the
    residual instead of resolving it to `local`.

    A least fixpoint from the bottom of the lattice is the textbook answer
    and it converges here in one pass."""
    src = """
        def deep(p):
            if isinstance(p, list):
                return tuple(deep(e) for e in p)
            return p

        def host(text):
            return deep(text)

        def t():
            h = host('let y = g(4)')
            assert [h] == ['x']
        """
    assert _prov(src) == "local"


def test_the_fixpoint_still_reports_tree_when_the_recursion_reads_the_tree():
    """The companion direction: optimistic initialisation must not be able
    to launder a real tree read through a recursive call."""
    src = """
        def deep(p):
            if isinstance(p, list):
                return tuple(deep(e) for e in p)
            return open('corpus.txt').read()

        def t():
            h = deep([1])
            assert [h] == ['x']
        """
    assert _prov(src) == "tree"


# ---------------------------------------------------------------------------
# 3. the assumption, and its falsifier
# ---------------------------------------------------------------------------

def test_a_helper_that_ignores_its_arguments_taints_what_it_returns():
    """`test_v10.py::_copy_package(dst)` returns `os.path.join(dst,
    'whence_ref')` -- a path under the caller's SCRATCH directory, so
    return-provenance alone says `scratch`. The line above it copied
    `ROOT/whence` into that directory. The path is scratch; the content is
    the tree."""
    src = """
        import os
        import shutil
        ROOT = os.path.dirname(os.path.abspath(__file__))

        def copy_package(dst):
            pkg = os.path.join(dst, 'whence_ref')
            shutil.copytree(os.path.join(ROOT, 'whence'), pkg)
            return pkg

        def t(tmp_path):
            pkg = copy_package(str(tmp_path))
            body = open(os.path.join(pkg, 'interp.py')).read()
            assert [body] == ['x']
        """
    assert _prov(src) == "tree"


def test_computing_a_path_in_the_tree_is_not_reaching_the_tree():
    """The narrowing that `reaches_tree_regardless` needed.

    `os.path.join(HERE, name)` evaluates to `tree` and reads not one byte.
    Flagging it re-broke the write-then-read-back case that had just been
    fixed, which is how the narrowing was found."""
    src = """
        import os
        HERE = os.path.dirname(os.path.abspath(__file__))

        def pathfor(name):
            return os.path.join(HERE, name)

        def reader(name):
            return open(os.path.join(HERE, name)).read()

        def t():
            assert [1] == [1]
        """
    tree = ast.parse(textwrap.dedent(src))
    res = S.Resolver(S.ModuleIndex(tree, "<synth>"))
    fns = dict((n.name, n) for n in tree.body
               if isinstance(n, ast.FunctionDef))
    assert [res.reaches_tree_regardless(fns["pathfor"]),
            res.reaches_tree_regardless(fns["reader"])] == [False, True]


def test_a_test_function_is_never_reported_as_a_helper():
    """Nothing calls a test function, so "arguments dominate" is never
    applied to one and it cannot be a counter-example to the assumption.
    Counting them reported 316 across this tree -- the size of the suite,
    not the size of the guess."""
    src = """
        def test_reads_the_tree():
            return open('x').read()

        def helper_reads_the_tree():
            return open('x').read()
        """
    tree = ast.parse(textwrap.dedent(src))
    res = S.Resolver(S.ModuleIndex(tree, "<synth>"))
    assert [h for h, _p, _k in res.helpers_that_ignore_their_arguments()] == \
        ["helper_reads_the_tree"]


# ---------------------------------------------------------------------------
# 4. the second axis
# ---------------------------------------------------------------------------

def test_guards_a_use_separates_a_precondition_from_a_shadow():
    """A precondition guards a USE; a shadow stands in front of a door.

    Both functions below have a tree-derived magnitude above a shape
    assertion, and the ONLY difference is whether the subject is touched in
    between. Provenance cannot tell them apart, which is why round 498's
    single axis had to carry two questions and got one of them wrong."""
    guard = """
        def t():
            s = open('p').read()
            assert s.count('x') > 1
            open('p', 'w').write(s.replace('x', 'y'))
            assert [1] == [1]
        """
    shadow = """
        def t():
            rows = open('p').read()
            assert len(rows) == 114
            assert [1] == [1]
        """
    out = []
    for src in (guard, shadow):
        tree = ast.parse(textwrap.dedent(src))
        fn = [n for n in tree.body if isinstance(n, ast.FunctionDef)][0]
        a = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
        out.append(S.guards_a_use(fn, a[0], a[1]))
    assert out == [True, False]


def test_another_assertion_in_between_is_not_a_use():
    """Three magnitudes stacked above one shape assertion do not make each
    other preconditions -- that is the shadow, at depth."""
    src = """
        def t():
            rows = open('p').read()
            assert len(rows) == 3
            assert len(rows) == 3
            assert [1] == [1]
        """
    tree = ast.parse(textwrap.dedent(src))
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef)][0]
    a = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    assert S.guards_a_use(fn, a[0], a[2]) is False


# ---------------------------------------------------------------------------
# 5. the live tree
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live():
    rows, helpers = S.compare_with_census()
    return rows, helpers, S.guard_rows()


def test_every_census_pair_finds_its_assertion(live):
    """THE GATE THAT MAKES THE RESIDUAL MEAN ANYTHING.

    `compare_with_census` joins on `(file, func, magnitude_line)`. A pair
    that fails to join silently defaults to `unknown` -- so a stale ledger
    coordinate reads as an unresolvable name, and the published residual
    measures the ledger's age rather than the analysis's reach. Five of
    this round's first ten residuals were exactly that, and it is how the
    stale-coordinate finding in `assertshadow.check_coordinates` was
    found."""
    rows, _helpers, _guards = live
    unjoined = [(r["node"], r["magnitude_line"]) for r in rows
                if not r["subjects"] and r["prov"] == "unknown"]
    assert unjoined == []
    #
    # ROUND 512: this line read `== [57, 57]`, which conflated two claims.
    # It split them, and ROUND 516 found the half it kept is not the claim
    # the comment says it is. `checkscope.py --selfref` reported this
    # assertion as one whose truth is a function of the LEDGER ALONE, and
    # it is: `compare_with_census` emits one row per census pair
    # UNCONDITIONALLY -- a pair that fails to join still produces a row,
    # with `prov` defaulted to "unknown" -- so `len(rows)` counts the
    # census's own pairs and can never disagree with a census whose
    # `totals` agrees with its `nodes`. The join invariant is asserted two
    # lines above, by `unjoined == []`, and that is the line that would go
    # red. What survives here is a real but DIFFERENT claim: the census's
    # published `totals["pairs"]` agrees with its own `nodes` -- which,
    # until this round, was the only place in the tree that compared them
    # (`assertshadow --check` was measured BLIND to its own `totals`).
    # `test_the_pair_count_identity_cannot_see_a_join_failure` below is
    # the falsification. The SIZE (and that count is 57) moves on any
    # corpus addition contributing a shadow pair.
    #
    # The conflation hid a twelve-round staleness. Round 510 added
    # `tests/test_branchlive.py`, which contributes a shadow pair -- but
    # `state/whence/assert-shadow-census.json` had not been regenerated
    # since round 500, so BOTH sides of the comparison read the stale 57
    # and this node stayed green while the ledger was twelve rounds out of
    # date. Round 512 regenerated it (`corpusledger.py --fix`); both sides
    # moved to 58 and only then did the literal disagree. Decision 64 --
    # size may not share a node with shape -- is why the size now lives in
    # `test_the_number_of_census_pairs_is_pinned` instead of here.
    assert len(rows) == A.load_census()["totals"]["pairs"]


def test_the_pair_count_identity_cannot_see_a_join_failure(tmp_path):
    """ROUND 516: the falsification for the comment above.

    A census naming a node this tree does not contain is the strongest
    join failure there is. `compare_with_census` still returns exactly one
    row per declared pair, so `len(rows) == census["totals"]["pairs"]`
    holds -- and the assertion that was named for the join invariant is
    green on a census that joins to nothing. `unjoined == []` is the one
    that fires."""
    empty = tmp_path / "tests"
    empty.mkdir()
    census = {
        "nodes": {"test_no_such_file.py::test_nothing": {
            "lineno": 1,
            "pairs": [{"magnitude_line": 1, "shape_line": 2,
                       "magnitude": "assert len(x) > 0",
                       "shape": "assert x == []",
                       "independent": False, "tree_derived": False}]}},
        "totals": {"pairs": 1},
    }
    rows, _helpers = S.compare_with_census(str(empty), census)
    assert len(rows) == census["totals"]["pairs"] == 1
    assert [(r["prov"], r["subjects"]) for r in rows] == [("unknown", {})]

    unjoined = [r["node"] for r in rows
                if not r["subjects"] and r["prov"] == "unknown"]
    assert unjoined == ["test_no_such_file.py::test_nothing"]


def test_the_number_of_census_pairs_is_pinned(live):
    """The SIZE, alone, so it can move without shadowing the invariant above.

    57 from round 500 to round 510; 58 from round 512, when
    `tests/test_branchlive.py`'s shadow pair finally entered a census that
    had been stale since round 500.

    Kept rather than deleted: the invariant above compares two numbers that
    are both derived from the census, so a collapse to zero pairs would
    satisfy it perfectly. This node is the only thing that would notice."""
    rows, _helpers, _guards = live
    assert len(rows) == 58


def test_the_two_axes_disagree_on_exactly_these_three_pairs(live):
    """The whole result of round 498's next-step #2, as a set.

    Both directions are represented, which is the point: dataflow is not a
    filter that only ever says `no`. It removes the one node round 498 had
    to declare a false positive by hand, and it finds two tree-derived
    magnitudes the name list could not see -- both in functions that take
    no fixture and call nothing in the 25-word list."""
    rows, _helpers, _guards = live
    dis = sorted((r["node"].split("::")[0], r["magnitude_line"],
                  r["heuristic"], r["prov"])
                 for r in rows if r["heuristic"] != r["derived"])
    assert dis == [
        ("test_lexer_guest_parity.py", 574, False, "tree"),
        ("test_v30.py", 335, True, "local"),
        ("test_v44.py", 191, False, "tree"),
    ]


def test_the_costly_set_is_the_same_size_and_not_the_same_set(live):
    """THE RESULT THAT WAS NOT PREDICTED, kept as a pin because it is the
    honest shape of the answer.

    Dataflow does not shrink the costly population at all: 7 pairs in 2
    nodes before, 7 pairs in 2 nodes after. It SWAPS a member -- round
    498's hand-declared false positive leaves, and a node the name list
    never saw arrives. The axis that actually cuts the population is the
    second one."""
    rows, _helpers, guards = live
    t = S.totals(rows, guards)
    assert [t["pairs_costly_heuristic"], t["nodes_costly_heuristic"],
            t["pairs_costly_dataflow"], t["nodes_costly_dataflow"],
            t["pairs_costly_unguarded"], t["nodes_costly_unguarded"]] == \
        [7, 2, 7, 2, 1, 1]
    old = sorted(set(r["node"] for r in rows
                     if r["independent"] and r["heuristic"]))
    new = sorted(set(r["node"] for r in rows
                     if r["independent"] and r["derived"]))
    assert [n for n in new if n not in old] == \
        ["test_v44.py::test_the_deepest_value_in_the_corpus_"
         "is_a_self_hosted_ast_14_deep"]
    assert [n for n in old if n not in new] == \
        ["test_v30.py::test_the_guest_never_merges_a_tail_loop"]


def test_the_one_unguarded_costly_pair_is_the_one_worth_repairing(live):
    """After both axes: ONE pair, in one node, and its own comment says the
    number moves for a reason the shape assertion is not about."""
    rows, _helpers, guards = live
    left = sorted((r["node"], r["magnitude_line"], r["magnitude"])
                  for r in rows
                  if r["independent"] and r["derived"]
                  and not guards.get((r["node"], r["magnitude_line"],
                                      r["shape_line"])))
    assert left == [
        ("test_v44.py::test_the_deepest_value_in_the_corpus_"
         "is_a_self_hosted_ast_14_deep", 191, "d == 14"),
    ]


def test_the_residual_is_small_named_and_never_counted_as_derived(live):
    """`unknown` is published, not folded. A residual that gets rounded
    into a verdict is how an instrument stops being falsifiable."""
    rows, _helpers, guards = live
    t = S.totals(rows, guards)
    unresolved = sorted(set(r["node"].split("::")[0] for r in rows
                            if r["prov"] == "unknown"))
    assert unresolved == ["test_folding.py", "test_timetravel.py",
                          "test_v35.py", "test_v43.py"]
    assert [t["unknown_residual"],
            any(r["derived"] for r in rows if r["prov"] == "unknown")] == \
        [5, False]


def test_the_assumptions_exposure_is_a_measured_number(live):
    """89 in-file helpers reach the tree while ignoring their arguments.
    Every one is handled correctly BECAUSE it is in a file this module
    parses; the number is what the guess would cost if they were one
    import away, and it is published for that reason rather than as a
    defect list."""
    _rows, helpers, _guards = live
    total = sum(len(v) for v in helpers.values())
    assert [total > 0, "test_v10.py" in helpers] == [True, True]
    assert sorted(h for h, _p in helpers["test_v10.py"]) == \
        ["_copy_package", "_have_rev", "_importable", "_ref_diff"]


def test_the_sweep_is_cheap_enough_to_run_beside_the_census():
    """No git, no subprocess, one `ast` parse per file."""
    r = subprocess.run([sys.executable, "subjprov.py", "--compare"],
                       cwd=S.HERE, capture_output=True, text=True,
                       timeout=300)
    assert [r.returncode, "COSTLY" in r.stdout] == [0, True], \
        r.stdout + r.stderr


def test_the_answer_is_the_same_in_two_processes():
    """ROUND 481's RULE, applied to a new module, and it caught a real one.

    The three per-function caches are keyed by `id(fn)` while the AST trees
    they describe are local to `analyse_file` and `guard_rows`. A tree is
    freed, the next one lands on the same addresses, and a cache lookup
    returns another file's bindings. Round 500 shipped exactly that: a
    `--json` immediately followed by a `--check` over an unchanged tree
    reported `unknown 7` and then `unknown 5`.

    Keying on an id and NOT holding the object is the defect; a test that
    runs the analysis once cannot see it. This runs it three times in three
    processes."""
    outs = []
    for _ in range(3):
        r = subprocess.run(
            [sys.executable, "-c",
             "import subjprov as S;"
             "rows, h = S.compare_with_census();"
             "print(sorted(S.totals(rows, S.guard_rows()).items()))"],
            cwd=S.HERE, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.append(r.stdout)
    assert outs[0] == outs[1] == outs[2]


def test_the_ledger_on_disk_matches_the_live_tree(live):
    rows, helpers, guards = live
    declared = S.load_ledger()
    assert S.check_ledger(declared, rows, guards, helpers) == []


def test_the_ledger_totals_are_the_sums_of_its_own_rows():
    """A published total a reader cannot re-derive from the rows beside it
    is a number they have to trust."""
    d = S.load_ledger()
    rows = d["pairs"]
    assert [sum(1 for r in rows if r["derived"]),
            sum(1 for r in rows if r["prov"] == "unknown"),
            sum(1 for r in rows if r["heuristic"] != r["derived"])] == \
        [d["totals"]["dataflow_derived"], d["totals"]["unknown_residual"],
         d["totals"]["disagree"]]


def test_the_ledger_is_where_the_module_says_it_is():
    p = S.ledger_path()
    assert [os.path.isabs(p), p.startswith(_C.AGI_ROOT),
            os.path.relpath(p, _C.AGI_ROOT)] == \
        [True, True, os.path.join("state", "whence",
                                  "subject-provenance.json")]


# ---------------------------------------------------------------------------
# 6. assertshadow.check_coordinates -- the gate this round added
# ---------------------------------------------------------------------------

def test_check_coordinates_fires_on_a_moved_pair_and_is_silent_otherwise():
    """Round 498's ledger carried five pairs across four nodes at a uniform
    +9 offset, with identical assertion text, against a file byte-identical
    to the one in round 498's own commit -- and `--check` said "ledger
    agrees" the whole time, because every SET it compared was in fact
    unchanged. `check_census` diffs node ids; `check_costly` diffs costly
    ids; neither looked inside a node."""
    live = A.scan_tree()
    exact = A.build_census(live)
    assert A.check_coordinates(exact, live) == []

    moved = json.loads(json.dumps(exact))
    nid = sorted(moved["nodes"])[0]
    pair = moved["nodes"][nid]["pairs"][0]
    was = (pair["magnitude_line"], pair["shape_line"])
    pair["magnitude_line"] -= 9
    pair["shape_line"] -= 9
    found = A.check_coordinates(moved, live)
    assert [f[0] for f in found] == [nid]
    assert [found[0][3], found[0][4]] == [was[0], was[1]]

    # ...and the SET gates stay silent on the very same ledger, which is
    # the reason this check had to exist rather than be assumed covered.
    assert [A.check_census(moved, live), A.check_costly(moved, live)] == \
        [([], []), ([], [])]


def test_a_changed_assertion_is_not_reported_as_a_move():
    """Editing the assertion itself is `check_census`/`check_costly`
    territory or a regeneration; reporting it here too would make the new
    finding indistinguishable from the old ones."""
    live = A.scan_tree()
    edited = json.loads(json.dumps(A.build_census(live)))
    nid = sorted(edited["nodes"])[0]
    edited["nodes"][nid]["pairs"][0]["magnitude"] = "len(nothing) == 999"
    edited["nodes"][nid]["pairs"][0]["magnitude_line"] -= 9
    assert A.check_coordinates(edited, live) == []


def test_the_cli_check_runs_all_three_gates_and_is_green_on_this_tree():
    """`check_costly` existed from round 498 and was exercised only by
    `test_assertshadow.py`; the CLI -- the path every failure message names
    as the way to check -- never called it."""
    r = subprocess.run([sys.executable, "assertshadow.py", "--check"],
                       cwd=A.HERE, capture_output=True, text=True,
                       timeout=300)
    assert [r.returncode, "ledger agrees" in r.stdout] == [0, True], \
        r.stdout + r.stderr
    body = open(os.path.join(A.HERE, "assertshadow.py"),
                encoding="utf-8").read()
    cli = body.split("if check:")[1]
    assert [name in cli for name in
            ("check_census", "check_costly", "check_coordinates")] == \
        [True, True, True]


# ---------------------------------------------------------------------------
# 7. this file's own footprint
# ---------------------------------------------------------------------------

def test_this_file_contains_no_shadow_of_its_own():
    """The instrument round 498 built, run against the file that extends
    it. A module that gates on count-above-shape and contains one would be
    the fourth instance in this program of an instrument reproducing the
    defect it measures."""
    mine = [f for f in A.scan_tree()
            if f["file"] == "test_subjprov.py" and f["pairs"]]
    assert ["%s::%s" % (f["file"], f["func"]) for f in mine] == []
