#!/usr/bin/env python3
"""Which test nodes in this tree hide a SHAPE assertion behind a COUNT?

Round 498 (language C), taking round 494's next-step #1 verbatim:

    "The AST shadow gate is ONE NODE DEEP. `_count_asserts` is applied to
    exactly one function, named by a constant. Every other shape assertion
    in this tree is unswept -- `test_polarity.py`'s registry lists,
    `reprsweep.py`'s manifest tests, `test_testcorpus_suite_census.py` --
    and the same shadow can exist in any of them. The sweep is cheap (one
    `ast` walk per test file) and nothing here measured it. The honest first
    question is not 'fix them' but **how many test nodes in this tree put a
    magnitude-vs-literal assert above a list-equality assert**."

THE DEFECT, as round 494 established it by paying for it. `pytest` evaluates
a test function's asserts in order and stops at the first failure. So an
assertion of the form

    assert len(rows) == 114          # MAGNITUDE -- moves on every addition

placed above

    assert sorted(r["cls"] for r in rest) == [...eleven classes...]   # SHAPE

makes the shape assertion unreachable *on exactly the rounds it matters*.
Round 494 measured six such rounds (474, 476, 480, 482, 488, 492) for one
node, and found that in that window the shape assertion had gone stale in
two independent ways without any of the six red rounds being able to say so.

WHAT THIS MODULE IS NOT. It is not a linter for "assert order". A magnitude
assert is fine on its own; a shape assert is fine on its own; and a magnitude
assert *below* every shape assert in its node costs nothing. The defect is
strictly the ordered PAIR, and the population this module reports is pairs.

-------------------------------------------------------------------------
THREE THINGS THIS MODULE MEASURES THAT A COUNT OF CANDIDATES DOES NOT
-------------------------------------------------------------------------

1. **Branch compatibility.** Two asserts in opposite arms of an `if` are not
   a shadow, ever. `_slots` records each assert's chain of (block, field)
   slots and `_shadows` refuses any pair that diverges into different
   fields of the same block. Without this the sweep over-reports, and a
   sweep that over-reports gets ignored.

2. **Conditionality.** A magnitude assert nested inside `if`/`for`/`while`/
   `try` shadows only when its branch is taken. Reported as a separate
   field rather than folded into the headline, because the remedy differs:
   an unconditional shadow is a re-order, a conditional one may not be a
   defect at all.

3. **REALISED vs LATENT -- the field the whole module exists for.** A
   candidate says a shadow *can* fire. Git says whether it *has*. For each
   shadowing magnitude assert, `line_history` walks `git log -L` over that
   one line and counts the commits in which the integer literal on it
   actually CHANGED. That count is the number of times somebody re-pinned
   the number -- i.e. the number of rounds on which everything below that
   assert in its node went unevaluated. Round 494's node scored six by hand;
   this makes the same number available for every candidate in the tree.

   A candidate with 0 literal edits is a latent shadow. A candidate with 6
   is round 494's, and it cost two undetected defects.

-------------------------------------------------------------------------
WHY THE PREDICATES ARE WIDER THAN ROUND 494's, AND WHERE THEY ARE NOT
-------------------------------------------------------------------------

`is_magnitude_strict` is round 494's `_count_asserts` predicate, character
for character in behaviour: `Compare`, one comparator, op in
Eq/Lt/LtE/Gt/GtE, right-hand side a non-bool `int` constant. It is kept
EXACTLY so that this module's tree-wide number is comparable with round
494's node-level one, and so that a change to the gate in
`tests/test_testcorpus_contributions.py` can be diffed against it.

`is_magnitude` is NOT a pure widening of it, which round 498 found by
tabulating the two against each other rather than by assuming. It WIDENS on
two cases -- the literal may be on either side (`assert 114 == len(rows)`
shadows precisely as hard) and `NotEq` counts -- and it NARROWS on one:
`assert 1 == 1` satisfies `_count_asserts`, because that predicate asks only
whether the right-hand side is an integer, and a comparison of two literals
is not a claim about anything.

Measured over `tests/` at round 498: the two disagree on exactly TWO asserts,
both `r.returncode != 0` (`test_v10.py:684`, `test_v40.py:131`), and neither
forms a pair. So `pairs_strict == pairs` and the tree-wide number is
comparable with round 494's node-level one either way. Both counts are
reported regardless; `pairs_widened_only` is the difference.

`is_shape` is new. A shape assertion is a comparison (Eq/NotEq/In/NotIn)
with a non-empty list/set/tuple/dict DISPLAY on one side -- the literal
enumeration of what is expected. Empty displays (`assert bad == []`) are
counted separately as `shape_empty` and are NOT part of the headline: an
emptiness claim carries no composition to lose, which is the property that
made round 494's eleven-class list worth protecting.

-------------------------------------------------------------------------
PATHS
-------------------------------------------------------------------------

Everything outside this tree resolves through `curecheck.AGI_ROOT`, imported
LAZILY inside the function that needs it, and nothing is read at import
time. Both rules are curecheck's own round-413 notes, restated in
`depthcensus.contributions_path`: five `__file__`-derived roots once blocked
every Whence mutation campaign at the door, and a `state/` read at import
time aborted COLLECTION of the whole suite.

CLI
    python3 assertshadow.py                        # report, no git
    python3 assertshadow.py --history              # + realised-shadow counts
    python3 assertshadow.py --json <path>          # write the census
    python3 assertshadow.py --check                # ledger vs live, rc=1 on drift
    python3 assertshadow.py --check --census <p>  # ...against a candidate file
"""

