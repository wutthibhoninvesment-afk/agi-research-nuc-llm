"""v0.22 (round 354, language C) — a wrong-argument miss names the CALL
that would have worked.

Where this comes from. Round 349 answered an operator bug report against
v0.19 — "`fold()` returns Miss instead of calculated values when using
inline lambdas or external functions" — and found it was a documentation
gap, not a code defect: the report's call was `fold(nums, 0, fn(acc, x)
{...})`, Whence's higher-order builtins take the FUNCTION FIRST, and
SPEC.md's `## Builtins` section was a bare list of 36 names that gave the
argument order for none of them. Round 349 wrote the signature table and
pinned it (`tests/test_spec_builtins.py`).

v0.22 closes the other half — the half that is the LANGUAGE's job rather
than the document's. The interpreter's miss was already exact about the
symptom (`fold needs a list, got <fn>`) and still left the reader to
discover the cure by reading `whence/interp.py`. Decision 30 (v0.20) made
a type miss name the FIELD that broke it; decision 32 makes an argument
miss name the SIGNATURE that fits.

What is pinned here that nothing else pins:

  * the exact hint TEXT for every builtin family that can produce one, in
    all three host evaluation modes;
  * the three SILENCES, which are the load-bearing half — a hint that
    appears where reordering would not help is worse than no hint, because
    a reader trusts it;
  * host-vs-guest wording for the four builtins `self_eval.lang`
    re-implements. The ordinary corpus differential
    (`test_self_eval.py::test_differential_host_vs_guest`) compares
    payloads and EXEMPTS miss reasons (round 17), so a guest emitting no
    hint at all — or a different one — would still rate "agree". That
    exemption is what hid round 326's anonymous-fn label bug and round
    338's six-errors-one-message bug.
"""

import os
import re

import pytest

from whence.interp import Interpreter
from whence.values import Miss

from test_v20 import guest_eval_all, reason  # same helpers, same rationale

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Round 404 (v0.38): a tenth copy of the `(line N)` normaliser lived here
# and was DEAD -- this module imports `reason` from `test_v20` and never
# used its own. It was unanchored, like eight of the other nine, and a
# dead unanchored normaliser is a trap for whoever reaches for it next, so
# it is deleted rather than fixed. `bench/sanitisers.py` is what found it.
HINT_RE = re.compile(r" \(arguments fit [a-z_]+\([^)]*\)\)$")


def host_modes(src):
    """(generator, no-fast-path, default) — every site that can raise one
    of these misses, reached by all three evaluation strategies."""
    return tuple(Interpreter(**kw).run(src).get("result")
                 for kw in ({"fast": False}, {"direct": False}, {}))


def host_reason(src):
    rs = [reason(v) for v in host_modes(src)]
    assert len(set(rs)) == 1, ("host modes disagree", src, rs)
    return rs[0]


# --- the hint, by exact text -------------------------------------------------

NUMS = "let nums = [1, 2, 3]\n"

