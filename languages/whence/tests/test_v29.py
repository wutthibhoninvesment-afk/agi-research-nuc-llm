"""Whence v0.29 (round 374, language C) — decision 37: the miss-message
differential, keyed by the OPERAND instead of by the site.

`tests/test_miss_message_differential.py` (v0.28, round 372) keys its corpus
by HOST SITE: one case per reachable `mk_miss`/`merge_miss` site in
`whence/interp.py`, chosen by greedy set cover. It reported 103 of 114 cases
agreeing between the host and `examples/self_eval.lang`, with the remaining
11 covered by three named exemptions. Its own module docstring records the
hole it could not close:

    Site coverage bounds the HOST side and only SAMPLES the guest side. One
    host site can be reached by operands the guest words differently from
    each other.

Round 372 patched that by hand, with a 10-case `EXTRA` list found by
noticing. THIS FILE REPLACES NOTICING WITH A CROSS PRODUCT: an ATLAS of one
source expression per renderable payload shape, crossed against every binary
operator, every unary operator, indexing, field access, every call form,
`if`, `rescue` and every argument slot of every builtin. 11 326 cases when
it was measured (11 354 once decision 37's own `show` joined the table), so
each host site is reached by many operand shapes rather than by one.

WHAT THAT FOUND, on the v0.28 tree (`state/whence/round-374/`):

  * **54 wording divergences no exemption covered** — i.e. v0.28's "every
    remaining divergence is one of three named exemptions" was a property of
    its 124-case corpus, not of the language. All four causes were the SAME
    one: v0.28's box-leak re-render was applied at the sites its corpus
    reached, with the operand its corpus used.
      - `eval_and`/`eval_or` re-rendered the LEFT operand only, because the
        cover's case had a left-hand miss (`true and [1, 2]` leaked).
      - `eval_index`'s gate read the INDEX, so `@{a: 1}[1]` — whose message
        renders the OBJECT — kept leaking.
      - `eval_field` and `eval_if` were never touched at all: the cover
        reached both with a SCALAR, for which a guest payload and a host
        payload are the same object.
      - `apply_builtin`'s cost gate (`any_compound`) missed the two slots
        that hand the host a box whatever the operands are, so
        `put(1, "b", 2)` INVENTED `(arguments fit put(r, name, v))`.
  * **Two hand-rolled copies of `show_payload` inside the guest**
    (`show_callable`'s `str` fallback and `show_val`), which is what made
    `filter(fn(a) { true }, "ab")` read `... got ab` against the host's
    `... got "ab"`. Decision 37 adds the `show` builtin so the guest can
    DELEGATE the rendering; that also retired round 362's two rendering
    exemptions (see `test_contract_message_differential.py`).
  * **A fourth exemption nobody had a case for (E4).** The guest answers
    `steps`/`at`/`blame` from the HOST's provenance of the value, which for
    a guest-computed value is `self_eval.lang`'s OWN history: `len(steps(1 +
    2))` is 4 on the host and 284 in the guest, and `blame` reports the
    evaluator's internal probe misses. `test_the_provenance_family_is_still
    _exempt_and_still_wrong` pins it; SPEC v0.29 carries the design sketch.

AFTER the v0.29 fixes: **zero** unexplained divergences over the same
11 326 cases, and the exemptions account for every one of the 4 469 that
remain — E1 1 796, E2 2 670, E4 3. That count is the other half of the
finding: the site-keyed corpus reported 11 exempt cases in 114 (9.6%) and
the operand sweep finds 4 469 in 11 326 (39.5%). E1 and E2 are not edge
cases; a corpus that visits each site once samples them thinly.

COST. The guest side is ONE interpreter run per 500-case batch (round 362's
trick) and costs ~240 s; the host side ~3 s. The whole sweep is therefore
`whence_slow`. The atlas, the generator and the classifier's own
well-formedness stay in the fast tier, because a corpus that silently stops
covering a kind is the failure this file exists to prevent.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whence.interp import Interpreter, _kind
from whence.lexer import LexError
from whence.parser import ParseError
from whence.values import Miss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
MARKER = "# ==== SELF-TESTS"

# Same rule as the v0.28 file: the guest's trailing `(line N)` is a line in
# `self_eval.lang`, the host's a line in the program under test.
# `$`-anchored since round 404 (v0.38): unanchored, this deletes a line
# number a message carries as a FACT, not just the implementation
# coordinate `miss` appends. Seven copies of this regex existed and all
# seven were unanchored — see `tests/test_self_eval.py`'s copy for the
# full account.
LINE_SUFFIX = re.compile(r" \(line \d+\)$")

PRELUDE = "fn g(a) { a }\n"

# --------------------------------------------------------------------------
# the atlas — one source expression per renderable payload SHAPE
#
# Not per TYPE: `[1, 2]`, `[len]` and `[1 / 0]` are all `list` to `_kind`
# and are three different things to `show_payload`, to `deep_eq` and to the
# guest's boxing. Shape is the unit the divergences turned out to live in.
# --------------------------------------------------------------------------
ATLAS = [
    ("int",       "1"),
    ("zero",      "0"),
    ("float",     "1.5"),
    ("str",       '"ab"'),
    ("emptystr",  '""'),
    ("true",      "true"),
    ("false",     "false"),
    ("emptylist", "[]"),
    ("list",      "[1, 2]"),
    ("liststr",   '["a"]'),
    ("nestlist",  "[[1]]"),
    ("listfn",    "[len]"),
    ("listclo",   "[g]"),
    ("listwhy",   "[why 1]"),
    ("listmiss",  "[1 / 0]"),
    ("emptyrec",  "@{}"),
    ("rec",       "@{a: 1}"),
    ("recfn",     "@{a: len}"),
    ("recwhy",    "@{a: why 1}"),
    ("recmiss",   "@{a: 1 / 0}"),
    ("builtin",   "len"),
    ("anonfn",    "fn(a) { a }"),
    ("namedfn",   "g"),
    ("why",       "why 1"),
    ("miss",      "1 / 0"),
    ("guessv",    'guess(1, 0.5, "s")'),
]

# `^` is deliberately absent: it is not a Whence operator (the lexer refuses
# it), so including it would add 676 PARSE-vs-guest-miss cases that measure
# `test_parse_error_differential.py`'s subject, not this one.
BINOPS = ["+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=",
          "and", "or"]
UNOPS = [("neg", "- %s"), ("not", "not %s"), ("miss", "miss %s")]

# One "sane" argument per slot; the sweep replaces ONE slot at a time with
# each atlas entry, so a wrong-kind miss is attributable to that slot.
DEFAULTS = {
    "len": ["1"], "range": ["0", "3"],
    "map": ["fn(a) { a }", "[1, 2]"], "filter": ["fn(a) { true }", "[1, 2]"],
    "fold": ["fn(ac, x) { ac }", "0", "[1, 2]"],
    "push": ["[1]", "2"], "str": ["1"], "show": ["1"], "num": ['"1"'],
    "abs": ["1"], "sqrt": ["4"], "trunc": ["1.5"], "missed": ["1"],
    "reasons": ["1"], "note": ['"l"', "1"], "contains": ["[1, 2]", "1"],
    "join": ['["a"]', '","'], "keys": ["@{a: 1}"],
    "merge": ["@{a: 1}", "@{b: 2}"], "get": ["@{a: 1}", '"a"'],
    "has": ["@{a: 1}", '"a"'], "put": ["@{a: 1}", '"b"', "2"],
    "find": ["fn(a) { true }", "[1, 2]"],
    "typed": ["1", '"num"', '"lbl"'], "matches": ["1", '"num"'],
    "shapeof": ["1"], "guess": ["1", "0.5", '"s"'], "is_guess": ["1"],
    "confidence": ["1"], "sure": ["1", "0.5"],
    "steps": ["1 / 0", '"x"'], "at": ["1 / 0", '"x"'], "blame": ["1 / 0"],
    "diverge": ["1", "2"], "contrast": ["1", "2"],
}
# `print` writes and `rand` draws: the guest's miss re-render calls a builtin
# a SECOND time, so both are excluded on the same reasoning `self_eval.lang`
# excludes them there.
SKIP_BUILTINS = {"print", "rand"}

PROVENANCE_FAMILY = ("steps", "at", "blame", "diverge", "contrast")


# Which atlas entries carry a value the guest cannot represent the way the
# host does. Recorded per case by `build_cases` rather than recovered from
# the source text later: `"g" in src` also matches `guess`, `range` and
# `get`, and a classifier that OVER-attributes to an exemption is exactly
# the failure `test_every_divergence_is_named` exists to catch. (The first
# draft of this file did it by substring and silently absorbed 21 real
# divergences into E2.)
WHY_ATOMS = frozenset(("why", "listwhy", "recwhy"))
CALLABLE_ATOMS = frozenset(("builtin", "anonfn", "namedfn",
                            "listfn", "listclo", "recfn"))
# A default argument that is itself a callable, in a slot this case did NOT
# replace — `map`/`filter`/`fold`/`find` all take the function first.
DEFAULT_FN = "<default-fn>"


def build_cases():
    """`[(name, family, src, atoms)]` — deterministic, no randomness."""
    cases = []

    def add(name, family, expr, atoms):
        cases.append((name, family, PRELUDE + "let r = " + expr + "\n",
                      frozenset(atoms)))

    for op in BINOPS:
        for ln, ls in ATLAS:
            for rn, rs in ATLAS:
                add("bin:%s:%s:%s" % (op, ln, rn), "binop",
                    "(%s) %s (%s)" % (ls, op, rs), (ln, rn))
    for un, tmpl in UNOPS:
        for n, s in ATLAS:
            add("un:%s:%s" % (un, n), "unary", tmpl % ("(%s)" % s), (n,))
    for ln, ls in ATLAS:
        for rn, rs in ATLAS:
            add("idx:%s:%s" % (ln, rn), "index", "(%s)[%s]" % (ls, rs),
                (ln, rn))
    for n, s in ATLAS:
        add("fld:%s" % n, "field", "(%s).a" % s, (n,))
        add("fld_missing:%s" % n, "field", "(%s).zz" % s, (n,))
        add("call0:%s" % n, "call", "(%s)()" % s, (n,))
        add("call1:%s" % n, "call", "(%s)(1)" % s, (n,))
        add("call2:%s" % n, "call", "(%s)(1, 2)" % s, (n,))
        add("if:%s" % n, "cond", "if (%s) { 1 } else { 2 }" % s, (n,))
        add("rescue:%s" % n, "rescue", "(%s) rescue 7" % s, (n,))
    for b, defs in sorted(DEFAULTS.items()):
        if b in SKIP_BUILTINS:
            continue
        fn_slots = [j for j, d in enumerate(defs) if d.startswith("fn(")]
        for i in range(len(defs)):
            for n, s in ATLAS:
                args = list(defs)
                args[i] = s
                atoms = [n]
                if any(j != i for j in fn_slots):
                    atoms.append(DEFAULT_FN)
                add("b:%s:%d:%s" % (b, i, n), "builtin",
                    "%s(%s)" % (b, ", ".join(args)), atoms)
        add("barity0:%s" % b, "builtin_arity", "%s()" % b, ())
        add("barityN:%s" % b, "builtin_arity",
            "%s(%s)" % (b, ", ".join(["1"] * (len(defs) + 1))), ())
    return cases


CASES = build_cases()


# --------------------------------------------------------------------------
# the four exemptions
#
# Each is a claim about the guest's REPRESENTATION, not about a message, so
# each is keyed by what the CASE contains rather than by what the host
# happened to say — v0.28 classified by the host's wording and that is
# exactly what made 162 E1/E2 consequences read as "unexplained" on the
# first pass of this sweep.
# --------------------------------------------------------------------------
EXEMPT = {
    "E1-why-is-reified":
        "The host's `why x` is an opaque `Explanation`; the guest's is a "
        "RECORD (`reify`/`reify_node`), because guest code must be able to "
        "READ a history — SPEC's own 'history is data'. Every message that "
        "renders a `why` therefore differs, AND — the half v0.28 did not "
        "state — every operation that accepts a record accepts a guest "
        "`why`: `keys(why 1)`, `has(why 1, \"a\")`, `merge(why 1, @{})` "
        "and `@{} == why 1` all miss on the host and succeed in the guest. "
        "That is a MISSEDNESS divergence, not a wording one, and it is a "
        "consequence of the design.",
    "E2-a-callable-cannot-be-rebuilt":
        "The host renders a function `<fn>`, `<fn NAME>` or `<builtin "
        "NAME>`; a guest function is a tagged record, and `<fn NAME>` "
        "cannot be built at run time because `fn NAME(..)` is a STATEMENT "
        "with a literal name (v0.28's finding, unchanged). v0.29 adds two "
        "halves v0.28 did not state. (a) MISSEDNESS: `len == guess(1, "
        "0.5, \"s\")` misses on the host (a Builtin is opaque to "
        "`deep_eq`) and returns a value in the guest (a record is not). "
        "(b) ORDER: `_incomparable_kind` searches left-operand-first for "
        "the first opaque payload, and a guest callable is not opaque, so "
        "`[len] == [1 / 0]` finds the FUNCTION on the host and the MISS in "
        "the guest — the two name different kinds and both are right about "
        "their own value space.",
    "E3-the-budgets-are-different-in-kind":
        "`recursion too deep in g (depth 20000)` vs `guest recursion too "
        "deep in g (guest depth 400)`. Round 371 established this is a "
        "difference of KIND: the host charges a tail call nothing (SPEC "
        "rule 8) and the guest's `apply_closure` charges one guest frame "
        "per call. The guest says 'guest' on purpose. No case in THIS "
        "sweep reaches it — the atlas is about operand shape, not about "
        "depth — so it is carried by "
        "`tests/test_miss_message_differential.py`, which owns it.",
    "E4-the-provenance-family-answers-from-the-wrong-history":
        "NEW in v0.29 and NARROWED by v0.30 (round 378) from five builtins "
        "to two. `self_eval.lang` BUILDS a correct guest history (the "
        "`@{v, op, ins}` box graph `why`/`reify` walk, checked against the "
        "host DAG by `tests/test_self_eval.py`'s guest-level provenance "
        "tests) and then answered the whole provenance-query family by "
        "calling the HOST builtin on the guest's PAYLOAD -- whose host "
        "provenance is `self_eval.lang`'s own execution. Round 218 "
        "introduced that delegation with the comment \"`a0`'s real host "
        "provenance is already there for free\"; the provenance that is "
        "there is the evaluator's. `len(steps(1 + 2))` was 4 on the host "
        "and 284 in the guest. v0.30 answers `steps`/`at`/`blame` from the "
        "guest box graph and they now agree: the 3 cases this exemption "
        "covered in this atlas are 0, and the family's agreement went "
        "204/234 to 208/234. What remains is `diverge`/`contrast`, whose "
        "host rules a Whence expression cannot state -- `diverge` decides "
        "sameness by `na is nb` and memoises on `(id(na), id(nb))`, and "
        "`render_contrast` column-aligns two rendered histories. NO CASE "
        "IN THIS ATLAS REACHES THE REMAINDER: its 104 diverge/contrast "
        "cases are argument-shape cases and all 104 agree. So, exactly "
        "like E3, it is excluded from `test_each_exemption_is_load_"
        "bearing` and carried by the file that owns it, "
        "`tests/test_v30.py`.",
}

def classify(name, atoms, host, guest):
    """Which exemption, if any, explains a divergence for this case.

    Fixed order: E3 and E4 are about a MECHANISM (a budget, a query), E1
    and E2 about a VALUE the case contains. E1 before E2 because a `why` is
    reified whether or not a callable is also present, and the reified
    record is what the message then renders."""
    reason = host[1] if host[0] == "MISS" else ""
    if "too deep" in reason or "tail loop" in reason:
        return "E3-the-budgets-are-different-in-kind"
    parts = name.split(":")
    if parts[0] == "b" and parts[1] in PROVENANCE_FAMILY \
            and host[0] != guest[0]:
        return "E4-the-provenance-family-answers-from-the-wrong-history"
    if atoms & WHY_ATOMS:
        return "E1-why-is-reified"
    if (atoms & CALLABLE_ATOMS) or DEFAULT_FN in atoms:
        return "E2-a-callable-cannot-be-rebuilt"
    return None


# --------------------------------------------------------------------------
# running both sides
# --------------------------------------------------------------------------

def outcome(src, **kw):
    """`("MISS", reason, n_reasons)`, `("VAL",)`, or a parse / host-exception
    marker. A host exception is DATA: rule 2 says one can never escape, and
    `test_no_case_raises_out_of_the_host` is the assertion that says so."""
    try:
        env = Interpreter(out=lambda s: None, seed=7, **kw).run(src)
    except (LexError, ParseError) as e:
        return ("PARSE", type(e).__name__)
    except BaseException as e:                       # noqa: BLE001 — data
        return ("HOSTEXC", type(e).__name__, str(e)[:160])
    box = env.get("r")
    if box is None:
        return ("NOBIND",)
    if isinstance(box.payload, Miss):
        return ("MISS", LINE_SUFFIX.sub("", box.payload.reasons[0]),
                len(box.payload.reasons))
    return ("VAL",)


def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


def guest_batch(cases, lib):
    """One interpreter run for the whole batch. Batching at 500 keeps the
    generated program (and its parse) from dominating; per-case runs would
    be ~1.5 s x N and are the wrong design (round 362)."""
    parts = [lib]
    for i, (_, _, src, _a) in enumerate(cases):
        parts.append('let __out%d = run_src("%s")\n' % (i, escape(src)))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    out = []
    for i, (name, _, _, _a) in enumerate(cases):
        rec = env.get("__out%d" % i)
        assert rec is not None, name
        payload = rec.payload.fields["v"].payload
        if isinstance(payload, Miss):
            out.append(("MISS", LINE_SUFFIX.sub("", payload.reasons[0]),
                        len(payload.reasons)))
        else:
            out.append(("VAL",))
    return out


@pytest.fixture(scope="module")
def host_outcomes():
    return {n: outcome(s) for n, _, s, _a in CASES}


@pytest.fixture(scope="module")
def guest_outcomes():
    lib = library_source()
    out = {}
    for i in range(0, len(CASES), 500):
        chunk = CASES[i:i + 500]
        for (n, _, _, _a), o in zip(chunk, guest_batch(chunk, lib)):
            out[n] = o
    return out


# --------------------------------------------------------------------------
# the corpus itself — fast tier
# --------------------------------------------------------------------------

def test_the_corpus_is_well_formed():
    names = [n for n, _, _, _a in CASES]
    assert len(names) == len(set(names)), "duplicate case name"
    # The exact size is the point: this file's claim is that it is much
    # wider than a site-keyed corpus, and a silent shrink would be the
    # failure it exists to prevent.
    # 11 326 when the sweep was MEASURED (`state/whence/round-374/`); 28
    # more once decision 37's own `show` joined the builtin table, which is
    # one slot x 26 atlas entries plus its two arity cases.
    assert len(CASES) == 11354, len(CASES)
    assert len(ATLAS) == 26


def test_the_atlas_covers_every_kind_the_interpreter_can_name():
    """`_kind` is the host's own list of runtime shapes. An atlas that
    cannot produce one of them leaves a whole column of the cross product
    untested, silently."""
    kinds = set()
    for _, s in ATLAS:
        o = Interpreter(out=lambda s: None, seed=7).run(
            PRELUDE + "let r = " + s + "\n")
        kinds.add(_kind(o.get("r").payload))
    assert {"num", "str", "bool", "list", "record", "fn", "guess",
            "value"} <= kinds, sorted(kinds)


def test_the_cross_product_is_actually_crossed():
    """Guards the shape of the generator, not its output: every binary
    operator must appear with every ordered pair of atlas entries. A future
    edit that samples instead of crossing is the thing that produced
    v0.28's blind spot."""
    fams = {}
    for n, fam, _s, _a in CASES:
        fams.setdefault(fam, []).append(n)
    assert len(fams["binop"]) == len(BINOPS) * len(ATLAS) ** 2
    assert len(fams["index"]) == len(ATLAS) ** 2
    assert len(fams["unary"]) == len(UNOPS) * len(ATLAS)


