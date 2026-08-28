"""Self-hosting round 6 (round 192): does the guest EVALUATOR (self_eval.lang,
running under the host) correctly run the guest LEXER+PARSER (self_host.lang),
on self_host.lang's own real, ~680-line source — not a hand-picked corpus
snippet?

Two levels are tested, cheapest first:

  1. `test_guest_parser_parses_its_own_full_source`: self_eval.lang's own
     copy of the shared lexer+parser (called directly, host-level — same
     cost as running self_host.lang itself) parses self_host.lang's ENTIRE
     source text as one string. This is what actually caught the bug this
     round fixed (see below) — it fails fast on any lex/parse divergence
     without needing a full guest-level evaluation pass.

  2. `test_guest_evaluator_executes_self_host_library`: the real, deeper
     claim — self_eval.lang's `run_src` (parse AND eval, guest-side) loads
     self_host.lang's ~530-line library section as GUEST closures and
     EXECUTES check statements that call into them recursively. This is two
     full levels of tree-walking interpretation (host -> self_eval.eval ->
     self_host's own `lex`/`parse_expr` etc, now guest data) and is
     deliberately kept small (a handful of checks, not all 66 of
     self_host.lang's own) because the cost is real: an attempt to run
     self_host.lang's FULL 66-check test section through run_src grew past
     1.7 GB RSS and was still climbing after 3 minutes on this machine's
     3.8 GB budget before being killed — a genuine, first-measured data
     point on how guest-level tree-walking cost compounds on a real (not
     synthetic-tiny) guest program, not attempted here. See the round-192
     knowledge file for the raw numbers.

Bug found by test 1, before either test existed: self_host.lang's guest
lexer's `suppressed()` only implemented HALF of whence/lexer.py's newline-
continuation rule (bracket depth), missing the other half (a newline right
after an operator/`=`/`:`/`,`/`and`/`or`/`not`/`rescue` is ALSO a
continuation, independent of brackets — see whence/lexer.py's own module
docstring). self_host.lang's own test section uses exactly this style
(`check "label":` with the boolean on the next line) and round-trips fine
under the HOST, but was an unconditional parse_error under the GUEST. Fixed
in both self_host.lang and self_eval.lang's byte-identical copy (round 192).

Round 228: found and fixed a SEPARATE, much larger cost trap than the one
described above, this one specific to `steps()`/`blame()`/`at()`/
`diverge()`. Those builtins delegate to the real host builtin on a guest
value's `.v` field (round 206/218's free-delegation fix) — but that `.v`
is the HOST-level Prov produced by running self_eval.lang's OWN
interpreter (host-level) up to that point, and self_eval.lang is a
STORE-PASSING evaluator: its `st` argument is threaded through virtually
every internal call as a real (not spurious) dataflow input, so it
legitimately appears in the `ins` chain of whatever value comes out.
Once self_host.lang's ~530-line library has been loaded (defining ~40
guest functions), `st`'s own provenance graph encodes the ENTIRE
host-level trace of interpreting all of that — and `steps()` walks the
full DAG reachable from its argument, so it walks that whole trace, NOT
just "how was this specific value derived." Measured directly: calling
`steps()` on `bad = miss "x"` (a trivial guest literal with no real
complexity of its own) right after the library loads costs the *same*
order of magnitude as calling it on a value produced by parsing
self_host.lang's own source (>1.35 GB RSS, still growing linearly with
no plateau after 5 minutes wall-clock, in both cases) — proving the cost
tracks the EVALUATOR's cumulative work, not the target value's own
semantic complexity. This is a real, large, but *finite* DAG walk (no
algorithmic bug found: `walk_steps` correctly dedupes by `id()`, is not
exponential) — it is simply enormous once the library is loaded, an
architectural property of store-passing self-hosting, not something to
fix here (mirrors round 206/216/227's own explicit "not a regression to
fix" stance on the smaller version of this cost). The two tests below
were restructured so the DEFAULT suite never pays this cost: the
`steps(p2)` check that used to live in
`test_guest_evaluator_executes_self_host_library` was removed outright
(redundant — dispatch-correctness for `steps` is proven elsewhere without
the expensive library-loaded context), and
`test_guest_steps_two_arg_pattern_and_total_on_miss` now exercises the
identical dispatch/totality/narrowing claims against a small arithmetic
guest value instead of a `parse_whence(...)`-produced AST — proving guest
`steps()` dispatch is correct without needing self_host.lang's library
loaded at all (0.6-3s / <40 MB instead of minutes / gigabytes, verified
empirically before and after). See the round-228 knowledge file for the
raw measurements and the isolation experiments that found this.
"""