import ast
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, "tests")

#: Ops that make a comparison a *magnitude* claim about a number.
_MAG_OPS = (ast.Eq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)

#: Ops that make a comparison a *shape* claim about a collection.
_SHAPE_OPS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)

#: Statement types whose bodies are conditionally reached.
_COND = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)

#: Commit-header marker for `git log --format=`. A diff CONTEXT line always
#: starts with a space, so no line of the diff body can be mistaken for this.
_COMMIT_MARK = "COMMIT-"


def _int_literal(node):
    """`True` for an integer constant that is not a bool.

    `isinstance(True, int)` is `True` in Python, so `assert x == True` would
    otherwise read as a magnitude assertion. Round 494's predicate excluded
    bools for the same reason and this keeps that."""
    return (isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool))


def _display(node):
    """A literal collection *display* -- `[...]`, `(...)`, `{...}`, `{k: v}`.

    A NAME that happens to hold a list is not a display: the point of a
    shape assertion is that the expectation is written out where a reader
    can diff it."""
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return len(node.elts)
    if isinstance(node, ast.Dict):
        return len(node.keys)
    return None


def is_magnitude_strict(test):
    """Round 494's `_count_asserts` predicate, unchanged.

    Kept separately from `is_magnitude` so the tree-wide number stays
    comparable with the one node round 494 measured, and so that widening
    is a reported delta rather than an invisible redefinition."""
    if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], _MAG_OPS):
        return False
    return _int_literal(test.comparators[0])


def is_magnitude(test):
    """Widened: the literal may be on either side, and `!=` counts.

    `assert 114 == len(rows)` shadows exactly as hard as
    `assert len(rows) == 114`; so does `assert len(rows) != 0` standing
    above a shape assertion. The one thing excluded is a comparison of two
    literals (`assert 1 == 1`), which is not a claim about the tree."""
    if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], _MAG_OPS + (ast.NotEq,)):
        return False
    left, right = test.left, test.comparators[0]
    lit = (_int_literal(left), _int_literal(right))
    return lit[0] != lit[1]


def is_shape(test):
    """A comparison against a NON-EMPTY collection display."""
    if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], _SHAPE_OPS):
        return False
    for side in (test.left, test.comparators[0]):
        n = _display(side)
        if n:
            return True
    return False


def is_shape_empty(test):
    """`assert x == []` and friends -- an emptiness claim.

    Reported, excluded from the headline. Losing one is losing the fact
    that a set was empty, not the fact that it held these eleven things."""
    if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], _SHAPE_OPS):
        return False
    return any(_display(s) == 0 for s in (test.left, test.comparators[0]))


def _len_subject(test):
    """For `len(X) == <int>`, the `(X-source, n)` pair; else `None`.

    Either order, `==` only: a `>=` ratchet is not implied by a shape
    assertion of any particular size."""
    if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
        return None
    if not isinstance(test.ops[0], ast.Eq):
        return None
    left, right = test.left, test.comparators[0]
    for call, lit in ((left, right), (right, left)):
        if not _int_literal(lit):
            continue
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) \
                and call.func.id == "len" and len(call.args) == 1:
            return ast.unparse(call.args[0]), lit.value
    return None


def _shape_sides(test):
    """For a shape assertion, `(other-side-source, element-count)`."""
    for a, b in ((test.left, test.comparators[0]),
                 (test.comparators[0], test.left)):
        n = _display(b)
        if n:
            return ast.unparse(a), n
    return None


def count_implied(mag_test, shape_test):
    """Does the shape assertion below already say what the count above says?

    True when the magnitude is `len(X) == n`, the shape compares an
    expression MENTIONING `X` against a display of exactly `n` elements, and
    both use `==`. `assert len(directional) == 22` above
    `assert sorted(directional) == [...22 names...]` is pure redundancy: the
    list below pins the length and the membership and the order, and the
    count above pins a strict subset of that while making the list below
    unreachable whenever it fires.

    NOT a proof, and named as a REMEDY rather than a verdict. `X` may be
    transformed on the way into the shape assertion (`sorted(X)`,
    `[r['id'] for r in X]`) and this checks only that `X` appears in the
    source of that transform, not that the transform preserves length. A
    human deleting the count on this signal has one thing to confirm; a
    human splitting the node has none. The default remedy is therefore
    `split`, and `delete_count` is an invitation to read."""
    a = _len_subject(mag_test)
    b = _shape_sides(shape_test)
    if a is None or b is None:
        return False
    if not isinstance(shape_test.ops[0], ast.Eq):
        return False
    subject, n = a
    other, k = b
    return k == n and subject in other


#: Names that carry no subject -- calling `len` in both asserts does not make
#: two assertions be about the same thing.
_NEUTRAL = frozenset("""
len sorted set sum max min list tuple dict str int float bool any all
repr type abs round enumerate zip range reversed frozenset next iter
""".split())


def subjects(test):
    """The NAMES an assertion is about, with pure builtins removed.

    `sorted(r['cls'] for r in rest)` is about `rest` (and its own bound
    `r`); `len(rows) == 114` is about `rows`. Attribute and subscript
    chains reduce to their root name, so `stats['programs']` and
    `stats['rows']` are both about `stats`."""
    out = set()
    for node in ast.walk(test):
        if isinstance(node, ast.Name) and node.id not in _NEUTRAL:
            out.add(node.id)
    return out