def test_every_exemption_is_documented_and_reachable_by_the_classifier():
    """A classifier that can never return an exemption is a dead branch,
    and a dead exemption reads as coverage — round 373's `resolved` rule,
    in another file."""
    assert set(EXEMPT) == {
        "E1-why-is-reified",
        "E2-a-callable-cannot-be-rebuilt",
        "E3-the-budgets-are-different-in-kind",
        "E4-the-provenance-family-answers-from-the-wrong-history",
    }
    for k, v in EXEMPT.items():
        assert len(v) > 200, k


def test_the_provenance_family_agrees_now_and_the_pins_are_exact():
    """v0.29 pinned E4 as an inequality here -- `guest_steps > 50` against a
    host 4, `guest_blame > 1` against a host 1 -- with the note that it was
    "the one exemption a reader is most likely to assume was fixed".

    v0.30 (round 378) fixed it for `steps`/`at`/`blame`, so the SAME two
    programs are now equalities. Kept in this file rather than moved to
    test_v30.py: this is where the wrong numbers were published, and an
    exemption that retires should be visibly retired at its own pin."""
    lib = library_source()
    got = guest_batch(
        [("steps", "e4", "let x = 1 + 2\nlet r = len(steps(x))\n", ()),
         ("blame", "e4", "let x = 1 / 0\nlet r = len(blame(x))\n", ())], lib)
    host_steps = Interpreter(out=lambda s: None, seed=7).run(
        "let x = 1 + 2\nlet r = len(steps(x))\n").get("r").payload
    host_blame = Interpreter(out=lambda s: None, seed=7).run(
        "let x = 1 / 0\nlet r = len(blame(x))\n").get("r").payload
    assert host_steps == 4 and host_blame == 1, (host_steps, host_blame)
    assert got[0] == ("VAL",) and got[1] == ("VAL",)
    guest_steps = _guest_number("let x = 1 + 2\nlet r = len(steps(x))\n", lib)
    guest_blame = _guest_number("let x = 1 / 0\nlet r = len(blame(x))\n", lib)
    assert guest_steps == 4, guest_steps
    assert guest_blame == 1, guest_blame