HINT_CASES = [
    # (source, exact expected reason with the line stripped)

    # the operator's own call, both spellings they named
    (NUMS + "let result = fold(nums, 0, fn(a, x) { a + x })",
     "fold needs a list, got <fn> (arguments fit fold(fn, acc, xs))"),
    (NUMS + "fn add(a, x) { a + x }\nlet result = fold(nums, 0, add)",
     "fold needs a list, got <fn add> (arguments fit fold(fn, acc, xs))"),
    # a 3-cycle, not just a transposition: seed and list also swapped
    (NUMS + "let result = fold(0, nums, fn(a, x) { a + x })",
     "fold needs a list, got <fn> (arguments fit fold(fn, acc, xs))"),

    # the rest of the fn-first family
    (NUMS + "let result = map(nums, fn(x) { x })",
     "map needs a list, got <fn> (arguments fit map(fn, xs))"),
    (NUMS + "let result = filter(nums, fn(x) { x > 1 })",
     "filter needs a list, got <fn> (arguments fit filter(fn, xs))"),
    (NUMS + "let result = find(nums, fn(x) { x > 1 })",
     "find needs a list, got <fn> (arguments fit find(fn, xs))"),

    # `push` is the one that goes the OTHER way (SPEC's own asymmetry note),
    # so it is the one most worth a hint
    ("let result = push(7, [1, 2])",
     "push needs a list, got 7 (arguments fit push(xs, x))"),

    ("let result = join(\", \", [1, 2])",
     "join needs (list, string) (arguments fit join(xs, sep))"),
    ("let result = note(5, \"hi\")",
     "note label must be a string, got 5 (arguments fit note(label, v))"),
    ("let result = contains(5, \"x\")",
     "contains needs a string or list, got 5 "
     "(arguments fit contains(hay, needle))"),

    # record builtins: r first, then the field name
    ("let result = get(\"a\", @{a: 1})",
     "get field name must be a string, got @{a: 1} "
     "(arguments fit get(r, name))"),
    ("let result = has(\"a\", @{a: 1})",
     "has needs a record, got \"a\" (arguments fit has(r, name))"),
    ("let result = put(\"a\", @{a: 1}, 9)",
     "put needs a record, got \"a\" (arguments fit put(r, name, v))"),

    # AI-native primitives
    ("let result = guess(0.5, \"src\", [1])",
     "guess confidence must be a number between 0 and 1, got \"src\" "
     "(arguments fit guess(value, conf, source))"),
    ("let result = sure(0.5, guess(1, 0.2, \"s\"))",
     "sure threshold must be a number between 0 and 1, got guess 0.2 (s): 1 "
     "(arguments fit sure(v, threshold))"),

    # provenance-as-data
    ("let result = at(\"pat\", [1, 2])",
     "at needs a string step name, got [1, 2] (arguments fit at(v, pat))"),
    ("let result = steps(\"pat\", [1, 2])",
     "steps needs a string step name, got [1, 2] "
     "(arguments fit steps(v, pat))"),

    # `typed`: the only 3-arg builtin whose kinds are loose enough that the
    # hint is reachable only from the LABEL position
    ("let result = typed(\"lbl\", \"num\", @{x: 1})",
     "typed label must be a string, got @{x: 1} "
     "(arguments fit typed(value, spec, label))"),
]


@pytest.mark.parametrize("src,want", HINT_CASES)
def test_hint_text(src, want):
    assert host_reason(src) == want


# --- the three silences ------------------------------------------------------

SILENT_CASES = [
    # 1. the given order already fits the declared kinds, so this miss is
    #    about something the kinds do not model. Pasting an order hint here
    #    would send the reader to reorder a call that is already right.
    (NUMS + "let result = filter(fn(x) { 5 }, nums)",
     "filter predicate must return true/false, got 5"),
    ("let result = guess([1], 5, \"src\")",
     "guess confidence must be a number between 0 and 1, got 5"),
    ("let result = range(1.5, 3)", "range needs integers, got 1.5"),
    # `_spec_ok` is deeper than any `_kind` tag: a record IS an allowed
    # `spec`, this one just is not a well-formed one
    ("let result = typed(\"Point\", @{x: 1}, \"lbl\")",
     "typed spec must be a type name or a shape, got @{x: 1}"),

    # 2. no reordering fits at all
    ("let result = join(\"a\", \"b\")", "join needs (list, string)"),
    ("let result = merge(@{a: 1}, 5)", "merge needs two records"),
    ("let result = map(5, 6)", "map needs a list, got 6"),
    ("let result = fold(1, 2, 3)", "fold needs a list, got 3"),
    # a Guess wrapping the right kind is NOT the right kind (v0.15 is
    # deliberately shallow) — and reordering is not the cure, `sure()` is
    (NUMS + "let result = map(fn(x) { x }, guess(nums, 0.9, \"s\"))",
     "map needs a list, got guess 0.9 (s): [1, 2, 3]"),

    # 3. an ARITY error is a different, already-precise miss
    (NUMS + "let result = fold(nums, 0)", "fold expects 3 args, got 2"),
    (NUMS + "let result = map(fn(x) { x }, nums, 1)",
     "map expects 2 args, got 3"),
]