import os
import sys

from whence.interp import Interpreter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
SELF_HOST = os.path.join(ROOT, "examples", "self_host.lang")
EFFECTS = os.path.join(ROOT, "examples", "effects.lang")
MARKER = "# ==== SELF-TESTS"
LIB_START, LIB_END = 27, 561  # self_host.lang lines 28..561 (0-indexed slice)


def eval_library_source():
    src = open(EXAMPLE).read()
    assert MARKER in src
    return src.split(MARKER)[0]


def self_host_library_section():
    lines = open(SELF_HOST).read().splitlines(keepends=True)
    section = "".join(lines[LIB_START:LIB_END])
    assert section.startswith("# ---- character classes")
    assert section.rstrip().endswith(
        "fn parse_whence(src) { parse_program(lex_all(src)) }")
    return section


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
              .replace("\n", "\\n").replace("\t", "\\t"))


def test_guest_parser_parses_its_own_full_source():
    # self_eval.lang's copy of parse_whence, called directly (host-level,
    # same cost class as running self_host.lang itself), fed self_host.lang's
    # ENTIRE real source as one string.
    eval_lib = eval_library_source()
    host_src = open(SELF_HOST).read()
    prog = (eval_lib +
            'let __ast = parse_whence("%s")\n' % escape(host_src) +
            'let __ok = not missed(__ast)\n'
            'let __nstmts = if __ok { len(__ast.stmts) } else { -1 }\n')
    env = Interpreter().run(prog)
    ok = env.get("__ok").payload
    assert ok is True, (env.get("__ast").payload.reasons
                         if not ok else None)
    # self_host.lang currently parses to 154 top-level statements; pin the
    # exact count so a silent structural regression (e.g. two statements
    # merging into one) fails loudly even though `__ok` alone would not
    # catch it.
    assert env.get("__nstmts").payload == 154


def test_guest_evaluator_executes_self_host_library():
    # The real claim: self_eval's `run_src` (parse + EVAL, guest-side)
    # loads self_host.lang's library as guest closures and runs check
    # statements that call into them — two full levels of interpretation.
    eval_lib = eval_library_source()
    lib_section = self_host_library_section()
    inner_checks = "\n".join([
        'let lx = lex_all("let x = 1 + 2")',
        'check "lexer token count": len(lx) == 7',
        # round 192's fix, exercised at the guest-EVAL level specifically
        # (test_guest_parser_parses_its_own_full_source above only proves
        # the parser, called directly, handles it — this proves the
        # GUEST's own interpreted copy of the same function does too):
        'check "newline after binop is a continuation":\n'
        '  not contains(map(fn(t) { t.t }, lex_all("1 +\\n2")), "nl")',
        'let p1 = parse_whence("let x = 1 + 2 * 3")',
        'check "parses without error": not missed(p1)',
        'let p2 = parse_whence("fn go(n) { if n == 0 { 0 } else { go(n - 1) } }")',
        'check "recursive fn body parses": not missed(p2)',
    ])
    # round 228: this test used to also assert
    # `not missed(p2) and len(steps(p2)) > 0` here (added round 206, when
    # `steps` first gained guest dispatch) — removed. It cost >1.35 GB RSS
    # and minutes of wall-clock with no plateau observed (see module
    # docstring: `steps()` on ANY value walks self_eval.lang's entire
    # store-threaded interpretation trace once the library is loaded, not
    # just the target value's own derivation), and it proved nothing that
    # `test_guest_steps_two_arg_pattern_and_total_on_miss` below doesn't
    # already prove more cheaply and more directly.
    inner_src = lib_section + "\n" + inner_checks + "\n"
    prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)

    env = Interpreter().run(prog)
    rec = env.get("__r").payload
    assert rec.fields["parse_error"].payload is False
    checks = rec.fields["checks"].payload
    assert len(checks) == 4
    failed = [c.payload.fields["label"].payload for c in checks
              if c.payload.fields["pass"].payload is not True]
    assert not failed, failed