def _guest_number(src, lib):
    parts = [lib, 'let __o = run_src("%s")\n' % escape(src)]
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    return env.get("__o").payload.fields["v"].payload


# --------------------------------------------------------------------------
# the sweep — slow tier
# --------------------------------------------------------------------------

@pytest.mark.whence_slow
def test_no_case_raises_out_of_the_host(host_outcomes):
    """SPEC rule 2: a runtime failure is a miss, never an exception. 11 326
    cases is the widest statement of that this repo makes."""
    bad = [(n, o) for n, o in host_outcomes.items() if o[0] == "HOSTEXC"]
    assert bad == [], bad[:5]


@pytest.mark.whence_slow
def test_no_case_fails_to_parse(host_outcomes):
    """The generator builds source text, so a parse error means the
    GENERATOR is wrong (it emitted something that is not Whence), not that
    the language is. `^` was removed from `BINOPS` for exactly this."""
    bad = [(n, o) for n, o in host_outcomes.items() if o[0] == "PARSE"]
    assert bad == [], bad[:5]


@pytest.fixture(scope="module")
def three_engine_outcomes():
    """Every case under all three engines. 34 062 host runs, ~14 s — cheap
    enough that leaving it unmeasured (which the first draft of this round
    did) was not a budget decision, only an oversight."""
    modes = (("direct", {}), ("fast", {"direct": False}),
             ("slow", {"fast": False}))
    return {n: tuple(outcome(s, **kw) for _, kw in modes)
            for n, _, s, _a in CASES}