@pytest.mark.parametrize("src,want", SILENT_CASES)
def test_no_hint_where_reordering_would_not_help(src, want):
    got = host_reason(src)
    assert got == want
    assert HINT_RE.search(got) is None, got


def test_symmetric_signatures_can_never_produce_a_hint():
    """`merge(a, b)` and `diverge`/`contrast` declare interchangeable
    positions on purpose: no reordering can fix a call whose positions mean
    the same thing, so the machinery must stay silent rather than reach for
    a sentence."""
    from whence import interp as I
    for name in ("merge", "diverge", "contrast"):
        kinds = [k for _, k in I._BUILTIN_SIGS[name]]
        assert len(set(map(repr, kinds))) == 1, (name, kinds)


# --- the rule itself, at the unit level --------------------------------------

def test_order_hint_is_existence_not_uniqueness():
    """The design decision recorded in `_order_hint`'s docstring.

    `guess("s", 1, 2)` fits `guess(value, conf, source)` in TWO orders (1
    or 2 can be the confidence). An earlier draft demanded a unique fitting
    order; the advice is the signature, which is the same string either
    way, so uniqueness would have suppressed a true sentence."""
    from whence import interp as I
    sig = I._BUILTIN_SIGS["guess"]
    fits = [p for p in __import__("itertools").permutations(["s", 1, 2])
            if I._sig_fits(sig, list(p))]
    assert len(fits) == 2, fits
    assert host_reason("let result = guess(\"s\", 1, 2)").endswith(
        "(arguments fit guess(value, conf, source))")


def test_every_builtin_declares_a_signature():
    """`register` takes `sig` positionally and required, so this cannot be
    forgotten — but the count is what makes that visible if `register` is
    ever relaxed."""
    from whence import interp as I
    table = I._make_builtin_table()
    # 36 through v0.28; 37 since v0.29 (round 374) added `show`. The number
    # is the point of this assertion — it is here so that relaxing
    # `register` shows up — so it is EDITED when a builtin is added, never
    # loosened to `>=`.
    assert len(table) == 37
    for name, _ in table:
        assert name in I._BUILTIN_SIGS, name


def test_declared_kinds_are_real_kind_tags():
    """A typo in a `sig` string ("lst" for "list") would silently make a
    position unsatisfiable and kill every hint that goes through it — the
    exact failure mode this whole feature exists to avoid."""
    from whence import interp as I
    tags = set(name for _, name in I._KIND_ORDER) | {"value"}
    for name, sig in I._BUILTIN_SIGS.items():
        for pname, kinds in sig:
            assert pname and pname.isidentifier(), (name, pname)
            if kinds is not None:
                for k in kinds:
                    assert k in tags, (name, pname, k, sorted(tags))


def test_the_hint_rides_on_the_reason_and_not_on_the_provenance():
    """v0.20's precedent: the clause is part of the miss's SENTENCE, so it
    reaches `reasons`, `why`, `blame` and a failing `check` with no new
    surface. The provenance INPUTS are unchanged — round 347 put `acc` back
    into `fold`'s miss inputs and this must not undo that."""
    env = Interpreter().run(
        NUMS + "let result = fold(nums, 0, fn(a, x) { a + x })")
    v = env.get("result")
    assert isinstance(v.payload, Miss)
    assert len(v.payload.reasons) == 1
    assert "(arguments fit fold(fn, acc, xs))" in v.payload.reasons[0]
    fold_node = v.inputs[0]     # `result`'s `let` node wraps the fold node
    assert fold_node.op == "fold", fold_node
    assert len(fold_node.inputs) == 3, fold_node.inputs


def test_hint_survives_a_failing_check_report():
    """End-to-end through `run.py`'s check reporting, which is where a
    reader actually meets a miss."""
    import subprocess
    import sys
    prog = os.path.join(ROOT, "run.py")
    src = NUMS + 'check "folds": fold(nums, 0, fn(a, x) { a + x }) == 6\n'
    path = os.path.join(os.path.dirname(prog), "_v22_tmp.lang")
    with open(path, "w") as f:
        f.write(src)
    try:
        out = subprocess.run([sys.executable, prog, path],
                             capture_output=True, text=True)
    finally:
        os.remove(path)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "arguments fit fold(fn, acc, xs)" in out.stdout, out.stdout