def test_guest_steps_two_arg_pattern_and_total_on_miss():
    # round 206: beyond the 1-arg form pinned above, self_eval.lang's guest
    # `steps` dispatch (`arities.steps = -1`, mirroring host's `(1, 2)`)
    # also accepts a 2-arg pattern-filter form, and must stay TOTAL (work
    # on a miss argument) like the real host builtin does — neither shape
    # is exercised by self_host.lang's own test corpus, so this is the only
    # coverage for them.
    #
    # round 228: this test originally ran `parse_whence(...)` against
    # self_host.lang's real library (loaded via `lib_section` below) before
    # calling `steps()` on the result. Measured cost: >1.35 GB RSS, still
    # growing linearly after 5 minutes wall-clock with no plateau observed
    # (see the module docstring's round-228 note) — NOT because the parsed
    # AST is complex, but because `steps()` walks self_eval.lang's entire
    # store-threaded interpretation trace once the library is loaded, and
    # that trace is what's expensive, regardless of the target value.
    # Confirmed directly: `steps()` on a trivial `miss "x"` literal in that
    # same loaded-library context costs the *same* order of magnitude. What
    # this test actually needs to prove — guest `steps()` dispatch is
    # correct (2-arg narrowing, totality on a miss) — does not depend on
    # self_host.lang's library at all, so it no longer loads it: `p` below
    # is a small arithmetic guest expression, evaluated directly by
    # self_eval.lang without ever calling `parse_whence`. Verified this
    # stays a real, non-trivial differential proof (not coverage theater):
    # `all_steps`/`go_steps` are real `steps()` results over a real guest
    # binop-chain derivation, not stubs.
    eval_lib = eval_library_source()
    inner_checks = "\n".join([
        'let p = 1 + 2 + 3',
        'let all_steps = steps(p)',
        'let narrow_steps = steps(p, "binop +")',
        'check "2-arg pattern form narrows, never widens":\n'
        '  len(narrow_steps) <= len(all_steps)',
        'let bad = miss "deliberately broken"',
        'check "steps is total: a miss has its own (short) history too":\n'
        '  len(steps(bad)) > 0',
    ])
    inner_src = inner_checks + "\n"
    prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)

    env = Interpreter().run(prog)
    rec = env.get("__r").payload
    assert rec.fields["parse_error"].payload is False
    checks = rec.fields["checks"].payload
    assert len(checks) == 2
    failed = [c.payload.fields["label"].payload for c in checks
              if c.payload.fields["pass"].payload is not True]
    assert not failed, failed


