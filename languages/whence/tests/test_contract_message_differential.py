"""Whence v0.25 (round 362, language C) — decision 35: the CONTRACT-message
refusal set, host vs guest.

`tests/test_parse_error_differential.py` (v0.24, round 360) asked whether the
two implementations refuse the same PROGRAMS, and answered "positions must
agree, wording need not". This file asks the same question one level down,
about the messages a program produces at RUN time when a type contract
fails — and gets the opposite answer, because here the wording is supposed
to agree. `examples/self_eval.lang`'s `check_contract`, `guest_match_why`
and `guest_mismatch_reason` were written to reproduce the host's sentences
exactly; round 338's own tests say so in their names.

WHY NOTHING HAD EVER CHECKED IT. The guest-differential oracle
(`harness/swe/guest.py`) compares payloads and exempts miss REASONS — its
oldest exemption, round 17, and a correct one for its purpose. So every
divergence in this file was rated `ok` by every campaign that ever ran:
both sides missed, and the oracle does not read what they said. The only
existing wording comparison was `test_self_eval.py`'s `SHAPE_MISS_CASES`,
THREE hand-written cases, against a host surface with 13 message sites.
Round 361's slow-tier instrument is what made this round look: it found
`harness/tests/test_swe_guest.py::test_no_shape_declaration_reaches_the_
guest_generator` red, which turned out to mean that the fuzzer had been
generating `shape` declarations into GUEST programs since round 347 while
a pin written in the same commit said it never would.

THE CONTRACT (SPEC.md `## v0.25`)

  1. MISSED-NESS AGREES. Every case misses on both sides or neither.
  2. THE WORDING AGREES, except for the enumerated `EXEMPT` set — which is
     two properties of the host's `show_payload` RENDERER (its caps and its
     escaping) and one measured, unfixed finding (`push`), each asserted
     load-bearing in BOTH directions by
     `test_each_exemption_is_load_bearing`.
  3. THE CORPUS REACHES EVERY HOST SITE. `test_the_corpus_reaches_every_
     host_contract_message_site` derives the sites from `whence/interp.py`'s
     AST and captures the ones the corpus actually hits by wrapping
     `mk_miss`/`merge_miss` — the same "key each case by the raise SITE, not
     the message" rule `skills/refusal-set-differential` states, since one
     generic site can absorb a dozen cases and look like coverage.

Cost: one interpreter run for the whole guest corpus, the trick
`test_self_eval.py`, `test_lexer_guest_parity.py` and
`test_parse_error_differential.py` all use.
"""

import ast
import os
import re
import sys
import traceback

import pytest

from whence.interp import Interpreter
from whence.values import Miss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
INTERP_PY = os.path.join(ROOT, "whence", "interp.py")
MARKER = "# ==== SELF-TESTS"

# The guest's trailing `(line N)` is a line in `self_eval.lang`; the host's
# is a line in the program. Both are stripped — this file compares WORDING,
# and `test_parse_error_differential.py` owns positions.
# `$`-anchored since round 404 (v0.38): unanchored, this deletes a line
# number a message carries as a FACT, not just the implementation
# coordinate `miss` appends. Seven copies of this regex existed and all
# seven were unanchored — see `tests/test_self_eval.py`'s copy for the
# full account.
LINE_SUFFIX = re.compile(r" \(line \d+\)$")


def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


# --------------------------------------------------------------------------
# the corpus — one case per host message site, plus the families that
# diverged, plus valid controls so rule 1 is a real biconditional
# --------------------------------------------------------------------------