# --- host vs guest, by WORDING ----------------------------------------------

GUEST_CASES = [
    NUMS + "let result = fold(nums, 0, fn(a, x) { a + x })",
    NUMS + "fn add(a, x) { a + x }\nlet result = fold(nums, 0, add)",
    NUMS + "let result = fold(0, nums, fn(a, x) { a + x })",
    NUMS + "let result = map(nums, fn(x) { x })",
    NUMS + "let result = filter(nums, fn(x) { x > 1 })",
    NUMS + "let result = find(nums, fn(x) { x > 1 })",
    # and the silences, which are the half a guest is most likely to get
    # wrong by simply not implementing them
    NUMS + "let result = map(5, 6)",
    NUMS + "let result = fold(1, 2, 3)",
    NUMS + "let result = filter(fn(x) { 5 }, nums)",
    NUMS + "let result = map(fn(x) { x }, guess(nums, 0.9, \"s\"))",
    # a guest CLOSURE is a record under the hood: if `guest_kind` classified
    # one as "record" the hint would vanish on this case alone
    NUMS + "let f = fn(a, x) { a + x }\nlet result = fold(nums, 0, f)",
]


@pytest.mark.whence_slow
def test_order_hint_wording_agrees_host_vs_guest():
    guest = guest_eval_all(GUEST_CASES)
    bad = []
    for src, g in zip(GUEST_CASES, guest):
        h = reason(Interpreter().run(src).get("result"))
        if h != reason(g):
            bad.append((src, h, reason(g)))
    assert bad == [], bad


# --- v0.22, the parser half --------------------------------------------------
#
# Same decision, second surface. The operator's v0.19 report had two halves;
# round 349 answered the first with SPEC.md's signature table and the second
# ("the parser requires explicit `{}` blocks ... consider auto-fixing older
# scripts") with SPEC.md's `### Blocks are always braced`. Round 354 measured
# the scripts before deciding whether to auto-fix them: see
# `test_the_ten_machine_written_programs_fail_for_six_reasons` below.

from whence.parser import ParseError, parse   # noqa: E402


def parse_error(src):
    with pytest.raises(ParseError) as ei:
        parse(src)
    return str(ei.value)


PARSE_HINT_CASES = [
    # (source, exact expected message)

    # braces — the operator's own half, at `if`, at `else`, and at a `fn`
    # body, because the rule was never `if`-specific
    ('if x > 3 print("big")\n',
     "expected '{', got 'print' (blocks are always braced: "
     "`if c { a } else { b }`, `fn f(x) { x }`) at line 1, col 10"),
    ('let x = 5\nif x > 3 { 1 }\nelse 2\n',
     "expected '{', got 2 (blocks are always braced: "
     "`if c { a } else { b }`, `fn f(x) { x }`) at line 3, col 6"),
    ('fn f(x) x + 1\n',
     "expected '{', got 'x' (blocks are always braced: "
     "`if c { a } else { b }`, `fn f(x) { x }`) at line 1, col 9"),

    # assignment — decision 3, which has no other way to announce itself
    ('let x = 1\nx = 2\n',
     "unexpected '=' (Whence has no assignment; a name binds once "
     "\u2014 write `let name = value`) at line 2, col 3"),

    # try/catch reaching for a `rescue` block
    ('let d = rescue { f(1) } catch Miss as e { 0 }\n',
     "unexpected 'rescue' (`rescue` is infix: `risky rescue fallback`) "
     "at line 1, col 9"),

    # a record literal missing its `@`. Without the lookahead the error
    # lands on the `:` and says only "unexpected ':'" — the mistake is the
    # brace two tokens earlier.
    ('let r = {a: 1}\n',
     "unexpected ':' (records are written `@{a: 1}`, not `{a: 1}`) "
     "at line 1, col 11"),
    ('let r = [ {name: "a", qty: 2} ]\n',
     "unexpected ':' (records are written `@{a: 1}`, not `{a: 1}`) "
     "at line 1, col 16"),
    ('let r = {\n  a: 1\n}\n',
     "unexpected ':' (records are written `@{a: 1}`, not `{a: 1}`) "
     "at line 2, col 4"),

    # juxtaposition: an unquoted string, inside a call and inside a list —
    # two DIFFERENT expected tokens, one adjacency rule
    ('let x = print(Calculating total)\n',
     "expected ')', got 'total' (two names in a row: Whence has no "
     "juxtaposition \u2014 a call is `f(x)` and text must be quoted) "
     "at line 1, col 27"),
    ('let xs = [Hardware Unit, 2100]\n',
     "expected ']', got 'Unit' (two names in a row: Whence has no "
     "juxtaposition \u2014 a call is `f(x)` and text must be quoted) "
     "at line 1, col 20"),
]