def test_guest_at_blame_diverge_contrast_dispatch_to_real_host_builtins():
    # round 218: closes the follow-up backlog round 206's own knowledge file
    # flagged when it fixed `steps`'s guest-parity gap -- `at`/`blame`/
    # `diverge`/`contrast` are the same "provenance as data" (round 4)
    # family, share the identical NAME-RESOLUTION gap (never in
    # `builtin_names`, so guest code calling them failed before dispatch
    # was ever reached), and get the identical free-delegation fix. This
    # test is the exercising code that makes the gap real per the corpus's
    # own "evaluate-before-authoring" convention -- self_host.lang's own
    # source still calls none of these four, so without a test like this
    # nothing in the corpus would ever exercise the fix.
    #
    # Real host-derivation "labels" seen here are self_eval.lang's OWN
    # internal call chain (its parameter names, its own eval helpers), not
    # anything about the guest program's syntax -- confirmed empirically:
    # `diverge(1 + 2, 1 + 2)` (same literal, twice) still reports one
    # origin, because the two evaluations run through different internal
    # call paths inside self_eval.lang itself. So assertions below avoid
    # exact-pattern-match / same-vs-different-divergence-count claims and
    # instead pin properties true regardless of that internal noise: the
    # real host MISS WORDING for a not-found `at` search (the pre-fix guest
    # stub returned a completely different "not implemented in the guest"
    # message, so seeing the real host wording proves the real builtin
    # ran), and non-empty/positive-length results proving each builtin
    # actually walked real provenance rather than crashing or silently
    # falling through to the catch-all stub.
    eval_lib = eval_library_source()
    inner_checks = "\n".join([
        'let bad = miss "deliberate"',
        'check "blame finds at least its own origin miss": len(blame(bad)) >= 1',
        'let missing = at(bad, "nonexistent-pattern-xyz")',
        'check "at reaches the real host builtin, not the guest stub":\n'
        '  contains(str(missing), "no step named")',
        'check "diverge finds at least one origin for two different literals":\n'
        '  len(diverge(1 + 2, 1 + 3)) >= 1',
        'check "contrast renders a non-empty report":\n'
        '  len(contrast(1 + 2, 1 + 3)) > 0',
    ])
    inner_src = inner_checks + "\n"
    prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)

    env = Interpreter().run(prog)
    rec = env.get("__r").payload
    assert rec.fields["parse_error"].payload is False
    checks = rec.fields["checks"].payload
    assert len(checks) == 4
    failed = [c.payload.fields["label"].payload for c in checks
              if c.payload.fields["pass"].payload is not True]
    assert not failed, failed


def test_guest_at_blame_diverge_contrast_total_on_miss_arguments():
    # round 218: host interp.py documents this whole family as TOTAL (works
    # on a miss argument -- walking a failed value's own history is the
    # point, matching `steps`'s own total-on-miss test above). Pins each
    # builtin's specific total-vs-propagating shape: `at`'s VALUE argument
    # being a miss still gets searched for real (not short-circuited), but
    # its PATTERN argument being a miss DOES propagate (`merge_miss`, per
    # host `b_at`); `diverge`/`contrast` still produce a real, non-empty
    # result when one side of the comparison is a miss.
    eval_lib = eval_library_source()
    inner_checks = "\n".join([
        'let bad = miss "deliberate"',
        'check "at is total on its value argument: still a real search":\n'
        '  contains(str(at(bad, "nonexistent-pattern-xyz")), "no step named")',
        'check "at propagates when its PATTERN argument is a miss":\n'
        '  missed(at(1 + 2, bad))',
        'check "diverge is total: a miss on one side still returns real origins":\n'
        '  len(diverge(bad, 1 + 2)) >= 1',
        'check "contrast is total: a miss on one side still renders":\n'
        '  len(contrast(bad, 1 + 2)) > 0',
    ])
    inner_src = inner_checks + "\n"
    prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)

    env = Interpreter().run(prog)
    rec = env.get("__r").payload
    assert rec.fields["parse_error"].payload is False
    checks = rec.fields["checks"].payload
    assert len(checks) == 4
    failed = [c.payload.fields["label"].payload for c in checks
              if c.payload.fields["pass"].payload is not True]
    assert not failed, failed