def independent(mag_test, shape_test):
    """THE AXIS THAT SEPARATES THE MECHANISM FROM THE COST.

    Every ordered (magnitude, shape) pair is a shadow mechanically: pytest
    stops at the first failure, so the shape assert does not run. But when
    both assertions are about the SAME object -- `assert env.get('result')
    .payload == 15` above another assertion about `env` -- a reader chasing
    the failed count arrives at the shape assertion anyway, because the two
    move together and for the same reason. Nothing is hidden.

    The cost is paid when the two have NO subject in common. Round 494's
    instance is exactly that: `len(rows) == 114` is about `rows`, the
    eleven-class list below is about `rest`, and `rows` moves on every
    corpus addition while `rest` moves only when something genuinely
    unreadable arrives. The count fired six times and each time it took an
    unrelated assertion down with it.

    Reported as a separate population rather than used to filter the
    census, because "these two share a name" is evidence about coupling and
    not proof of it -- two assertions can be independent while both
    mentioning `stats`. Narrowing silently would make the headline
    unfalsifiable; both numbers are published."""
    return not (subjects(mag_test) & subjects(shape_test))


#: pytest builtins. A test that takes only these constructs its own input.
_PYTEST_BUILTINS = frozenset("""
tmp_path tmp_path_factory tmpdir tmpdir_factory capsys capsysbinary
capfd capfdbinary monkeypatch caplog recwarn request pytestconfig
record_property doctest_namespace cache
""".split())

#: Calls whose presence means the function reaches OUTSIDE itself for data.
_TREE_READS = frozenset("""
open listdir glob iglob walk load loads read_text read_bytes
check_output Popen harvest_tests harvest_file census audit survey
scan_tree corpus_paths field_programs
""".split())


def tree_derived(fn):
    """Does this test's data come from the TREE, or does it build its own?

    THE DISTINCTION THIS AXIS EXISTS FOR. A magnitude assert placed first
    as a PRECONDITION is legitimate and common:

        assert sa["nonconstant_programs"] == 1      # the arrangement is
        assert sa["programs"] >= 1                  # only interesting if...
        ... three assertions that are the point ...

    is round 494's own `test_a_compensating_move_is_invisible_to_a_total_
    and_visible_to_the_ledger`, and its `1` is over a `tmp_path` fixture the
    test WRITES three lines earlier. That number cannot drift: nothing but a
    change to the census itself can move it, and such a change is what the
    whole node is about. Reordering it would be a regression -- a failed
    precondition gives a better report than a confusing downstream failure.

    The defect is the SAME shape over data the test does not own. Round
    494's `len(rows) == 114` counted the whole `tests/` corpus, and the
    corpus grows every round for reasons that have nothing to do with the
    node. `assert len(ran) == 5` counts the FIELD corpus, which belongs to
    a separate system entirely.

    A HEURISTIC, and reported as one. `True` when the function takes a
    non-builtin fixture parameter, or calls anything in `_TREE_READS`.
    Both directions can be wrong: a session fixture may hand over a
    constructed object, and a test may reach the tree through a helper this
    misses. It narrows the population to read first; it does not filter the
    census, which publishes every pair either way."""
    params = [a.arg for a in fn.args.args + fn.args.kwonlyargs
              if a.arg != "self"]
    if any(p not in _PYTEST_BUILTINS for p in params):
        return True
    if params:
        # Every parameter is a pytest builtin, so the test is HANDED a
        # scratch area and writes its own input into it. Round 494's
        # `test_a_compensating_move...(tmp_path)` calls `harvest_tests` on
        # that scratch area, and counting that as a tree read flagged the
        # one node in the census whose count provably cannot drift. The
        # short-circuit is here, ahead of the call scan, for that case.
        return False
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else \
                f.attr if isinstance(f, ast.Attribute) else None
            if name in _TREE_READS:
                return True
    return False


def _assigned_between(fn, lo, hi):
    """Names bound anywhere in `fn` on a line strictly between `lo` and `hi`.

    THE CHECK THAT MAKES `reorder` SAFE TO ACT ON. `test_v10.py::
    test_ref_diff_same_on_identical_copy_and_diff_on_sabotage` runs a
    subprocess, asserts `r.returncode == 0`, runs a SECOND subprocess into
    the same `r`, and asserts about it further down. Moving the first
    assertion below the second binding would silently re-point it at the
    other run and the test would still pass -- the worst possible outcome
    for a cleanup. Any rebinding in the window refuses the reorder."""
    out = set()
    for node in ast.walk(fn):
        if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign,
                                 ast.For, ast.AsyncFor, ast.With,
                                 ast.AsyncWith, ast.NamedExpr)):
            continue
        if not (lo < getattr(node, "lineno", 0) < hi):
            continue
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
            targets = [node.target]
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            targets = [node.target]
        else:
            targets = [i.optional_vars for i in node.items if i.optional_vars]
        for t in targets:
            for sub in ast.walk(t):
                if isinstance(sub, ast.Name):
                    out.add(sub.id)
    return out


def _guards_a_subscript(mag_test, shape_test):
    """Does the shape assertion index into something the count pins?

    `assert len(zips) == 1` above `assert (zips[0]["file"], ...) == (...)`
    is a GUARD: reorder it and an empty `zips` raises `IndexError` instead
    of failing an assertion. But `assert stats["programs"] >= 829` above
    that same line is NOT a guard -- it is about `stats` and says nothing
    about `zips`, and moving it down is free.

    The first version of this check refused BOTH, because it only asked
    whether the shape assertion contained an integer subscript. Asking
    WHOSE subscript is what makes the answer useful."""
    mine = subjects(mag_test)
    for node in ast.walk(shape_test):
        if not (isinstance(node, ast.Subscript) and _int_literal(node.slice)):
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Name) and sub.id in mine:
                return True
    return False