BAD = [
    # --- b_typed: the three guards, in the host's own order ---------------
    ("typed-propagated-value",  'let r = typed(num("x"), "num", "L")'),
    ("typed-propagated-spec",   'let r = typed(1, num("x"), "L")'),
    ("typed-propagated-label",  'let r = typed(1, "num", num("x"))'),
    ("typed-label-num",         'let r = typed(1, "num", 5)'),
    ("typed-label-list",        'let r = typed(1, "num", [1])'),
    ("typed-label-record",      'let r = typed(1, "num", @{a: 1})'),
    ("typed-label-fn",          'let r = typed(1, "num", fn(z) { z })'),
    ("typed-spec-num",          'let r = typed(1, 5, "L")'),
    ("typed-spec-bool",         'let r = typed(1, true, "L")'),
    ("typed-spec-list",         'let r = typed(1, [1], "L")'),
    ("typed-spec-fn",           'let r = typed(1, fn(z) { z }, "L")'),
    ("typed-spec-badfield",     'let r = typed(1, @{a: 5}, "L")'),
    ("typed-spec-badfield-deep",
     'let r = typed(@{a: @{b: 1}}, @{a: 5}, "L")'),
    ("typed-spec-badfield-list", 'let r = typed(@{}, @{a: [1]}, "L")'),
    # the order hint: the same guard, reached by a caller who swapped args
    ("typed-order-hint",        'let r = typed("num", 1, "L")'),
    # --- b_typed / _mismatch_reason: the v0.12 sentence -------------------
    ("typed-prim-mismatch",     'let r = typed("s", "num", "L")'),
    ("typed-prim-vs-fn",        'let r = typed(fn(z) { z }, "num", "L")'),
    ("typed-prim-vs-guess",     'let r = typed(guess(5, 0.9, "m"), "str", "L")'),
    ("typed-rec-vs-num",        'let r = typed(1, @{a: "num"}, "L")'),
    ("typed-named-rec-vs-num",
     'let r = typed(1, @{__shape: "Pt", a: "num"}, "L")'),
    # --- _match_why: its three clauses, and the nesting ------------------
    ("why-no-field",            'let r = typed(@{}, @{a: "num"}, "L")'),
    ("why-field-kind",          'let r = typed(@{a: "s"}, @{a: "num"}, "L")'),
    ("why-field-is-a-miss",
     'let r = typed(@{a: num("x")}, @{a: "num"}, "L")'),
    ("why-nested-path",
     'let r = typed(@{a: @{b: 1}}, @{a: @{b: "str"}}, "L")'),
    ("why-nested-missing",
     'let r = typed(@{a: @{}}, @{a: @{b: "str"}}, "L")'),
    ("why-sorted-order",
     'let r = typed(@{}, @{z: "num", a: "num"}, "L")'),
    # --- decision 35: `__shape` is a NAME slot ---------------------------
    ("shape-name-num",   'let r = typed(1, @{__shape: 5, a: "num"}, "L")'),
    ("shape-name-bool",  'let r = typed(1, @{__shape: true, a: "num"}, "L")'),
    ("shape-name-list",
     'let r = typed(1, @{__shape: [1, 2], a: "num"}, "L")'),
    ("shape-name-record",
     'let r = typed(1, @{__shape: @{q: 1}, a: "num"}, "L")'),
    ("shape-name-miss",
     'let r = typed(1, @{__shape: num("x"), a: "num"}, "L")'),
    ("shape-name-empty",  'let r = typed(1, @{__shape: "", a: "num"}, "L")'),
    ("shape-name-nested",
     'let r = typed(@{a: 1}, @{a: @{__shape: 7, b: "num"}}, "L")'),
    # --- _check_contract: the annotation ends ----------------------------
    ("contract-ret-prim",  'fn g() -> num { "s" }\nlet r = g()'),
    ("contract-ret-anon",  'let g = fn() -> num { "s" }\nlet r = g()'),
    ("contract-param-prim", 'fn g(p: num) { 0 }\nlet r = g("s")'),
    ("contract-ret-shape",
     'shape P = @{x: num}\nfn mk() -> P { @{y: 1} }\nlet r = mk()'),
    ("contract-param-shape",
     'shape P = @{x: num, y: num}\nfn mag(p: P) { 0 }\nlet r = mag(@{x: 3})'),
    # a shape name shadowed in the DEFINING block (round 342 s7): the only
    # way an ANNOTATION reaches `_check_contract`'s `not _spec_ok` guard
    ("contract-shadow-num",
     'shape S = @{x: num}\nfn outer() { let S = 5\n'
     'fn g() -> S { 1 }\ng() }\nlet r = outer()'),
    ("contract-shadow-badfield",
     'shape S = @{x: num}\nfn outer() { let S = @{a: 5}\n'
     'fn g() -> S { 1 }\ng() }\nlet r = outer()'),
    ("contract-shadow-fn",
     'shape S = @{x: num}\nfn outer() { let S = fn(z) { z }\n'
     'fn g() -> S { 1 }\ng() }\nlet r = outer()'),
    ("contract-shadow-named-fn",
     'shape S = @{x: num}\nfn h(z) { z }\nfn outer() { let S = h\n'
     'fn g() -> S { 1 }\ng() }\nlet r = outer()'),
    ("contract-shadow-shape-name",
     'shape S = @{x: num}\nfn outer() { let S = @{__shape: 5, a: "num"}\n'
     'fn g() -> S { 1 }\ng() }\nlet r = outer()'),
    ("contract-shadow-param",
     'shape S = @{x: num}\nfn outer() { let S = @{__shape: 5, a: "num"}\n'
     'fn g(p: S) { 0 }\ng(1) }\nlet r = outer()'),
    # --- b_sure ----------------------------------------------------------
    ("sure-propagated",   'let r = sure(num("x"), 0.5)'),
    ("sure-threshold-str", 'let r = sure(5, "x")'),
    ("sure-threshold-high", 'let r = sure(guess(5, 0.9, "m"), 2)'),
    ("sure-threshold-rec", 'let r = sure(5, @{a: 1})'),
    ("sure-below",  'let r = sure(guess(5, 0.2, "m"), 0.9)'),
    # --- b_get: the two key-side guards ----------------------------------
    ("get-key-missed",   'let r = get(@{a: 1}, num("x"))'),
    ("get-key-num",      'let r = get(@{a: 1}, 5)'),
    ("get-key-record",   'let r = get("a", @{a: 1})'),
    # --- _field: reached THROUGH get, so get(r,"a") == r.a node for node --
    ("field-absent",     'let r = get(@{a: 1}, "b")'),
    ("field-non-record", 'let r = get(5, "a")'),
    ("field-record-missed", 'let r = get(num("x"), "a")'),
    ("field-non-record-str", 'let r = get("hi", "a")'),
    ("field-on-fn",      'let f = fn(z) { z }\nlet r = get(f, "a")'),
    # --- apply: one renderer, every value slot ---------------------------
    ("call-non-callable-str", 'let f = "hi"\nlet r = f(1)'),
    ("call-non-callable-num", 'let f = 5\nlet r = f(1)'),
    ("call-non-callable-rec", 'let f = @{a: 1}\nlet r = f(1)'),
    # Round 362's exemption E3, PROMOTED to a required agreement by v0.28
    # (round 372). E3 read "a design call handed to a future language(C)
    # round with this case as the repro"; the whole-surface sweep found 14
    # more instances of the same box-instead-of-payload class, and
    # `self_eval.lang` now re-renders a delegated builtin's miss from
    # deep-stripped arguments. `test_each_exemption_is_load_bearing` is
    # what forced this edit: it went red the moment the divergence stopped
    # existing, which is exactly what round 362 wrote it to do.
    ("push-order-hint", 'let r = push(1, [2])'),
    # Round 362's exemptions E1 (`show_payload`'s CAPS) and E2 (`_quote`'s
    # ESCAPES), PROMOTED to required agreements by v0.29 (round 374). Both
    # said the same thing: "the guest's renderer is the `str` builtin, which
    # is `full_show`, and no Whence expression can reach those constants".
    # Decision 37 made that false by adding one — `show` IS `show_payload`,
    # so `show_val` delegates the rendering instead of approximating it, and
    # the caps and the escapes come with it. Same mechanism as
    # `push-order-hint` above: `test_each_exemption_is_load_bearing` went
    # red the moment the divergence stopped existing.
    ("render-cap",
     'let r = typed(1, @{alpha: 5, beta: 5, gamma: 5, delta: 5, eps: 5}, '
     '"L")'),
    ("render-escape", 'let r = sure(5, "a\\"b")'),
]