def test_guest_steps_blame_diverge_element_field_access():
    # round 222: round 218's own knowledge file flagged a fresh, narrower
    # gap it deliberately left open -- `eval_index`'s list-passthrough
    # branch (self_eval.lang) assumes every host list handed back across
    # the guest boundary already has its elements in the guest `{v, op,
    # ins}` box shape, which is true for guest-BUILT lists but false for
    # `steps`/`blame`/`diverge`'s elements: the host's `_step_record`
    # (interp.py) is a real host Record with fields op/detail/line/show/
    # depth/inputs/count/value, none individually boxed, because host-level
    # field access never needed the guest's box convention. Before this
    # round, `steps(x)[0].op` failed guest-side with "miss: no field 'v'
    # (record has: count, depth, detail, inputs, line, op, show, value)" --
    # every check below indexes an element AND reads a field off it (not
    # just `len(...)` of the list, which is all rounds 206/218 exercised),
    # so this is real exercising code for the fix, not a retroactive pin.
    # `diverge`'s elements nest a SECOND, structurally different unboxed
    # record shape (`kind`/`a`/`b`[/`which`]) one level down, with `a`/`b`
    # themselves raw `_step_record`s -- the last two checks below are the
    # only coverage of that nested case.
    eval_lib = eval_library_source()
    inner_checks = "\n".join([
        'let x = 1 + 2',
        'let s = steps(x)',
        'check "steps element .op reads back, not a miss, after indexing":\n'
        '  not missed(s[0].op)',
        'check "steps element .op is the real first-walked step label":\n'
        '  s[0].op == "let"',
        'check "steps element descriptive fields are all readable":\n'
        '  not missed(s[0].detail) and not missed(s[0].line) and\n'
        '  not missed(s[0].depth) and not missed(s[0].inputs) and\n'
        '  not missed(s[0].count) and not missed(s[0].value)',
        'let bl = blame(miss "deliberate")',
        'check "blame element .value reads back and is itself a miss":\n'
        '  missed(bl[0].value)',
        'let d = diverge(1 + 2, 1 + 3)',
        'check "diverge element .kind reads back, not a miss":\n'
        '  not missed(d[0].kind)',
        'let d2 = diverge([1 + 2, 1 + 3, 1 + 4])',
        'check "n-way diverge element .which is the real diverging run index":\n'
        '  d2[0].which == 1',
        'check "diverge element .a/.b are step-shaped: their own .op reads back":\n'
        '  not missed(d[0].a.op) and not missed(d[0].b.op)',
    ])
    inner_src = inner_checks + "\n"
    prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)

    env = Interpreter().run(prog)
    rec = env.get("__r").payload
    assert rec.fields["parse_error"].payload is False
    checks = rec.fields["checks"].payload
    assert len(checks) == 7
    failed = [c.payload.fields["label"].payload for c in checks
              if c.payload.fields["pass"].payload is not True]
    assert not failed, failed