@pytest.mark.whence_slow
def test_the_three_engines_word_every_miss_identically(three_engine_outcomes):
    """v0.28 pinned this over its 114-case corpus and a 23 997-case
    mechanical sweep; v0.29 re-pins it over the operand cross product,
    which is a different shape of input (the same site reached by many
    operand kinds, rather than many sites reached once). Still ZERO
    divergences in wording, reason count or missedness. A negative result,
    and this file's only claim about the host in isolation."""
    bad = [(n, o) for n, o in three_engine_outcomes.items()
           if not (o[0] == o[1] == o[2])]
    assert bad == [], bad[:5]


@pytest.mark.whence_slow
def test_the_sweep_exercises_both_outcomes(host_outcomes):
    """Without this the agreement tests below would be satisfiable by a
    corpus that only ever misses."""
    # MEASURED, not guessed: 1 808 values and 9 546 misses over the 11 354
    # cases. (The first draft asserted `> 2000` on both sides from memory
    # and went red on the value side — the atlas is deliberately weighted
    # towards operand shapes an operation REFUSES.) Floors, well under the
    # measurement, so an ordinary language change cannot trip them.
    vals = sum(1 for o in host_outcomes.values() if o[0] == "VAL")
    misses = sum(1 for o in host_outcomes.values() if o[0] == "MISS")
    assert vals > 1500 and misses > 5000, (vals, misses)


