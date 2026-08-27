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
        # round 206: self_host.lang's own line 651-652 check, at the guest-
        # EVALUATOR level specifically — `steps` was entirely unimplemented
        # in self_eval.lang's guest builtin table (not even a name-
        # resolution hit) until this round, so this failed with "unbound
        # name 'steps'" for every prior self-hosting round (192/198/200/
        # 204) that got deep enough to reach it (round 204's own
        # bench/self_host_memscale.py at checkpoint 47).
        'check "guest AST is itself a real Whence value with its own history":\n'
        '  not missed(p2) and len(steps(p2)) > 0',
    ])
    inner_src = lib_section + "\n" + inner_checks + "\n"
    prog = eval_lib + 'let __r = run_src("%s")\n' % escape(inner_src)

    env = Interpreter().run(prog)
    rec = env.get("__r").payload
    assert rec.fields["parse_error"].payload is False
    checks = rec.fields["checks"].payload
    assert len(checks) == 5
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
    eval_lib = eval_library_source()
    lib_section = self_host_library_section()
    inner_checks = "\n".join([
        'let p = parse_whence("fn go(n) { if n == 0 { 0 } else { go(n - 1) } }")',
        'let all_steps = steps(p)',
        'let go_steps = steps(p, "call go")',
        'check "2-arg pattern form narrows, never widens":\n'
        '  len(go_steps) <= len(all_steps)',
        'let bad = miss "deliberately broken"',
        'check "steps is total: a miss has its own (short) history too":\n'
        '  len(steps(bad)) > 0',
    ])
    inner_src = lib_section + "\n" + inner_checks + "\n"
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