def test_guest_matches_shapeof_dispatch_and_callable_guard():
    # round 224: `matches`/`shapeof` (v0.12 structural types) were never in
    # self_eval.lang's `builtin_names` at all -- guest code calling either
    # failed at NAME RESOLUTION ("unbound name"), never even reaching
    # `apply_builtin`/`apply_host_builtin`'s dispatch tables, the same gap
    # class rounds 206 (`steps`) and 218 (`at`/`blame`/`diverge`/`contrast`)
    # already found and fixed for the rest of this builtin family. Both are
    # TOTAL and return scalar payloads, so free delegation to the real host
    # builtin applies -- EXCEPT for a callable value, where undguarded
    # delegation reports "record" (a guest closure is an ordinary tagged
    # Record under the hood, not a real host `Closure` object) instead of
    # "fn"; checks below cover both the plain-delegation path (every other
    # kind) and the callable-guard path explicitly, not just name
    # resolution succeeding.
    eval_lib = eval_library_source()
    inner_checks = "\n".join([
        'check "matches a num spec against a num": matches(1, "num")',
        'check "matches a str spec against a num is false": not matches(1, "str")',
        'check "matches any always matches": matches([1, 2], "any")',
        'check "matches is total: a miss argument is just false, not itself a miss":\n'
        '  matches(miss "x", "num") == false',
        'check "shapeof a number": shapeof(1) == "num"',
        'check "shapeof a list": shapeof([1, 2]) == "list"',
        'check "shapeof a record": shapeof(@{a: 1}) == "record"',
        'check "shapeof a miss": shapeof(miss "x") == "miss"',
        'check "shapeof a string": shapeof("hi") == "str"',
        'check "shapeof a bool": shapeof(true) == "bool"',
        'check "shapeof a guess": shapeof(guess(1, 0.5, "s")) == "guess"',
        'let f = fn(x) { x }',
        'check "shapeof a guest closure reports fn, not record (the callable guard)":\n'
        '  shapeof(f) == "fn"',
        'check "matches fn spec against a guest closure (the callable guard)":\n'
        '  matches(f, "fn")',
        'check "matches fn spec against a non-callable value is false":\n'
        '  not matches(1, "fn")',
        'check "matches any still matches a guest closure":\n'
        '  matches(f, "any")',
    ])
    inner_src = inner_checks + "\n"
    prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)

    env = Interpreter().run(prog)
    rec = env.get("__r").payload
    assert rec.fields["parse_error"].payload is False
    checks = rec.fields["checks"].payload
    assert len(checks) == 15
    failed = [c.payload.fields["label"].payload for c in checks
              if c.payload.fields["pass"].payload is not True]
    assert not failed, failed


def test_effects_lang_runs_under_the_guest_round_164_backlog_closed():
    # round 164 (SPEC.md "v0.14 guest parity") found run_src(effects.lang)
    # reported parse_error precisely because of one multi-line `check
    # "...":\n  expr` statement (line 45-46, still present, unchanged) and
    # explicitly deferred the fix as backlog rather than build it behind
    # that round's actual feature. Round 192's fix (the same one the two
    # tests above pin) closes it: the whole file, verbatim, now parses AND
    # evaluates cleanly under the guest, all 4 of its own checks passing.
    eval_lib = eval_library_source()
    effects_src = open(EFFECTS).read()
    prog = eval_lib + 'let __r = run_src("%s")\n' % escape(effects_src)
    env = Interpreter().run(prog)
    rec = env.get("__r").payload
    assert rec.fields["parse_error"].payload is False
    checks = rec.fields["checks"].payload
    assert len(checks) == 4
    failed = [c.payload.fields["label"].payload for c in checks
              if c.payload.fields["pass"].payload is not True]
    assert not failed, failed


def test_guest_miss_unary_why_shape_matches_host_for_all_three_reason_kinds():
    # round 210: harness/swe/guest.py's why-shape fuzzer (round 20's
    # containment probe: every guest-reified `why` op must appear in the
    # real host derivation's op set) found a real mirroring bug at seed 152
    # -- flagged in round 206's knowledge file, not fixed there. Root
    # cause: self_eval.lang's `eval_unary` "miss" branch unconditionally
    # kept the operand as a why-input (`mkb(miss r.v.v, "miss", [r.v])`),
    # but the host's own `_miss_lit` (interp.py) only keeps it when the
    # reason is a miss (propagate) or a valid string -- a non-string,
    # non-miss reason (e.g. `miss 1`) discards the operand and yields a
    # fresh 0-input miss node. The guest's old unconditional behaviour
    # invented a "literal" op the host derivation never has for that third
    # case. This test pins host/guest op-set containment directly for all
    # three reason shapes (was previously only exercised indirectly, and
    # not at all for the non-string case, by the differential fuzzer).
    from whence import values as VAL

    eval_lib = eval_library_source()
    cases = {
        "string reason": 'miss "deliberate"',
        "non-string reason (the bug)": "miss 1",
        "miss reason (propagate)": 'miss (miss "inner")',
    }
    for label, expr in cases.items():
        host_env = Interpreter().run("let v = %s\n" % expr)
        host_box = host_env.get("v")
        host_ops = set(node.op for node, _ in VAL.walk_steps(host_box))

        inner_src = (
            'let v = %s\n'
            'fn __opwalk(acc, n) { fold(__opwalk, push(acc, n.op), n.ins) }\n'
            'let __ops = __opwalk([], why v)\n'
            '__ops\n') % expr
        prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)
        genv = Interpreter().run(prog)
        rec = genv.get("__r").payload
        assert rec.fields["parse_error"].payload is False, label
        guest_ops = set(e.payload.split(" ")[0] for e in rec.fields["v"].payload)

        extra = guest_ops - host_ops
        assert not extra, (label, "guest-only ops", sorted(extra),
                            "host ops", sorted(host_ops))