# Valid programs, so rule 1 is a biconditional and not a test that only ever
# sees the failing half.
GOOD = [
    ("good-typed-prim",   'let r = typed(1, "num", "L")'),
    ("good-typed-any",    'let r = typed(fn(z) { z }, "any", "L")'),
    ("good-typed-shape",
     'shape P = @{x: num}\nlet r = typed(@{x: 1}, P, "L")'),
    ("good-typed-handbuilt", 'let r = typed(@{a: 1}, @{a: "num"}, "L")'),
    ("good-typed-wide",   'let r = typed(@{a: 1, b: 2}, @{a: "num"}, "L")'),
    ("good-contract",     'fn g(p: num) -> num { p }\nlet r = g(1)'),
    ("good-sure",         'let r = sure(guess(5, 0.9, "m"), 0.5)'),
    ("good-get",          'let r = get(@{a: 1}, "a")'),
]

# Three enumerated divergences. Each is asserted load-bearing in BOTH
# directions by `test_each_exemption_is_load_bearing`: if the host and guest
# ever agree on one, the exemption fails and must be DELETED, not adjusted.
EXEMPT = {}
# E1 ("exempt-render-cap") and E2 ("exempt-render-escape") were DELETED by
# v0.29 (round 374), which closed them, and their cases moved to `BAD`.
# Both rested on the same premise — "the guest's renderer is the `str`
# builtin, which is `full_show` (limit=None), and no Whence expression can
# reach those constants" — and both were true only for as long as the
# language had no way to ask for the SNAPSHOT rendering. Decision 37 added
# `show`, which is `show_payload` itself, so the caps (40 chars, 12 per
# nested element, 6 items, 4 fields, 3 levels) and `_quote`'s escapes now
# reach the guest by delegation rather than by re-implementation. This
# corpus is now exemption-FREE: every case must agree.
# E3 ("exempt-push-order-hint") was DELETED by v0.28 (round 372), which
# closed it. Round 362 described it as "a design call handed to a future
# language(C) round with this case as the repro" and predicted the fix
# would mean "the guest stops delegating `push`'s guard and builds the
# message itself, on the hot path of its own interpretation loop". That
# prediction was wrong in a useful way: the fix keeps the delegation and
# adds a SECOND delegated call, on the miss path only, with deep-stripped
# arguments — so the hot path is untouched and the whole 15-case class
# (not just `push`) closes at once. `push(1, [2])` now lives in `BAD`.