@pytest.mark.parametrize("src,want", PARSE_HINT_CASES)
def test_parse_error_hint_text(src, want):
    assert parse_error(src) == want


def test_shape_is_the_one_legal_name_name_and_draws_no_hint():
    """`shape` is a SOFT keyword — `lexer.KEYWORDS` has 14 words and it is
    not one of them — so `shape Foo` is a legal NAME NAME. If the
    juxtaposition rule did not except it, every malformed `shape` statement
    would be told to quote its own type name."""
    from whence.lexer import tokenize, KEYWORDS
    assert "shape" not in KEYWORDS
    assert [t.type for t in tokenize("shape Foo")][:2] == ["NAME", "NAME"]
    # v0.23 (round 356) moved WHERE this program's error comes from: `shape
    # Foo` is not a shape head (`peek(2)` is `Bar`, not `=`), so `shape` is
    # an expression statement and `Foo` starts a second one on the same
    # line — the missing-separator check now fires first. It inherits this
    # exclusion verbatim (`Parser._separator_hint`), which is the only
    # reason this assertion still holds; dropping `_NAME_INTRODUCERS` there
    # turns this test red.
    msg = parse_error("shape Foo Bar = @{x: num}\nlet r = 1\n")
    assert "juxtaposition" not in msg, msg
    assert msg.startswith("two statements on one line "), msg
    # and a well-formed shape still parses
    parse("shape Foo = @{x: num}\nlet r = 1\n")


def test_hints_are_additive_and_never_replace_the_diagnosis():
    """Every hint is a suffix on the message the parser already produced.
    Round 349's own `test_if_branches_require_braces_and_the_parser_says_so`
    asserts `"expected '{'" in str(...)`, and callers like it must keep
    working."""
    for src, want in PARSE_HINT_CASES:
        head = want.split(" (")[0]
        assert parse_error(src).startswith(head), (src, head)