@pytest.mark.whence_slow
def test_every_divergence_is_named(host_outcomes, guest_outcomes):
    """THE ASSERTION OF THIS FILE. Over the whole cross product, every
    host/guest difference — in wording, in reason count, or in whether
    there is a miss at all — is attributable to one of the four exemptions.
    On the v0.28 tree this failed with 54 unexplained cases."""
    unexplained = []
    for n, fam, src, atoms in CASES:
        h, g = host_outcomes[n], guest_outcomes[n]
        if h == g:
            continue
        if classify(n, atoms, h, g) is None:
            unexplained.append((n, src.strip().replace("\n", "; "), h, g))
    assert unexplained == [], (
        "%d unexplained divergences, first 5: %s"
        % (len(unexplained), unexplained[:5]))


@pytest.mark.whence_slow
def test_each_exemption_is_load_bearing(host_outcomes, guest_outcomes):
    """An exemption with no case left is a lie in the corpus — round 362's
    rule, applied to this one. E3 is the declared exception: no case in
    this atlas reaches a depth budget, and it is carried by
    `test_miss_message_differential.py` instead, so requiring a case here
    would force a slow recursion case into a sweep that is about operand
    shape.

    v0.30 (round 378) added E4 to that exclusion for the identical reason.
    Its `steps`/`at`/`blame` half is FIXED, not exempted, and its
    `diverge`/`contrast` remainder needs two histories that actually
    diverge -- which this atlas, being about the shape of ONE operand,
    never builds. `tests/test_v30.py` owns it and pins it live."""
    used = set()
    for n, fam, src, atoms in CASES:
        h, g = host_outcomes[n], guest_outcomes[n]
        if h != g:
            used.add(classify(n, atoms, h, g))
    assert used == set(EXEMPT) - {"E3-the-budgets-are-different-in-kind",
                                  "E4-the-provenance-family-answers-from-"
                                  "the-wrong-history"}, sorted(used)