EXEMPT_CASES = []


# --------------------------------------------------------------------------
# running both sides
# --------------------------------------------------------------------------

ALL = BAD + GOOD + EXEMPT_CASES


def host_reason(src):
    """The host's first miss reason for `r`, position clause stripped, or
    None when `r` is not a miss."""
    env = Interpreter().run(src)
    box = env.get("r")
    assert box is not None, src
    if not isinstance(box.payload, Miss):
        return None
    return LINE_SUFFIX.sub("", box.payload.reasons[0])


@pytest.fixture(scope="module")
def guest_reasons():
    """One host run: the guest library, then one `run_src` per case."""
    parts = [library_source()]
    for i, (_, src) in enumerate(ALL):
        parts.append('let __out%d = run_src("%s")\n' % (i, escape(src)))
    env = Interpreter().run("".join(parts))
    out = {}
    for i, (name, _) in enumerate(ALL):
        rec = env.get("__out%d" % i)
        assert rec is not None, name
        payload = rec.payload.fields["v"].payload
        out[name] = (LINE_SUFFIX.sub("", payload.reasons[0])
                     if isinstance(payload, Miss) else None)
    return out


@pytest.fixture(scope="module")
def host_reasons():
    return {name: host_reason(src) for name, src in ALL}


# --------------------------------------------------------------------------
# rule 1 — missed-ness agrees
# --------------------------------------------------------------------------

def test_missedness_agrees_on_every_case(host_reasons, guest_reasons):
    bad = [(n, host_reasons[n], guest_reasons[n]) for n, _ in ALL
           if (host_reasons[n] is None) != (guest_reasons[n] is None)]
    assert bad == [], bad


def test_the_corpus_exercises_both_outcomes(host_reasons):
    missed = [n for n, _ in ALL if host_reasons[n] is not None]
    clean = [n for n, _ in ALL if host_reasons[n] is None]
    assert len(missed) >= 55, len(missed)
    assert len(clean) >= 8, len(clean)