def test_guest_sure_why_shape_matches_host_exactly_including_flattening():
    # Round 194 fixed `sure()`'s plain-value pass-through (a non-Guess is
    # always a no-op escape hatch) but left the two Guess-CARRYING cases
    # -- above-threshold pass-through (host: `g.node`, bypassing every
    # later `let`/`guess` wrapper) and below-threshold miss (host:
    # `mk_miss(..., inputs=(v,))`, the VALUE's own derivation only, never
    # the threshold's) -- deliberately unfixed, reasoning there was no
    # fuzzer finding on that path yet. Round 234 found both gaps are real
    # by direct construction: `sure`/`guess` are absent from
    # `harness/swe/guest.py`'s `WHY_VOCAB`, and the tokens the old guest
    # code DID leak that ARE in that vocabulary ("literal") already
    # legitimately appear elsewhere in the host derivation -- so the
    # differential fuzzer's containment-only probe could never have
    # caught either gap regardless of how long it ran. This test compares
    # the exact host/guest op LIST (not just set containment) across five
    # shapes, including two the guest's own fix has to trace through
    # (a `let`-chain and a function-parameter hop) and one that mirrors
    # the host's own guess-of-guess flattening.
    from whence import values as VAL

    eval_lib = eval_library_source()
    cases = {
        "direct, above threshold": (
            'let g = guess(1 + 2, 0.9, "m")\nlet r = sure(g, 0.5)\n'),
        "direct, below threshold": (
            'let g = guess(1 + 2, 0.9, "m")\nlet r = sure(g, 0.95)\n'),
        "let-chain, above threshold": (
            'let g = guess(1 + 2, 0.9, "m")\n'
            'let h = g\nlet r = sure(h, 0.5)\n'),
        "fn-param, above threshold": (
            'fn commit(x) { sure(x, 0.5) }\n'
            'let g = guess(1 + 2, 0.9, "m")\nlet r = commit(g)\n'),
        "fn-param, below threshold": (
            'fn commit(x) { sure(x, 0.5) }\n'
            'let g = guess(1 + 2, 0.4, "m")\nlet r = commit(g)\n'),
        "guess-of-guess flattening, above threshold": (
            'let inner = guess(1 + 2, 0.9, "a")\n'
            'let g = guess(inner, 0.8, "b")\nlet r = sure(g, 0.5)\n'),
    }
    for label, src in cases.items():
        host_env = Interpreter().run(src)
        host_box = host_env.get("r")
        host_ops = [n.op for n, _ in VAL.walk_steps(host_box)]

        inner_src = (
            src +
            'fn __opwalk(acc, n) { fold(__opwalk, push(acc, n.op), n.ins) }\n'
            'let __ops = __opwalk([], why r)\n'
            '__ops\n')
        prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)
        genv = Interpreter().run(prog)
        rec = genv.get("__r").payload
        assert rec.fields["parse_error"].payload is False, label
        guest_ops = [e.payload.split(" ")[0] for e in rec.fields["v"].payload]

        assert guest_ops == host_ops, (label, "guest", guest_ops, "host", host_ops)