@pytest.mark.whence_slow
def test_the_agreement_rate_does_not_regress(host_outcomes, guest_outcomes):
    """A floor, not a pin. v0.28 agreed on 6 789 of these 11 326 cases,
    v0.29 on 6 857 and v0.30 on 6 861; the number can only go UP without an
    exemption being added, and adding one is what
    `test_every_exemption_is_documented` makes visible.

    v0.30's 6 861 is DERIVED, not swept: round 378 measured the 234-case
    provenance-family subset old-vs-new (204 -> 208 agreeing) and no other
    case in this atlas can reach the code it changed, so the whole-atlas
    figure moves by exactly that +4. Stated this way on purpose -- the
    derivation is what a later sweep can falsify."""
    agree = sum(1 for n, _, _, _a in CASES
                if host_outcomes[n] == guest_outcomes[n])
    assert agree >= 6861, agree


@pytest.mark.whence_slow
def test_the_exemption_classes_are_the_measured_sizes(host_outcomes,
                                                      guest_outcomes):
    """The headline number, asserted rather than described: the site-keyed
    corpus reported 11 exempt cases in 114 (9.6%) and this one finds ~39.5%
    of the surface exempt. E1 and E2 are not edge cases; a site-keyed
    corpus samples them thinly because it visits each site once."""
    counts = {}
    for n, fam, src, atoms in CASES:
        h, g = host_outcomes[n], guest_outcomes[n]
        if h != g:
            k = classify(n, atoms, h, g)
            counts[k] = counts.get(k, 0) + 1
    total = sum(counts.values())
    assert total > 0.35 * len(CASES), (total, len(CASES))
    assert counts["E1-why-is-reified"] > 1000, counts
    assert counts["E2-a-callable-cannot-be-rebuilt"] > 1000, counts
    # v0.30: 3 -> 0. Measured on the 234-case provenance-family SUBSET (the
    # only cases whose guest side this round could change), old library vs
    # new: 204/234 agreeing -> 208/234, E4 3 -> 0, E1 9 -> 8, E2 18 -> 18.
    assert counts.get(
        "E4-the-provenance-family-answers-from-the-wrong-history", 0) == 0, \
        counts