def test_parse_error_wording_is_not_a_guest_contract():
    """Why the parser half needs no `self_host.lang` mirror, established
    rather than assumed.

    ROUND 354 wrote this and asserted `"col" in host and "col" not in
    guest`: host parse errors were exceptions carrying line AND column,
    guest parse errors were `miss` values carrying a line only, and the two
    had never used the same words, so adding a v0.22 hint to one could not
    create a divergence where there was never an agreement. It ended: "If a
    future round makes them agree, this test is the one that should go red
    first."

    ROUND 360 made HALF of them agree, and this test went red first,
    exactly there — `"col" not in guest` is now false. v0.24's decision 34
    splits the claim in two: a POSITION is a fact about the program and is
    now a contract (`tests/test_parse_error_differential.py`, 43 malformed
    programs, both sides refusing at the same line and column); WORDING is
    still a choice and is still not a contract. The test keeps its name
    because its name is about the half that did not change, and it now
    pins BOTH halves on the same example round 354 chose, so the sentence
    above stays checkable rather than becoming a story about a deleted
    assertion.

    ROUND 398 went red here a SECOND time, for the same good reason, and
    the assertion it broke was the one this test had left as its proof
    that the wordings differ: `"unexpected token" in guest`. v0.36's
    decision 45 gave the guest the host's `_show` and, with it, the host's
    `unexpected X` spelling, so the two now write this sentence
    identically apart from the hint. Rule 3 is unchanged and is NOT
    becoming a contract --- 20 of the corpus's 54 refusals still differ
    (`test_parse_error_differential.py::test_every_remaining_divergence_
    is_a_hint_or_the_rebind_sentence`), 18 of them by exactly the hint
    this test is about. What is pinned here now is the ONE fact the v0.22
    hint needs: strip the host's parenthetical and the two sentences are
    equal, so a hint is additive and cannot silently change the diagnosis
    underneath it.
    """
    src = 'let x = 1\nx = 2\n'
    host = parse_error(src)
    lib = open(os.path.join(ROOT, "examples", "self_host.lang")).read()
    lib = lib.split("# ==== SELF-TESTS")[0]
    esc = src.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    env = Interpreter().run(lib + 'let out = str(parse_whence("%s"))\n' % esc)
    guest = env.get("out").payload
    # v0.24: the position agrees, down to the column round 354 recorded.
    assert "at line 2, col 3" in host, host
    assert "at line 2, col 3" in guest, guest
    # v0.22's hint is host-only. v0.36: the rest of the sentence is not.
    assert "Whence has no assignment" in host and "Whence has no" not in guest
    assert "unexpected token" not in guest and "unexpected token" not in host
    assert host != guest
    # The hint is ADDITIVE: host minus its parenthetical is the guest's
    # sentence, character for character (after the guest's `(line N)`
    # implementation coordinate, which is a separate debt -- see
    # `test_parse_error_differential.py::test_every_guest_parse_error_
    # still_leaks_an_implementation_coordinate`).
    bare = re.sub(r" \(Whence has no assignment[^)]*\)", "", host.strip())
    assert bare == "unexpected '=' at line 2, col 3", bare
    assert re.sub(r" \(line \d+\)$", "", guest.strip()) == "miss: " + bare


# --- the measurement that decided against auto-fixing ------------------------

MACHINE_WRITTEN = [
    # One line lifted from each of the ten machine-written `.lang` files a
    # separate system leaves in `examples/` (untracked — see
    # `state/known-standing-dirty-paths.json`), reduced to the smallest
    # program that reproduces the same first error. Copied in as literals
    # ON PURPOSE: the files themselves are another system's and may change
    # or vanish, but the evidence for this round's decision must not.
    ("cognitive_verifier.lang", 'if c { 1 } else\n  2\n', "braces"),
    ("cognitive_verifier_v2.lang", 'fn f(c) { if c { 1 }\n  2 }\nlet r = f(true)\n',
     "if-without-else"),
    ("cognitive_verifier_v3.lang", 'if c { 1 }\nelse "two"\n', "braces"),
    ("nano_reasoner.lang", 'let s = 1\ns = 2\n', "assignment"),
    ("prod_demo_v1.lang", 'let d = rescue { f(1) }\n', "rescue-block"),
    ("prod_demo_v3.lang", 'let x = print(Calculating total)\n', "juxtaposition"),
    ("prod_demo_v4.lang", 'let d = f one, two\n', "juxtaposition"),
    ("prod_demo_v5.lang", 'let d = rescue(f(1)) catch(Miss as e) 0\n',
     "rescue-block"),
    ("whenceguard_auditor.lang", 'let xs = [{name: "a", qty: 2}]\n',
     "record-literal"),
    ("whenceguard_v2.lang", 'let xs = [Hardware Unit, 2100]\n', "juxtaposition"),
]


def test_the_ten_machine_written_programs_fail_for_six_reasons():
    """The operator asked whether to auto-fix older scripts for the braces
    rule. This is the measurement that answered it: of the ten programs,
    the braces rule is TWO. Six distinct causes, and every one of them is
    the same underlying mistake — a mainstream construct Whence
    deliberately does not have — which is why the fix was to make the
    errors teach rather than to rewrite the programs.
    """
    causes = set(c for _, _, c in MACHINE_WRITTEN)
    assert len(causes) == 6, sorted(causes)
    assert sum(1 for _, _, c in MACHINE_WRITTEN if c == "braces") == 2