# --------------------------------------------------------------------------
# rule 2 — the wording agrees, except where enumerated
# --------------------------------------------------------------------------

def test_the_wording_agrees_host_vs_guest(host_reasons, guest_reasons):
    bad = []
    for name, _ in BAD:
        h, g = host_reasons[name], guest_reasons[name]
        if h != g:
            bad.append((name, h, g))
    assert bad == [], bad


def test_each_exemption_is_load_bearing(host_reasons, guest_reasons):
    """An exemption that no longer describes a real difference is a lie in
    the corpus. Every entry must still DIVERGE; if one stops, delete it."""
    agreed = [(n, host_reasons[n]) for n, _ in EXEMPT_CASES
              if host_reasons[n] == guest_reasons[n]]
    assert agreed == [], (
        "these exemptions no longer describe a divergence — delete them "
        "rather than keep them: %s" % agreed)
    assert set(EXEMPT) == {n for n, _ in EXEMPT_CASES}


def test_the_cap_and_the_escape_are_now_agreements(host_reasons,
                                                   guest_reasons):
    """v0.29 (round 374) closed round 362's two rendering exemptions. The
    old test asserted the guest did NOT truncate; this one asserts it does,
    and that it escapes — the direction reversed, deliberately, so the
    closure is pinned rather than merely un-asserted. Both cases are in
    `BAD` now, so `test_every_bad_case_agrees` already requires equality;
    what this adds is that the equality is the INTERESTING one (a truncated
    rendering, an escaped rendering) and not two empty strings."""
    short = 'let r = typed(1, @{alpha: 5, beta: 5, gamma: 5}, "L")'
    assert host_reason(short) == _guest_reason_of(short)
    assert "\u2026" not in host_reason(short)          # below the cap: no cut

    cap = host_reasons["render-cap"]
    assert "\u2026" in cap, cap                        # above it: cut
    assert guest_reasons["render-cap"] == cap

    esc = host_reasons["render-escape"]
    assert '\\"' in esc, esc                           # the quote is escaped
    assert guest_reasons["render-escape"] == esc


def _guest_reason_of(src):
    parts = [library_source(), 'let __o = run_src("%s")\n' % escape(src)]
    env = Interpreter().run("".join(parts))
    payload = env.get("__o").payload.fields["v"].payload
    return (LINE_SUFFIX.sub("", payload.reasons[0])
            if isinstance(payload, Miss) else None)


# --------------------------------------------------------------------------
# rule 3 — the corpus reaches every host site
# --------------------------------------------------------------------------

# Every host function that BUILDS a type/contract message. `_propagate` is
# shared machinery, so a miss it builds is attributed to the TYPE_FN that
# called it (see `_site_of`).
TYPE_FNS = ("_check_contract", "b_typed", "b_sure", "b_get", "_field")

# Declared-but-unreachable, with the reason. Not a laxity: a site listed
# here must still exist in the source, and `test_every_unreachable_site_
# still_exists` fails if one is deleted or renamed out from under this list.
UNREACHABLE = {
    "_check_contract:_UnboundType":
        "v0.18 (round 342) made `parse_type` scope-aware, so an annotation "
        "naming a shape whose block has closed is a PARSE error at the "
        "annotation's own line and no source text reaches the sentinel. "
        "`_UnboundType`'s own docstring says so and keeps it as the floor "
        "under `_closure_spec`, which resolves in Python and would RAISE "
        "on a None binding (round 128 found exactly that AttributeError).",
}


def declared_sites():
    """Every `mk_miss`/`merge_miss`/`_propagate` call inside a TYPE_FN, read
    off the AST. Keyed by (function, line) — one generic site can absorb a
    dozen cases, so counting CASES would not measure coverage."""
    tree = ast.parse(open(INTERP_PY, encoding="utf-8").read())
    found = set()

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node):
            nm = getattr(node.func, "id", None) or getattr(node.func, "attr",
                                                           None)
            if (nm in ("mk_miss", "merge_miss", "_propagate")
                    and self.stack and self.stack[-1] in TYPE_FNS):
                found.add((self.stack[-1], node.lineno))
            self.generic_visit(node)

    V().visit(tree)
    return found