def reorder_safe(fn, mag, shape):
    """Can the magnitude assert simply be moved BELOW the shape assert?

    The cheapest remedy for a shadow is a one-line move: let the assertion
    that carries composition run first and the count fire after it. It costs
    no duplicated setup and no new node id -- which matters, because a new
    node id has no episode history in `harness/redattrib.py` and a split
    node reads as `NEW` the first time it goes red.

    Three refusals, each of which was a wrong answer this module gave
    before it was measured against the actual tree:

      * the shape assertion indexes something the count guards
        (`_guards_a_subscript`);
      * a name the count is about is REBOUND in between
        (`_assigned_between`) -- silent mis-pointing, the worst outcome;
      * the two asserts are at different nesting. Same `try:` body, same
        `for:` body is fine; lifting an assert out of a loop is not.
        Compared by slot chain rather than by a `conditional` flag, because
        both asserts being inside one `try` block made the first version
        refuse `test_v48.py`'s reorder for no reason."""
    if mag["_chain"] != shape["_chain"]:
        return False
    if _guards_a_subscript(mag["_test"], shape["_test"]):
        return False
    if subjects(mag["_test"]) & _assigned_between(
            fn, mag["lineno"], shape["lineno"]):
        return False
    return True


def classify(test):
    """One label per assert. Magnitude wins over shape when both fire,
    which happens only for `len(x) == 0`-style tests written against a
    display; there are none in this tree and the tie-break is recorded so
    that if one arrives it is not silently double-counted."""
    if is_magnitude(test):
        return "magnitude"
    if is_shape(test):
        return "shape"
    if is_shape_empty(test):
        return "shape_empty"
    return "other"


# ---------------------------------------------------------------------------
# execution order and branch compatibility
# ---------------------------------------------------------------------------

def _slots(tree, fn):
    """Map every `ast.Assert` inside `fn` to its chain of enclosing
    (block-id, field) slots, stopping at `fn` itself.

    Two asserts can shadow only if neither's chain contradicts the other's
    at a shared depth -- `if: assert A` / `else: assert B` share the `If`
    but differ in field, and B is never reached after A. Without this the
    sweep reports pairs that cannot occur, and an instrument that
    over-reports is one nobody reads."""
    out = {}

    def walk(node, chain):
        for field, value in ast.iter_fields(node):
            if not isinstance(value, list):
                continue
            for child in value:
                # ExceptHandler is not an `ast.stmt`, so without it every
                # assert inside an `except:` block is invisible to the sweep.
                if not isinstance(child, (ast.stmt, ast.ExceptHandler)):
                    continue
                sub = chain if node is fn else \
                    chain + [(id(node), field, type(node).__name__)]
                if isinstance(child, ast.Assert):
                    out[id(child)] = (child, sub)
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef)):
                    # a nested def's asserts belong to the nested def; it may
                    # be called from anywhere, so its order is not this
                    # function's order.
                    continue
                walk(child, sub)

    walk(fn, [])
    return out


def _compatible(a, b):
    """`True` when two slot chains do not diverge into different branches."""
    for (na, fa, _ta), (nb, fb, _tb) in zip(a, b):
        if na != nb:
            return True          # different blocks entirely: sequential
        if fa != fb:
            return False         # same block, different arm
    return True


def _conditional(chain):
    """`True` when the assert sits under any conditionally-reached block --
    an `if`/`for`/`while`/`try`, but not a `with`, which always runs its
    body. A conditional shadow fires only when its branch is taken, so it
    is reported apart from the headline rather than folded into it."""
    cond = set(c.__name__ for c in _COND) | {"ExceptHandler"}
    return any(t in cond for _n, _f, t in chain)


def _scan_function(tree, fn, path):
    """The ordered assert record for one function, plus its shadow pairs."""
    slots = _slots(tree, fn)

    records = []
    for node, chain in slots.values():
        records.append({
            "lineno": node.lineno,
            "col": node.col_offset,
            "kind": classify(node.test),
            "strict": is_magnitude_strict(node.test),
            "text": ast.unparse(node.test),
            "conditional": _conditional(chain),
            "_chain": chain,
            "_test": node.test,
        })
    records.sort(key=lambda r: (r["lineno"], r["col"]))

    pairs = []
    for i, mag in enumerate(records):
        if mag["kind"] != "magnitude":
            continue
        for shape in records[i + 1:]:
            if shape["kind"] != "shape":
                continue
            if not _compatible(mag["_chain"], shape["_chain"]):
                continue
            implied = count_implied(mag["_test"], shape["_test"])
            indep = independent(mag["_test"], shape["_test"])
            reord = reorder_safe(fn, mag, shape)
            if implied:
                remedy = "delete_count"
            elif reord:
                remedy = "reorder"
            else:
                remedy = "split"
            pairs.append({
                "magnitude_line": mag["lineno"],
                "magnitude": mag["text"],
                "magnitude_strict": mag["strict"],
                "magnitude_conditional": mag["conditional"],
                "shape_line": shape["lineno"],
                "shape": shape["text"],
                "count_implied": implied,
                "independent": indep,
                "shared_subjects": sorted(subjects(mag["_test"])
                                          & subjects(shape["_test"])),
                "reorder_safe": reord,
                "remedy": remedy,
            })

    for r in records:
        del r["_chain"]
        del r["_test"]
    return records, pairs


