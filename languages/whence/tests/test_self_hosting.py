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
    ])
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