def observed_sites():
    """The sites this corpus actually reaches, captured by wrapping the two
    miss constructors and walking the stack for the innermost TYPE_FN."""
    import whence.interp as I
    seen = set()
    originals = (I.mk_miss, I.merge_miss)

    def wrap(fn):
        def w(*a, **k):
            stack = traceback.extract_stack()
            interp_frames = [f for f in stack
                             if os.path.abspath(f.filename) == INTERP_PY]
            for fr in reversed(interp_frames):
                if fr.name in TYPE_FNS:
                    seen.add((fr.name, fr.lineno))
                    break
            return fn(*a, **k)
        return w

    I.mk_miss, I.merge_miss = wrap(originals[0]), wrap(originals[1])
    try:
        for _, src in ALL:
            Interpreter().run(src)
    finally:
        I.mk_miss, I.merge_miss = originals
    return seen


def test_the_corpus_reaches_every_host_contract_message_site():
    declared = declared_sites()
    assert len(declared) >= 12, sorted(declared)
    reached = observed_sites()
    unreachable_lines = {
        line for (fn, line) in declared
        if fn == "_check_contract" and _is_unbound_site(line)}
    missing = sorted(s for s in declared
                     if s not in reached and s[1] not in unreachable_lines)
    assert missing == [], (
        "the corpus reaches %d of %d host contract-message sites; add a "
        "case for %s" % (len(reached & declared), len(declared), missing))


def _is_unbound_site(line):
    """The `_UnboundType` branch of `_check_contract`, located by reading
    the source rather than by pinning a line number."""
    src = open(INTERP_PY, encoding="utf-8").read().split("\n")
    for i in range(max(0, line - 4), line):
        if "_UnboundType" in src[i]:
            return True
    return False


def test_every_unreachable_site_still_exists():
    """`UNREACHABLE` names a real branch. If a future round deletes the
    `_UnboundType` guard, this fails instead of the exclusion quietly
    covering nothing."""
    src = open(INTERP_PY, encoding="utf-8").read()
    assert "isinstance(spec, _UnboundType)" in src
    assert len(UNREACHABLE) == 1


# --------------------------------------------------------------------------
# decision 35, stated as a test rather than as prose
# --------------------------------------------------------------------------

NAME_SLOT_CASES = [
    ('@{__shape: "Pt", a: "num"}', "Pt"),      # a name IS a string
    ('@{__shape: 5, a: "num"}', "record"),     # everything else is anonymous
    ('@{__shape: true, a: "num"}', "record"),
    ('@{__shape: [1, 2], a: "num"}', "record"),
    ('@{__shape: @{q: 1}, a: "num"}', "record"),
    ('@{__shape: num("x"), a: "num"}', "record"),
    ('@{a: "num"}', "record"),                 # no `__shape` at all
    ('@{__shape: "", a: "num"}', ""),          # the empty string IS a name
]


def test_a_name_slot_holds_a_name_or_says_record():
    for spec, want in NAME_SLOT_CASES:
        reason = host_reason('let r = typed(1, %s, "L")' % spec)
        assert reason == "L expected %s, got num" % want, (spec, reason)


def test_a_non_string_shape_never_renders_a_payload_into_the_message():
    """The property round 335's `show_payload` call was reaching for, now
    obtained by not rendering at all: no payload text and, a fortiori, no
    Python repr and no heap address."""
    for spec, _ in NAME_SLOT_CASES[1:7]:
        reason = host_reason('let r = typed(@{a: "z"}, %s, "L")' % spec)
        assert "object at 0x" not in reason, reason
        assert reason.startswith("L expected record, got record"), reason


def test_a_matching_record_still_matches_a_spec_with_a_non_string_name():
    """Decision 35 is about the MESSAGE. `_spec_ok` still ignores
    `__shape`, so structural matching is untouched — a record that fits
    still fits, which is what "structural, not nominal" means."""
    env = Interpreter().run(
        'let r = matches(@{a: 1}, @{__shape: 5, a: "num"})\n')
    assert env.get("r").payload is True
    env = Interpreter().run(
        'let r = typed(@{a: 1}, @{__shape: 5, a: "num"}, "L")\n')
    assert not isinstance(env.get("r").payload, Miss)