def test_all_ten_now_name_a_cure():
    """1 -> 9 -> 10, across two rounds and two decisions.

    Before v0.22 exactly ONE of the ten said what to write instead
    ('if' requires 'else' (every expression has a value)). Decision 32
    (round 354) took that to nine. The tenth, `prod_demo_v4.lang`, was not
    a missing hint at all but a grammar laxity, recorded as such in the
    test below; decision 33 (v0.23, round 356) removed the laxity and the
    hint the other juxtaposition programs already got now reaches it too.
    """
    named = []
    for fname, src, cause in MACHINE_WRITTEN:
        msg = parse_error(src)
        head = msg.split(" at line")[0]
        named.append((fname, "(" in head))
    assert [f for f, ok in named if not ok] == [], named
    assert len(named) == 10


def test_the_tenth_was_a_separator_laxity_and_v023_removed_it():
    """`f one, two` could not be hinted in v0.22 because the parser ACCEPTED
    the mistake.

    Whence statements needed no separator, so `let d = f` and `one` were
    two complete statements on one line: the juxtaposition was consumed
    silently and the error surfaced three tokens later, at the `,`, where
    no adjacency was visible any more. The two programs whose juxtaposition
    WAS hinted in v0.22 are the ones where it happens inside brackets,
    where the statement rule could not swallow it.

    Round 354 pinned that as a known property of the grammar rather than a
    wish, and said a future round making the separator mandatory should
    UPDATE this test rather than delete it. v0.23 is that round. Both
    halves are kept: the programs that used to be accepted, now refused at
    the mistake, and the diagnosis `prod_demo_v4.lang` gets instead of
    `unexpected ','`.
    """
    for accepted_before in ("let a = 1 let b = 2\nlet c = a\n",
                            "let a = 1\nlet b = a b\n"):
        with pytest.raises(ParseError):
            parse(accepted_before)
    # the error moved from the `,` (col 14) back to `one` (col 11), which is
    # where the author's mistake actually is, and it names the cure.
    assert parse_error("let d = f one, two\n") == (
        "two statements on one line (two names in a row: Whence has no "
        "juxtaposition \u2014 a call is `f(x)` and text must be quoted) "
        "at line 1, col 11")


# --- the header line that rotted in one round --------------------------------

def test_spec_level_header_matches_the_highest_version_section():
    """Round 348 replaced SPEC.md's stale version enumeration with a
    sentence explaining why enumerations rot, and set the level to v0.20.
    Round 350 added `## v0.21` and did not touch the header. Round 354
    found it two levels stale — the replacement rotted faster than the
    thing it replaced, because a better sentence is still a claim no round
    re-executes (round 321's item 14, round 333's rescoping of it).

    This is the re-execution. `_ver` sorts on the numeric parts so v0.22
    outranks v0.2, which plain string order would not.
    """
    text = open(os.path.join(ROOT, "SPEC.md"), encoding="utf-8").read()
    sections = re.findall(r"^## v(\d+\.\d+)", text, re.M)
    assert sections, "no `## vN` sections found in SPEC.md"

    def _ver(v):
        return tuple(int(part) for part in v.split("."))

    highest = max(sections, key=_ver)
    header = re.search(r"^\*Spec level: \*\*v(\d+\.\d+)\*\*", text, re.M)
    assert header, "SPEC.md has no `*Spec level: **vN**` header line"
    assert header.group(1) == highest, (
        "SPEC.md's header says v%s; the highest `## vN` section is v%s"
        % (header.group(1), highest))