def scan_file(path):
    """Every `test_`-named function in one file, with its shadow pairs."""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src, filename=path)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        records, pairs = _scan_function(tree, node, path)
        derived = tree_derived(node)
        for p in pairs:
            p["tree_derived"] = derived
        out.append({
            "file": os.path.basename(path),
            "func": node.name,
            "lineno": node.lineno,
            "tree_derived": derived,
            "asserts": records,
            "pairs": pairs,
        })
    out.sort(key=lambda f: (f["file"], f["lineno"]))
    return out


def scan_tree(directory=None):
    """Every test function in `tests/`, sorted, deterministic."""
    directory = TESTS if directory is None else directory
    out = []
    for name in sorted(os.listdir(directory)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        out.extend(scan_file(os.path.join(directory, name)))
    return out


# ---------------------------------------------------------------------------
# realised vs latent: what git says about a magnitude literal
# ---------------------------------------------------------------------------

def _ints(text):
    """The integer literals in a source line, as written."""
    out, cur = [], ""
    for ch in text:
        if ch.isdigit():
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def _skeleton(text):
    """A source line with every digit removed and whitespace collapsed.

    Two forms of one assertion that differ ONLY in their integer literals
    have the same skeleton. This is what separates a RE-PIN -- somebody
    typed a new number into an assertion that was otherwise left alone --
    from a REWRITE, where `git log -L` matched a moving line range across a
    block that was replaced wholesale and the "before" text is a different
    assertion entirely.

    Measured round 498: of the 7 pairs whose literal changed, 4 are
    rewrites of this kind (`dbaf51ba` replaced three whole test bodies,
    `5969dede` replaced `set(guest[0]) and len(guest[0]) == 3` with
    `len(guest[0]) == 4`). Counting those as shadows firing would have
    inflated the one field this module exists to make trustworthy, so the
    headline uses `repins` and reports `literal_edits` beside it."""
    return " ".join("".join(c for c in text if not c.isdigit()).split())


def line_history(path, lineno, root=None, cwd=None):
    """How many commits CHANGED the integer literal on this one line.

    `git log -L <n>,<n>:<file>` follows the line back through history and
    prints one hunk per commit that touched it. A commit counts here only
    when the removed and added forms of the line differ in their integer
    literals -- a reindent, a message change or a rename moves the line
    without re-pinning the number, and calling those "the shadow fired"
    would inflate exactly the field this module exists to make trustworthy.

    `repins` is the strictly stronger half: the same edit, PLUS identical
    skeletons, so the assertion was left alone and only the number moved.
    That is a shadow that provably fired -- on the round it fired,
    everything below it in its node went unevaluated.

    TWO LIMITS, both stated because neither is fixable here:

      * UNDER-count. A round that re-pins by deleting and re-adding the
        whole function reads to `-L` as a CREATION, not an edit. Round 494
        did exactly that to the node it fixed, so that node's six known
        firings are invisible to this measure.
      * The measure is per LINE, and a line's history begins where `-L`
        stops tracing it. It is a floor on how often a shadow has fired,
        never a ceiling.

    Returns `(literal_edits, commits_touching, repins, [(sha, kind, before,
    after)])`."""
    cwd = cwd or os.path.dirname(os.path.abspath(path))
    rel = os.path.relpath(os.path.abspath(path), cwd)
    try:
        raw = subprocess.run(
            ["git", "log", "--format=%s%%H" % _COMMIT_MARK, "-L",
             "%d,%d:%s" % (lineno, lineno, rel)],
            cwd=cwd, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None, None, []

    edits, touched, repins, moves = 0, 0, 0, []
    state = {"sha": None, "removed": [], "added": []}

    def flush():
        nonlocal edits, touched, repins
        if state["sha"] is None:
            return
        touched += 1
        removed, added = state["removed"], state["added"]
        # A commit that only ADDS the line is the commit that WROTE it, not
        # one that re-pinned it. A commit that only removes it deleted the
        # line. Neither is a shadow firing.
        if not (removed and added):
            return
        before, after = " ".join(removed).strip(), " ".join(added).strip()
        if _ints(before) == _ints(after):
            return
        edits += 1
        kind = "repin" if _skeleton(before) == _skeleton(after) else "rewrite"
        if kind == "repin":
            repins += 1
        moves.append((state["sha"][:8], kind, before, after))

    for line in raw.splitlines():
        if line.startswith(_COMMIT_MARK):
            flush()
            state = {"sha": line[len(_COMMIT_MARK):].strip(),
                     "removed": [], "added": []}
        elif line.startswith("---") or line.startswith("+++"):
            continue                      # diff file headers
        elif line.startswith("-"):
            state["removed"].append(line[1:])
        elif line.startswith("+"):
            state["added"].append(line[1:])
    flush()
    return edits, touched, repins, moves


def add_history(funcs, directory=None, root=None):
    """Attach `literal_edits` to every shadow pair, in place.

    One `git log -L` per DISTINCT (file, line): several pairs commonly share
    one magnitude assert, and paying for each of them separately is the
    difference between a sweep that runs in a round and one that does not."""
    directory = TESTS if directory is None else directory
    cache = {}
    for f in funcs:
        for p in f["pairs"]:
            key = (f["file"], p["magnitude_line"])
            if key not in cache:
                cache[key] = line_history(
                    os.path.join(directory, f["file"]), p["magnitude_line"])
            edits, touched, repins, moves = cache[key]
            p["literal_edits"] = edits
            p["commits_touching"] = touched
            p["repins"] = repins
            p["moves"] = [{"sha": s, "kind": k, "before": b, "after": a}
                          for s, k, b, a in moves]
    return funcs


# ---------------------------------------------------------------------------
# the census
# ---------------------------------------------------------------------------

def candidates(funcs):
    """The test functions that hold at least one shadow pair."""
    return [f for f in funcs if f["pairs"]]


def totals(funcs):
    """The headline numbers. Every one of them is a SUM over `funcs`, so a
    reader can re-derive any of them from the rows without trusting this."""
    cands = candidates(funcs)
    kinds = {}
    for f in funcs:
        for a in f["asserts"]:
            kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    shadowed_shapes = set()
    strict_pairs = 0
    cond_pairs = 0
    implied_pairs = 0
    indep_pairs = 0
    remedies = {}
    costly = 0
    repins = 0
    edits = 0
    scored = 0
    for f in cands:
        for p in f["pairs"]:
            shadowed_shapes.add((f["file"], p["shape_line"]))
            strict_pairs += 1 if p["magnitude_strict"] else 0
            cond_pairs += 1 if p["magnitude_conditional"] else 0
            implied_pairs += 1 if p["count_implied"] else 0
            indep_pairs += 1 if p["independent"] else 0
            remedies[p["remedy"]] = remedies.get(p["remedy"], 0) + 1
            if p["independent"] and p["tree_derived"]:
                costly += 1
            if "repins" in p:
                scored += 1
                repins += p["repins"] or 0
                edits += p["literal_edits"] or 0
    hist = {}
    if scored:
        hist = {"pairs_with_history": scored,
                "literal_edits": edits,
                "repins": repins,
                "pairs_with_a_repin": sum(
                    1 for f in cands for p in f["pairs"] if p.get("repins"))}
    return dict({
        "files": len(set(f["file"] for f in funcs)),
        "test_functions": len(funcs),
        "asserts": sum(len(f["asserts"]) for f in funcs),
        "assert_kinds": kinds,
        "functions_with_magnitude": sum(
            1 for f in funcs
            if any(a["kind"] == "magnitude" for a in f["asserts"])),
        "functions_with_shape": sum(
            1 for f in funcs
            if any(a["kind"] == "shape" for a in f["asserts"])),
        "candidates": len(cands),
        "pairs": sum(len(f["pairs"]) for f in cands),
        "pairs_strict": strict_pairs,
        "pairs_widened_only": sum(len(f["pairs"]) for f in cands) - strict_pairs,
        "pairs_conditional": cond_pairs,
        "pairs_count_implied": implied_pairs,
        "remedies": remedies,
        "pairs_costly": costly,
        "candidates_costly": sum(
            1 for f in cands
            if any(p["independent"] and p["tree_derived"] for p in f["pairs"])),
        "pairs_independent": indep_pairs,
        "candidates_independent": sum(
            1 for f in cands if any(p["independent"] for p in f["pairs"])),
        "shadowed_shape_asserts": len(shadowed_shapes),
    }, **hist)


def by_file(funcs):
    """Candidate count per file, descending, ties broken by name."""
    counts = {}
    for f in candidates(funcs):
        counts[f["file"]] = counts.get(f["file"], 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def costly_ids(funcs):
    """`file::func` for candidates holding at least one INDEPENDENT and
    TREE-DERIVED pair -- the population that provably costs something."""
    return sorted("%s::%s" % (f["file"], f["func"])
                  for f in candidates(funcs)
                  if any(p["independent"] and p["tree_derived"]
                         for p in f["pairs"]))


def node_ids(funcs):
    """`file::func` for every candidate -- the SHAPE of the census, and the
    thing the ledger check compares. A count can be equal while the set has
    moved; the set cannot."""
    return sorted("%s::%s" % (f["file"], f["func"]) for f in candidates(funcs))


def census_path():
    """`state/whence/assert-shadow-census.json`, resolved LAZILY through
    `curecheck.AGI_ROOT` and never at import time -- `depthcensus.
    contributions_path`'s two pitfalls, which are curecheck's round-413
    notes: a sixth `__file__`-derived root blocks mutation campaigns, and a
    `state/` read at import aborts COLLECTION of the whole suite."""
    import curecheck                                   # noqa: PLC0415
    return os.path.join(curecheck.AGI_ROOT, "state", "whence",
                        "assert-shadow-census.json")


def load_census(path=None):
    """The declared census. Raises when absent: an instrument that silently
    answered about an empty ledger would report every node as NEW."""
    path = census_path() if path is None else path
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_census(declared, funcs):
    """`(missing, extra)` -- declared-but-gone, and live-but-undeclared.

    Set difference, not a count comparison, on purpose: this module exists
    because a count assertion hid a set."""
    live = set(node_ids(funcs))
    old = set(declared.get("nodes", {}))
    return sorted(old - live), sorted(live - old)


def check_coordinates(declared, funcs):
    """Declared pairs whose LINE NUMBERS no longer point at the assertion.

    ROUND 500's FINDING, and it is this module's own lesson arriving one
    level up. Round 498 built `assertshadow` because a COUNT assertion was
    standing in front of a LIST assertion, and then wrote this module's
    ledger gate to compare only the list: `check_census` diffs the node-id
    SET, `check_costly` diffs the costly SET, and neither one looks at the
    coordinates inside a node. So a node can keep its id, its pair count,
    its assertion text and every published total while the line numbers
    recorded against it drift to point at nothing.

    That is not hypothetical. At round 500 the ledger committed by round
    498 carried FIVE pairs across FOUR `test_testcorpus_census.py` nodes at
    a uniform +9 offset, with identical assertion text -- and the file is
    byte-identical to the version in round 498's own commit. The census was
    generated, nine lines were then inserted above line 1634, and the two
    were committed together. `--check` said "ledger agrees" throughout,
    because every set it compares really was unchanged, and so did
    `check_costly` and every published total.

    Round 494 already found this shape once, in the other direction: it
    WIDENED a residual-row location pin, and that pin's first live firing
    caught round 498's own reorder. This is the same pin one level up, at
    the pair coordinate rather than the residual row.

    Returns `[(node_id, declared_mag, declared_shape, live_mag,
    live_shape)]`, matched on ASSERTION TEXT rather than on position in the
    pair list: a node whose pairs were re-ordered by an insertion is not
    the same event as a pair that moved, and matching by index would report
    both as the second."""
    live = dict(("%s::%s" % (f["file"], f["func"]), f["pairs"])
                for f in funcs)
    out = []
    for nid, node in sorted(declared.get("nodes", {}).items()):
        got = live.get(nid)
        if got is None:
            continue          # `check_census` owns declared-but-gone nodes
        for p in node["pairs"]:
            same_text = [g for g in got
                         if g["magnitude"] == p["magnitude"]
                         and g["shape"] == p["shape"]]
            if not same_text:
                continue      # the assertion itself changed, not its place
            if any(g["magnitude_line"] == p["magnitude_line"]
                   and g["shape_line"] == p["shape_line"]
                   for g in same_text):
                continue
            g = same_text[0]
            out.append((nid, p["magnitude_line"], p["shape_line"],
                        g["magnitude_line"], g["shape_line"]))
    return out


def check_costly(declared, funcs):
    """`(missing, extra)` over the COSTLY set alone -- the hard gate."""
    live = set(costly_ids(funcs))
    old = set(declared.get("costly_nodes", []))
    return sorted(old - live), sorted(live - old)


def _residual(declared, funcs):
    """Top-level keys of the census that no finding above ranges over.

    THE PREDICATE THAT IS TOTAL BY CONSTRUCTION, and round 512's rule
    applied to its own next-step #6: `build_census` is a pure function of
    `funcs`, so "the document I would write now" is the only comparison
    that cannot fall behind the document.

    Two exclusions, both named rather than silent. `nodes` and
    `costly_nodes` are excluded because `check_census`, `check_coordinates`
    and `check_costly` already report them in a form a reader can act on --
    a whole-key diff of 38 nodes is not. And the census is rebuilt with the
    SAME `history` shape as the declared document, because `--history` runs
    `git log -L` per pair: rebuilding without it would report `_history` as
    a spurious drift on every check, which is how a total gate earns the
    reputation that gets it deleted."""
    import checkscope                                  # noqa: PLC0415
    live = build_census(funcs, history="_history" in declared)
    #: Totals that only exist once `add_history` has run `git log -L` over
    #: every pair. `--check` deliberately does not, so they are dropped
    #: from BOTH sides rather than reported as drift -- found by
    #: `test_the_cli_check_exits_zero_on_this_tree` going red on the first
    #: run of the total residual, which is the failure mode the docstring
    #: above predicts and the reason the exclusions are named out loud.
    hist = ("literal_edits", "pairs_with_history", "repins",
            "pairs_with_a_repin")
    if not any(f.get("pairs") and "literal_edits" in f["pairs"][0]
               for f in funcs if f.get("pairs")):
        declared = dict(declared)
        declared["totals"] = dict((k, v) for k, v in
                                  declared.get("totals", {}).items()
                                  if k not in hist)
        live["totals"] = dict((k, v) for k, v in live["totals"].items()
                              if k not in hist)
    return checkscope.document_diff(declared, live,
                                    ignore=("nodes", "costly_nodes"))


def build_census(funcs, history=False):
    nodes = {}
    for f in candidates(funcs):
        nodes["%s::%s" % (f["file"], f["func"])] = {
            "lineno": f["lineno"],
            "pairs": f["pairs"],
        }
    out = {
        "_what": "test nodes in languages/whence/tests/ where a magnitude "
                 "assert precedes a shape assert in the same execution path "
                 "-- round 494's next-step #1, measured by round 498.",
        "_regenerate": "cd languages/whence && python3 assertshadow.py "
                       "--history --json <this file>",
        "_headline_predicate": "is_magnitude (widened) x is_shape "
                               "(non-empty display), branch-compatible, "
                               "magnitude strictly first",
        "totals": totals(funcs),
        "by_file": [{"file": k, "candidates": v} for k, v in by_file(funcs)],
        "costly_nodes": costly_ids(funcs),
        "nodes": nodes,
    }
    if history:
        out["_history"] = ("literal_edits = commits in which the integer "
                           "literal on the magnitude line CHANGED, per "
                           "`git log -L`. A realised shadow, not a possible "
                           "one.")
    return out


def render(funcs, history=False, limit=None):
    t = totals(funcs)
    L = []
    L.append("assert-shadow census -- languages/whence/tests/")
    L.append("  %d files, %d test functions, %d asserts"
             % (t["files"], t["test_functions"], t["asserts"]))
    L.append("  kinds: " + ", ".join(
        "%s %d" % (k, t["assert_kinds"][k]) for k in sorted(t["assert_kinds"])))
    L.append("  functions with a magnitude assert: %d;  with a shape assert: %d"
             % (t["functions_with_magnitude"], t["functions_with_shape"]))
    L.append("  SHADOW CANDIDATES: %d functions, %d pairs "
             "(%d strict / %d widened-only, %d conditional)"
             % (t["candidates"], t["pairs"], t["pairs_strict"],
                t["pairs_widened_only"], t["pairs_conditional"]))
    L.append("  shape asserts made conditionally unreachable: %d"
             % t["shadowed_shape_asserts"])
    L.append("  INDEPENDENT (no shared subject -- the shape assert's "
             "information is lost): %d pairs in %d nodes"
             % (t["pairs_independent"], t["candidates_independent"]))
    L.append("  COSTLY (independent AND tree-derived -- the count moves "
             "for reasons the shape assert is not about): %d pairs in %d "
             "nodes" % (t["pairs_costly"], t["candidates_costly"]))
    L.append("  remedy: " + ", ".join(
        "%s %d" % (k, t["remedies"][k]) for k in sorted(t["remedies"])))
    if "repins" in t:
        L.append("  REALISED: %d pair(s) whose literal was re-pinned "
                 "(%d re-pins, %d literal edits incl. block rewrites)"
                 % (t["pairs_with_a_repin"], t["repins"], t["literal_edits"]))
    L.append("")
    L.append("by file:")
    for name, n in by_file(funcs):
        L.append("  %-42s %d" % (name, n))
    L.append("")
    rows = []
    for f in candidates(funcs):
        worst = max((p.get("repins") or 0) for p in f["pairs"]) \
            if history else 0
        rows.append((worst, f))
    rows.sort(key=lambda r: (-r[0], r[1]["file"], r[1]["lineno"]))
    L.append("candidates%s:" % (" (by realised shadow, descending)"
                                if history else ""))
    for worst, f in rows[:limit]:
        head = "  %s::%s" % (f["file"], f["func"])
        if history:
            head += "   repins=%d" % worst
        L.append(head)
        for p in f["pairs"]:
            L.append("      L%-5d %-40s  shadows L%-5d [%s%s]"
                     % (p["magnitude_line"], p["magnitude"][:40],
                        p["shape_line"], p["remedy"],
                        " INDEP" if p["independent"] else ""))
    return "\n".join(L)


def main(argv):
    args = list(argv)
    history = "--history" in args
    check = "--check" in args
    limit = None
    out_json = None
    if "--json" in args:
        out_json = args[args.index("--json") + 1]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    directory = TESTS
    if "--tests" in args:
        directory = args[args.index("--tests") + 1]
    # Round 516 (language C): see `subjprov.main` -- a `--check` that can
    # only read its own hardcoded path cannot be run against a mutant
    # without endangering the artefact, and so was never measured.
    census_file = (args[args.index("--census") + 1]
                   if "--census" in args else None)

    funcs = scan_tree(directory)
    if history:
        add_history(funcs, directory)

    if check:
        try:
            declared = load_census(census_file)
        except FileNotFoundError:
            print("no census on disk: %s"
                  % (census_file or census_path()))
            return 1
        missing, extra = check_census(declared, funcs)
        # `check_costly` existed from round 498 and was exercised only by
        # `test_assertshadow.py`; the CLI -- the path every failure message
        # names as the way to check -- never called it. A gate reachable
        # only from a test is a gate the author of a change does not run.
        cmiss, cextra = check_costly(declared, funcs)
        moved = check_coordinates(declared, funcs)
        # ROUND 516: everything above ranges over `nodes` and
        # `costly_nodes`. `checkscope.py --scope` mutated this census one
        # top-level key at a time and pointed this very verb at each
        # mutant: it saw 2 of the 8 keys. The census's OWN HEADLINE --
        # `totals`, the three numbers the CLI prints and a reader quotes --
        # was one of the six it could not see, and round 512 found those
        # numbers had drifted 72 -> 76 files, 1935 -> 2029 test functions
        # and 3908 -> 4122 asserts while this line printed "ledger agrees".
        # The residual is not a seventh bespoke comparison: it is the
        # document this run would write, diffed against the one on disk.
        residual = _residual(declared, funcs)
        if not (missing or extra or cmiss or cextra or moved or residual):
            print("assert-shadow census: %d candidate node(s), ledger agrees"
                  % totals(funcs)["candidates"])
            return 0
        for n in missing:
            print("GONE     %s  (declared, no longer a candidate)" % n)
        for n in extra:
            print("NEW      %s  (a shadow this tree did not have)" % n)
        for n in cmiss:
            print("UNCOSTLY %s  (declared costly, no longer is)" % n)
        for n in cextra:
            print("COSTLY   %s  (newly costly, not declared)" % n)
        for nid, dm, ds, lm, ls in moved:
            print("MOVED    %s  ledger %d/%d -> tree %d/%d"
                  % (nid, dm, ds, lm, ls))
        for key, why in residual:
            print("DRIFT    %-20s %s" % (key, why))
        if residual:
            print("         (`nodes` is compared as a set and by "
                  "coordinate above; its per-pair `literal_edits` need "
                  "--history and are NOT compared here)")
        print("regenerate: cd languages/whence && python3 assertshadow.py "
              "--history --json <census>")
        return 1

    print(render(funcs, history=history, limit=limit))
    if out_json:
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump(build_census(funcs, history=history), fh, indent=2,
                      sort_keys=False)
            fh.write("\n")
        print("\nwrote %s" % out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