def test_research_state_track_c_names_the_same_version_as_spec_md():
    """The SECOND copy of the same number, found by round 416 six rounds
    after it went stale.

    `state/research-state.md`'s `- **Language (C):**` line carries the
    track's current version. It said `v0.39 (round 408)` through rounds
    410 (which made the bump to v0.40), 411, 412, 413, 414 and 415, while
    `SPEC.md`'s own header said v0.40 correctly the whole time — because
    the test above pins THAT header and nothing pinned this one. Round 348
    wrote the paragraph about exactly this failure mode, for SPEC.md, and
    it rotted in the other file.

    A version number belongs in one place. It is in two, so the second one
    gets a test instead of a promise.
    """
    spec = open(os.path.join(ROOT, "SPEC.md"), encoding="utf-8").read()
    header = re.search(r"^\*Spec level: \*\*v(\d+\.\d+)\*\*", spec, re.M)
    assert header, "SPEC.md has no `*Spec level: **vN**` header line"

    state_path = os.path.normpath(
        os.path.join(ROOT, "..", "..", "state", "research-state.md"))
    if not os.path.exists(state_path):          # a whence-only checkout
        return
    state = open(state_path, encoding="utf-8").read()
    m = re.search(r"^- \*\*Language \(C\):\*\* \*\*v(\d+\.\d+)\*\*",
                  state, re.M)
    assert m, "research-state.md has no `- **Language (C):** **vN**` line"
    assert m.group(1) == header.group(1), (
        "research-state.md's Language (C) line says v%s; SPEC.md's header "
        "says v%s" % (m.group(1), header.group(1)))


# --- the fourth silence, found by an oracle five rounds later ----------------

def test_a_contract_miss_never_carries_an_order_hint():
    """A TYPE-CONTRACT miss (v0.13 `-> T`, v0.19 `p: T`) is silent, even
    where the identical condition reached through the `typed` BUILTIN is
    not. Found by round 359's `param_erasure` oracle, which erases a v0.19
    parameter contract back into the v0.12 `let p = typed(p, T, label)`
    guard it replaced and compares answers: on 47 of 2500 generated
    programs the two forms differed, and in all 47 the entire difference
    was this clause.

    The silence is correct and is the fourth entry in this file's list:
    `_order_hint` names a signature the caller could reorder its arguments
    into, and an annotation has no argument list to reorder — `fn f(p: P)`
    is not a call the programmer wrote. What was WRONG was
    `_check_contract`'s docstring, which claimed since v0.19 that "the
    wording matches `typed`'s own for the same condition"; v0.22 made that
    false and nothing re-executed the claim (round 321's item 14 class
    again). Round 359 corrected the docstring and added this.

    Both contract ends and both `_check_contract` guard branches that have
    a `b_typed` counterpart are covered.
    """
    from whence import interp as I
    shadow = "shape P = @{a: num}\nfn outer() {\n  let P = 3\n%s\n}\n" \
             "let result = outer()\n"
    cases = [
        # not `_spec_ok`: the annotation's name resolved to a number.
        # `b_typed`'s wording for this is pinned above WITH the clause.
        (shadow % "  fn h() -> P { 1 }\n  h()",
         "typed spec must be a type name or a shape, got 3"),
        (shadow % "  fn h(q: P) { q }\n  h(1)",
         "typed spec must be a type name or a shape, got 3"),
        # an ordinary mismatch, the common case, both ends
        ("fn h() -> num { \"x\" }\nlet result = h()\n",
         "return value of h expected num, got str"),
        ("fn h(q: num) { q }\nlet result = h(\"x\")\n",
         "parameter 'q' of h expected num, got str"),
    ]
    for src, want in cases:
        got = host_reason(src)
        assert got == want, (src, got)
        assert HINT_RE.search(got) is None, got

    # ... and the same condition through the BUILTIN does carry it, so this
    # is a real asymmetry and not just an absence of hintable calls.
    with_hint = host_reason('let result = typed(@{a: 1}, true, "l")')
    assert with_hint == ("typed spec must be a type name or a shape, got true"
                         " (arguments fit typed(value, spec, label))")

    # the mechanism, at the unit level: `_order_hint` is only ever reached
    # from a registered builtin, and `_check_contract` is not one.
    src = open(os.path.join(ROOT, "whence", "interp.py"), encoding="utf-8").read()
    body = src.split("def _check_contract(")[1].split("\ndef ")[0]
    assert "_order_hint" not in body.split('"""')[2], \
        "_check_contract's CODE now calls _order_hint; this test is the pin"
    assert "_order_hint" in body.split('"""')[1], \
        "_check_contract's docstring must keep explaining why it does not"
