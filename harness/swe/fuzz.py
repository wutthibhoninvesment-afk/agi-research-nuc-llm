"""Fuzzing the Whence interpreter for totality violations.

Whence's central invariant (SPEC decision 2): the evaluator never raises for
user-level problems — every runtime error is a `miss` value. The only
exceptions allowed out of `Interpreter.run` are LexError and ParseError. So
the oracle is simple and strong: generate a random program, run it, and
anything else escaping (RecursionError, OverflowError, TypeError, ...) is a
bug. A second oracle checks a structural invariant: every bound value's
provenance node retains that very payload (`v.prov.value is v.payload`).

Pieces:
  ProgramGen(seed).program()   grammar-directed random program (plus stress
                               templates: deep nesting, big ints, parser depth)
  run_program(src)             in-process oracle with a SIGALRM timeout
  signature(outcome)           stable crash key: (exc type, innermost whence
                               function, message prefix)
  shrink(src, keep)            line ddmin + integer minimisation, keeps `keep`
                               (a predicate on the source) true
  fuzz(seed, n)                campaign: returns Campaign with unique crashers
"""

import os
import random
import signal
import subprocess
import sys
import time
import traceback

WHENCE_ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "languages", "whence"))


def list_example_files(root=WHENCE_ROOT):
    """Names of the CURATED `examples/*.lang` corpus, sorted.

    `examples/` is not exclusively ours: a separate autonomous process
    sharing this repo (the Hermes gateway, see
    `project_hermes_gateway_shares_the_repo`) has dropped its own untracked
    `.lang` files into this same directory before, and a plain
    `os.listdir` has no way to tell those apart from the real corpus. Using
    `git ls-files` instead means only committed, curated examples ever
    enter differential-testing corpora — new example files a language(C)
    round adds show up automatically once committed, and any file another
    process drops in (or removes) stays invisible until it's actually
    ours. Falls back to a plain listdir (old behaviour) if `git` itself is
    unavailable or `root` isn't inside a git checkout at all.
    """
    ex_dir = os.path.join(root, "examples")
    try:
        out = subprocess.run(
            ["git", "ls-files", "examples"], cwd=root,
            capture_output=True, text=True, timeout=10, check=True)
        names = sorted(
            line.split("/", 1)[1] for line in out.stdout.splitlines()
            if line.startswith("examples/") and line.endswith(".lang"))
        if names:
            return names
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return sorted(n for n in os.listdir(ex_dir) if n.endswith(".lang"))


def _import_whence(root=WHENCE_ROOT):
    """Import the whence package from `root` (default: the checkout)."""
    if root not in sys.path:
        sys.path.insert(0, root)
    from whence.interp import Interpreter          # noqa: E402
    from whence.lexer import LexError              # noqa: E402
    from whence.parser import ParseError           # noqa: E402
    from whence.values import Value, full_show     # noqa: E402
    return Interpreter, LexError, ParseError, Value, full_show


# --------------------------------------------------------------- generator --

BUILTIN_ARITY = {
    "print": 1, "len": 1, "range": (1, 2), "map": 2, "filter": 2, "fold": 3,
    "push": 2, "str": 1, "num": 1, "abs": 1, "sqrt": 1, "missed": 1,
    "reasons": 1, "note": 2, "contains": 2, "join": 2, "keys": 1, "merge": 2,
    "get": 2, "put": 3, "has": 2, "find": 2,
    "steps": (1, 2), "at": 2, "blame": 1, "diverge": (1, 2),
    "contrast": (1, 2),
    "guess": 3, "is_guess": 1, "confidence": 1, "sure": 2,
}
BINOPS = ["+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">=", "and", "or"]
STR_POOL = ["", "a", "ab", "3O", "42", " 7 ", "1_000", "nan", "inf", "-inf",
            "1e400", "1e5", "0x1f", "true", "let a", "a\\nb", "\\\\", "\\\"",
            "0.5", "-3", "+4", "٣", "1e-2", "let x", "call f", "literal"]
FIELD_POOL = ["a", "b", "c", "x", "name", "v"]
STEP_NAMES = ["let x", "literal", "call", "arg", "note k", "+", "let a", "if",
              "call go", "call even", "odd", "fold", "==", "arg acc"]
# v0.13 backlog (SPEC "Not done"): the grammar generated no `: Type`/`-> Type`
# annotations, so type-guard code paths (v0.12 params, v0.13 returns) were
# only ever exercised by the hand-written corpus, never by fuzz input. No
# `shape` names exist here (nothing declares one), so only primitive tags —
# the values flowing through are otherwise-untyped fuzz expressions, so a
# tag frequently WON'T match at runtime; that mismatch-as-miss path is
# exactly what needs exercising against fast/direct/trampoline + tail calls.
TYPE_TAGS = ("num", "str", "bool", "list", "record", "fn", "any")

# v0.14 backlog (closed round 162): the grammar generated no `effects [...]`
# clauses either, so the parse-time effect check (round 146) was only ever
# exercised by the hand-written corpus (`examples/effects.lang`,
# `tests/test_v14.py`). `io` is the only builtin ever registered as
# effectful; `net` is deliberately never registered, so it fuzzes the
# "declared but unrelated tag does not grant" path alongside the real one.
# A generated body is free to call `print` directly (it's an ordinary
# BUILTIN_ARITY entry `call()` can pick) inside an `effects []` function,
# which is a real host ParseError — already a normal, handled fuzzer
# outcome (every existing seed already produces plenty from other causes).
EFFECT_TAG_SETS = ("[]", "[io]", "[net]", "[io, net]")

# `guess`/`is_guess`/`confidence`/`sure` are ORDINARY builtin calls (no new
# syntax, unlike `: Type`/`effects [...]`), so they join `BUILTIN_ARITY` and
# `call()` picks them like any other builtin — exercising `_guess_binop`'s
# weakest-link-confidence path, the "genuine type error stays a miss"
# path, and `sure()`'s threshold both ways against fast/direct/trampoline.
# STALE until round 236, this comment used to say `GuestGen` (guest.py)
# bans these four names because self_eval.lang had no guest support for
# them yet — that was true when this section was first written (v0.15,
# guest parity "not started") but has been false since round 176, which
# gave `self_eval.lang`'s `arities`/`apply_builtin` tables free-delegation
# entries for all four (a guest Guess literally IS the host's own `Guess`
# payload). `GuestGen` never banned them via the BANNED-line mechanism at
# all — see `guest.py`'s own `BANNED` regex and its accurate round-176
# comment, which this one failed to match for 60 rounds (158-217 or so, a
# comment-only instance of the exact staleness class rounds 230/234 found
# and fixed in SPEC.md prose; nothing here needed a code fix, only this
# text). `call()` already generates guess/is_guess/confidence/sure freely
# for BOTH the host-only and guest-safe generators today.
GUESS_CONFIDENCES = ("0.9", "0.5", "0.1", "0.0", "1.0", "1.5", "-0.2", '"bad"')
GUESS_SOURCES = ('"model"', '"sampled"', "42")


class ProgramGen(object):
    def __init__(self, seed, stress_rate=0.5, max_depth=4):
        self.r = random.Random(seed)
        self.stress_rate = stress_rate
        self.max_depth = max_depth
        self.counter = 0
        self.scope = []       # top-level bound names
        self.fns = []         # (name, arity) of top-level fns

    # names ---------------------------------------------------------------
    def fresh(self, prefix="v"):
        self.counter += 1
        return "%s%d" % (prefix, self.counter)

    def some_name(self, local):
        r = self.r
        pool = list(local) + self.scope + [f for f, _ in self.fns]
        if not pool or r.random() < 0.04:
            return r.choice(["zz", "undefined_name", "q"])
        return r.choice(pool)

    # program -------------------------------------------------------------
    def program(self):
        r = self.r
        lines = []
        if r.random() < self.stress_rate:
            lines.extend(self.template())
        for _ in range(r.randint(2, 7)):
            lines.append(self.statement())
        probes = r.sample(self.scope, min(len(self.scope), 3)) if self.scope else []
        for name in probes:
            lines.append(self.probe(name))
        return "\n".join(lines) + "\n"

    def template(self):
        r = self.r
        k = r.choice([3, 20, 60, 200, 700, 1500, 3000])
        which = r.randrange(13)
        if which == 9:      # v0.3 tail loop: merged `call go xN` + merged `if` (v0.4)
            self.fns.append(("go", 2)); self.scope.append("tail")
            return ["fn go(n, acc) { if n == 0 { acc } else { go(n - 1, acc + n) } }",
                    "let tail = go(%d, 0)" % k]
        if which == 10:     # mutual recursion: `call even/odd xN`
            self.fns.append(("even", 1)); self.fns.append(("odd", 1)); self.scope.append("par")
            return ["fn even(n) { if n == 0 { true } else { odd(n - 1) } }",
                    "fn odd(n) { if n == 0 { false } else { even(n - 1) } }",
                    "let par = even(%d)" % k]
        if which == 11:     # alternating branches: run-length merge boundaries
            self.fns.append(("alt", 2)); self.scope.append("zig")
            return ["fn alt(n, acc) { if n == 0 { acc } else if n %% %d == 0 { alt(n - 1, acc + 1) }"
                    " else { alt(n - 1, acc - 1) } }" % r.choice([2, 3, 5]),
                    "let zig = alt(%d, 0)" % k]
        if which == 12:     # two near-identical runs for diverge/contrast
            self.fns.append(("go", 2)); self.scope.extend(["r0", "r1"])
            return ["fn go(n, acc) { if n == 0 { acc } else { go(n - 1, acc + n) } }",
                    "let r0 = go(%d, 0)" % k, "let r1 = go(%d, %s)" % (k, r.choice(["1", "0", '"3O"']))]
        if which == 0:
            self.fns.append(("nest", 1)); self.scope.append("deep")
            return ["fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }",
                    "let deep = nest(%d)" % k]
        if which == 1:
            self.fns.append(("count", 1)); self.scope.append("cnt")
            return ["fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }",
                    "let cnt = count(%d)" % k]
        if which == 2:
            self.fns.append(("wrap", 1)); self.scope.append("rec")
            return ["fn wrap(n) { if n == 0 { @{v: 0} } else { @{v: wrap(n - 1)} } }",
                    "let rec = wrap(%d)" % k]
        if which == 3:
            self.scope.append("paren")
            return ["let paren = " + "(" * k + "1" + ")" * k]
        if which == 4:
            self.scope.append("neg")
            return ["let neg = " + "- " * k + "1"]
        if which == 5:
            self.scope.append("lst")
            return ["let lst = " + "[" * k + "]" * k]
        if which == 6:
            self.scope.append("huge")
            return ["let huge = fold(fn(a, x) { a * 2 }, 1, range(%d))" % k]
        if which == 7:
            self.scope.append("grown")
            return ["let grown = fold(fn(acc, x) { push(acc, x) }, [], range(%d))" % k]
        self.scope.append("chain")
        return ["let chain = 1" + " + 1" * k]

    def statement(self):
        r = self.r
        p = r.random()
        if p < 0.55:
            name = self.fresh()
            e = self.expr(0, [])
            self.scope.append(name)
            return "let %s = %s" % (name, e)
        if p < 0.75:
            name = self.fresh("f")
            arity = r.randint(0, 3)
            params = [self.fresh("p") for _ in range(arity)]
            self.fns.append((name, arity))    # visible inside body: recursion
            body = self.body(params)
            return "fn %s(%s)%s%s %s" % (name, self.typed_params(params),
                                         self.maybe_effects(), self.maybe_ret_type(), body)
        if p < 0.9:
            return 'check "%s": %s' % (self.fresh("c"), self.expr(0, []))
        return self.expr(0, [])

    def typed_params(self, params):
        """`(a, b: num, c: str)` — each param independently gets a `: TAG`
        30% of the time (v0.13 backlog)."""
        r = self.r
        return ", ".join(
            "%s: %s" % (p, r.choice(TYPE_TAGS)) if r.random() < 0.3 else p
            for p in params)

    def maybe_ret_type(self):
        """` -> TAG` 25% of the time, else ''."""
        if self.r.random() < 0.25:
            return " -> %s" % self.r.choice(TYPE_TAGS)
        return ""

    def maybe_effects(self):
        """` effects [...]` 30% of the time, BEFORE `-> Type` (fixed order
        per SPEC v0.14 — the other order is an ordinary out-of-order parse
        error, already covered by the grammar's general malformed-syntax
        rate)."""
        if self.r.random() < 0.3:
            return " effects %s" % self.r.choice(EFFECT_TAG_SETS)
        return ""

    def body(self, local):
        r = self.r
        local = list(local)
        stmts = []
        for _ in range(r.randint(0, 2)):
            name = self.fresh("t")
            stmts.append("let %s = %s" % (name, self.expr(1, local)))
            local.append(name)
        stmts.append(self.expr(1, local))
        return "{ " + "\n  ".join(stmts) + " }"

    def probe(self, name):
        r = self.r
        return r.choice([
            "print(%s)", "print(why %s)", "print(str(why %s))",
            "print(len(steps(%s)))", "print(blame(%s))", 'print(at(%s, "let %s"))',
            'check "p": %s == %s', "print(contains([%s], %s))",
            "print(str(steps(%s)))", "print(reasons(%s))", "print(missed(%s))",
            "print(snip %s)", "print(steps(why %s))", 'check "p": %s == %s',
            "print(%s / 3)", "print(sqrt(%s))", "print(%s == [%s])",
            "print(contains(%s, %s))", "print(%s + %s)", "print(-%s)",
            "print(contrast(%s, %s))", "print(len(diverge(%s, %s)))",
            'print(len(steps(%s, "call go")))', 'print(at(%s, "if"))',
            "print(steps(%s)[0].count)", 'print(steps(%s, "if"))',
            "print(contrast(%s, snip %s))", "print(diverge(why %s, %s))",
        ]).replace("%s", name)

    # expressions -------------------------------------------------------
    def literal(self):
        r = self.r
        p = r.random()
        if p < 0.45:
            return str(r.choice([0, 1, 2, 3, 7, 10, 100, 0, 1]))
        if p < 0.6:
            return r.choice(["0.5", "2.0", "0.0", "1.5", "100.25"])
        if p < 0.85:
            return '"%s"' % r.choice(STR_POOL)
        return r.choice(["true", "false"])

    def fnlike(self, depth, local):
        r = self.r
        p = r.random()
        if p < 0.4:
            n = r.randint(0, 2)
            params = [self.fresh("q") for _ in range(n)]
            return "fn(%s)%s%s { %s }" % (self.typed_params(params), self.maybe_effects(),
                                          self.maybe_ret_type(),
                                          self.expr(depth + 1, local + params))
        if p < 0.7 and self.fns:
            return r.choice(self.fns)[0]
        if p < 0.85:
            return r.choice(list(BUILTIN_ARITY))
        return self.expr(depth + 1, local)

    def listlike(self, depth, local):
        r = self.r
        p = r.random()
        if p < 0.35:
            return "[%s]" % ", ".join(self.expr(depth + 1, local) for _ in range(r.randint(0, 4)))
        if p < 0.6:
            return "range(%d)" % r.randint(0, 12)
        if p < 0.8:
            return self.some_name(local)
        return self.expr(depth + 1, local)

    def call(self, depth, local):
        r = self.r
        if self.fns and r.random() < 0.35:
            name, arity = r.choice(self.fns)
            if r.random() < 0.1:
                arity += 1
            return "%s(%s)" % (name, ", ".join(self.expr(depth + 1, local) for _ in range(arity)))
        name = r.choice(list(BUILTIN_ARITY))
        ar = BUILTIN_ARITY[name]
        n = r.randint(*ar) if isinstance(ar, tuple) else ar
        if r.random() < 0.06:
            n += 1
        if name in ("map", "filter"):
            args = [self.fnlike(depth, local), self.listlike(depth, local)]
        elif name == "fold":
            args = [self.fnlike(depth, local), self.expr(depth + 1, local),
                    self.listlike(depth, local)]
        elif name == "at" or (name == "steps" and n == 2):
            args = [self.expr(depth + 1, local), '"%s"' % r.choice(STEP_NAMES)]
        elif name in ("diverge", "contrast"):
            a1 = self.some_name(local)
            if n == 1:      # n-way form: a list of runs (v0.4 diverge, v0.6 contrast)
                args = ["[%s, %s]" % (a1, self.some_name(local))]
            else:
                args = [a1, r.choice([a1, self.some_name(local), self.expr(depth + 1, local)])]
        elif name == "note":
            args = ['"%s"' % r.choice(["k", "note"]), self.expr(depth + 1, local)]
        elif name == "range":
            args = [str(r.randint(-2, 15)) for _ in range(n)]
        elif name == "join":
            args = [self.listlike(depth, local), '"%s"' % r.choice([",", "", "-"])]
        elif name in ("push", "contains"):
            args = [self.listlike(depth, local), self.expr(depth + 1, local)]
        elif name in ("get", "has"):
            # half the time a plausible field name, so present/absent both fire
            args = [self.expr(depth + 1, local),
                    r.choice(['"%s"' % r.choice(FIELD_POOL),
                              self.expr(depth + 1, local)])]
        elif name == "guess":
            # confidence/source pools mix valid and invalid so both the
            # success path and the "confidence/source must be a str/num
            # in [0, 1]" propagated-miss path fire.
            args = [self.expr(depth + 1, local), r.choice(GUESS_CONFIDENCES),
                    r.choice(GUESS_SOURCES)]
        elif name == "sure":
            args = [self.expr(depth + 1, local), r.choice(GUESS_CONFIDENCES)]
        else:
            args = [self.expr(depth + 1, local) for _ in range(n)]
        return "%s(%s)" % (name, ", ".join(args[:n] if n <= len(args) else args + [self.literal()]))

    def expr(self, depth, local):
        r = self.r
        if depth >= self.max_depth:
            return self.literal() if r.random() < 0.6 else self.some_name(local)
        p = r.random()
        d = depth + 1
        if p < 0.14:
            return self.literal()
        if p < 0.26:
            return self.some_name(local)
        if p < 0.32:
            return "[%s]" % ", ".join(self.expr(d, local) for _ in range(r.randint(0, 3)))
        if p < 0.37:
            names = r.sample(FIELD_POOL, r.randint(0, 3))
            return "@{%s}" % ", ".join("%s: %s" % (nm, self.expr(d, local)) for nm in names)
        if p < 0.42:
            return "%s%s" % (r.choice(["-", "not "]), self.expr(d, local))
        if p < 0.60:
            return "(%s %s %s)" % (self.expr(d, local), r.choice(BINOPS), self.expr(d, local))
        if p < 0.66:
            return "if %s { %s } else { %s }" % (self.expr(d, local), self.expr(d, local), self.expr(d, local))
        if p < 0.82:
            return self.call(d, local)
        if p < 0.86:
            return "%s[%s]" % (self.expr(d, local), r.choice(["0", "1", "-1", "2", '"a"', self.expr(d, local)]))
        if p < 0.89:
            return "%s.%s" % (self.expr(d, local), r.choice(FIELD_POOL))
        if p < 0.93:
            return "%s %s" % (r.choice(["why", "snip", "miss"]),
                              '"boom"' if r.random() < 0.5 else self.expr(d, local))
        if p < 0.97:
            return "(%s rescue %s)" % (self.expr(d, local), self.expr(d, local))
        return self.fnlike(depth, local)


# ------------------------------------------------------------------ oracle --

class FuzzTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise FuzzTimeout("program exceeded time budget")


class Outcome(object):
    """kind: ok | lex_error | parse_error | crash | timeout | invariant"""
    __slots__ = ("kind", "exc_type", "message", "frames", "seconds", "out", "phase")

    def __init__(self, kind, exc_type="", message="", frames=(), seconds=0.0,
                 out=(), phase=""):
        self.kind = kind
        self.exc_type = exc_type
        self.message = message
        self.frames = tuple(frames)   # innermost-last (function, lineno, file)
        self.seconds = seconds
        self.out = tuple(out)
        self.phase = phase

    def as_dict(self):
        return {"kind": self.kind, "exc_type": self.exc_type,
                "message": self.message, "frames": list(self.frames),
                "seconds": round(self.seconds, 4), "phase": self.phase}


def _whence_frames(tb, root):
    out = []
    for fr in traceback.extract_tb(tb):
        if os.sep + "whence" + os.sep in fr.filename or fr.filename.startswith(root):
            out.append((fr.name, fr.lineno, os.path.basename(fr.filename)))
    return out


def run_program(src, max_depth=2000, timeout_s=3.0, root=WHENCE_ROOT,
                check_invariants=True):
    """Run one program in-process under a wall-clock budget."""
    Interpreter, LexError, ParseError, Value, full_show = _import_whence(root)
    out = []
    interp = Interpreter(out=out.append, max_depth=max_depth)
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    t0 = time.time()
    phase = "parse"
    try:
        try:
            from whence.parser import parse
            program = parse(src)
        except (LexError, ParseError) as e:
            kind = "lex_error" if isinstance(e, LexError) else "parse_error"
            return Outcome(kind, type(e).__name__, str(e), seconds=time.time() - t0,
                           out=out, phase=phase)
        phase = "run"
        from whence.interp import Env
        env = Env(interp.globals)
        for stmt in program.stmts:
            interp.exec_stmt(stmt, env)
        if check_invariants:
            phase = "invariant"
            for name, v in env.vars.items():
                if not isinstance(v, Value):
                    return Outcome("invariant", "NotAValue", "%s bound to %r" % (name, v),
                                   seconds=time.time() - t0, out=out, phase=phase)
                if v.prov.value is not v.payload:
                    return Outcome("invariant", "ProvValueMismatch",
                                   "%s: prov.value is not payload (%s vs %s)"
                                   % (name, full_show(v.prov.value)[:40],
                                      full_show(v.payload)[:40]),
                                   seconds=time.time() - t0, out=out, phase=phase)
        return Outcome("ok", seconds=time.time() - t0, out=out, phase="run")
    except FuzzTimeout:
        return Outcome("timeout", "FuzzTimeout", "exceeded %.1fs" % timeout_s,
                       seconds=time.time() - t0, out=out, phase=phase)
    except MemoryError:
        return Outcome("crash", "MemoryError", "out of memory",
                       seconds=time.time() - t0, out=out, phase=phase)
    except Exception as e:  # noqa: BLE001 — this is the oracle: any escape is a bug
        frames = _whence_frames(e.__traceback__, root)
        return Outcome("crash", type(e).__name__, str(e)[:200], frames=frames,
                       seconds=time.time() - t0, out=out, phase=phase)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def signature(o):
    """Stable key for grouping crashes by root cause."""
    if o.kind not in ("crash", "invariant"):
        return (o.kind,)
    if o.exc_type == "RecursionError" and o.frames:
        # The innermost frame is wherever the cycle happened to be cut, which
        # depends on the caller's stack depth. Key on the cycle's dominant
        # function instead (ties broken by name -> deterministic).
        counts = {}
        for name, _, _ in o.frames:
            counts[name] = counts.get(name, 0) + 1
        # only functions that recur are part of the cycle; single-occurrence
        # frames (entry path, or the leaf helper the cut landed in) are noise
        cycle = sorted(n for n, c in counts.items() if c >= 2)
        return (o.kind, o.exc_type, "cycle:" + "+".join(cycle), o.phase)
    inner = o.frames[-1][0] if o.frames else "?"
    return (o.kind, o.exc_type, inner, o.message[:40])


# ----------------------------------------------------------------- shrinker --

def ddmin_lines(lines, keep):
    """Classic delta debugging over a list of lines; `keep(lines)` must be
    True for the input and stays True for the result."""
    n = 2
    while len(lines) >= 2:
        chunk = max(1, len(lines) // n)
        removed = False
        i = 0
        while i < len(lines):
            candidate = lines[:i] + lines[i + chunk:]
            if candidate and keep(candidate):
                lines = candidate
                n = max(n - 1, 2)
                removed = True
            else:
                i += chunk
        if not removed:
            if n >= len(lines):
                break
            n = min(n * 2, len(lines))
    return lines


def _minimize_ints(line, keep_line):
    """Binary-search every integer literal in `line` toward 0 while
    keep_line(new_line) stays True."""
    import re
    spans = [(m.start(), m.end()) for m in re.finditer(r"(?<![\w.])\d+(?![\w.])", line)]
    for start, end in reversed(spans):     # right to left keeps earlier spans valid
        value = int(line[start:end])
        lo, hi = 0, value
        best = value
        while lo < hi:
            mid = (lo + hi) // 2
            cand = line[:start] + str(mid) + line[end:]
            if keep_line(cand):
                best = mid
                hi = mid
            else:
                lo = mid + 1
        line = line[:start] + str(best) + line[end:]
    return line


def _minimize_repeats(line, keep_line):
    """Shrink runs of a repeated token by binary search on the run length:
    balanced bracket runs `(((x)))` / `[[[]]]` shrink both sides together;
    prefix runs (`- - -`, `why why`, `not not`) and ` + 1 + 1` chains shrink
    alone."""
    import re

    def search(count, build):
        lo, hi, best = 1, count, count
        while lo < hi:
            mid = (lo + hi) // 2
            if keep_line(build(mid)):
                best, hi = mid, mid
            else:
                lo = mid + 1
        return build(best)

    for open_c, close_c in (("(", ")"), ("[", "]")):
        m = re.search(r"(\%s{4,})([^%s%s]*)(\%s{4,})" % (open_c, open_c, close_c, close_c), line)
        if m and len(m.group(1)) == len(m.group(3)):
            n = len(m.group(1))
            mid_text = m.group(2)
            line = search(n, lambda k, m=m, mid_text=mid_text: line[:m.start()] + open_c * k + mid_text + close_c * k + line[m.end():])
    for unit in ("- ", "why ", "not ", "snip "):
        m = re.search(r"((?:%s){4,})" % re.escape(unit), line)
        if m:
            n = len(m.group(1)) // len(unit)
            line = search(n, lambda k, m=m: line[:m.start()] + unit * k + line[m.end():])
    m = re.search(r"((?: \+ 1){4,})", line)
    if m:
        n = len(m.group(1)) // 4
        line = search(n, lambda k, m=m: line[:m.start()] + " + 1" * k + line[m.end():])
    return line


def shrink(src, keep, max_rounds=3):
    """Minimise `src` while keep(src) stays True. Line ddmin first, then
    per-line integer and repeat-run minimisation, repeated to a fixpoint."""
    lines = [ln for ln in src.split("\n") if ln.strip()]
    if not keep("\n".join(lines) + "\n"):
        return None   # flaky reproducer (non-deterministic); leave unminimised
    for _ in range(max_rounds):
        before = list(lines)
        lines = ddmin_lines(lines, lambda ls: keep("\n".join(ls) + "\n"))
        new_lines = []
        for i, ln in enumerate(lines):
            def keep_line(cand, i=i):
                trial = lines[:i] + [cand] + lines[i + 1:]
                return keep("\n".join(trial) + "\n")
            ln = _minimize_repeats(ln, keep_line)
            ln = _minimize_ints(ln, keep_line)
            new_lines.append(ln)
            lines = lines[:i] + [ln] + lines[i + 1:]
        lines = new_lines
        if lines == before:
            break
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------- campaign --

class Crasher(object):
    def __init__(self, sig, seed, src, outcome, minimized=None):
        self.sig = sig
        self.seed = seed
        self.src = src
        self.outcome = outcome
        self.minimized = minimized

    def as_dict(self):
        return {"signature": list(self.sig), "seed": self.seed,
                "outcome": self.outcome.as_dict(),
                "src_lines": self.src.count("\n"),
                "minimized": self.minimized,
                "minimized_lines": self.minimized.count("\n") if self.minimized else None}


class Campaign(object):
    def __init__(self):
        self.counts = {}
        self.crashers = {}   # sig -> Crasher (first seen)
        self.programs = 0
        self.seconds = 0.0

    def summary(self):
        lines = ["fuzz: %d programs in %.1fs" % (self.programs, self.seconds)]
        for k in sorted(self.counts):
            lines.append("  %-12s %d" % (k, self.counts[k]))
        lines.append("  unique crash signatures: %d" % len(self.crashers))
        for sig, c in sorted(self.crashers.items(), key=lambda kv: kv[0]):
            lines.append("  - %s  (seed %d, %d lines%s)" % (
                " | ".join(sig), c.seed, c.src.count("\n"),
                ", minimized to %d" % c.minimized.count("\n") if c.minimized else ""))
        return "\n".join(lines)

    def as_dict(self):
        return {"programs": self.programs, "seconds": round(self.seconds, 2),
                "counts": self.counts,
                "crashers": [c.as_dict() for c in self.crashers.values()]}


def fuzz(seed=0, n=200, max_depth=2000, timeout_s=3.0, root=WHENCE_ROOT,
         do_shrink=True, stress_rate=0.5, on_program=None):
    camp = Campaign()
    t0 = time.time()
    for i in range(n):
        s = seed * 1000003 + i
        src = ProgramGen(s, stress_rate=stress_rate).program()
        o = run_program(src, max_depth=max_depth, timeout_s=timeout_s, root=root)
        camp.programs += 1
        camp.counts[o.kind] = camp.counts.get(o.kind, 0) + 1
        if on_program:
            on_program(i, src, o)
        sig = signature(o)
        if o.kind in ("crash", "invariant") and sig not in camp.crashers:
            cr = Crasher(sig, s, src, o)
            if do_shrink:
                def keep(cand, sig=sig):
                    return signature(run_program(cand, max_depth=max_depth,
                                                 timeout_s=timeout_s, root=root)) == sig
                cr.minimized = shrink(src, keep)
            camp.crashers[sig] = cr
    camp.seconds = time.time() - t0
    return camp


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--no-shrink", action="store_true")
    ap.add_argument("--show", action="store_true", help="print minimized crashers")
    ap.add_argument("--limit", type=int, default=0,
                    help="host recursion limit (run.py uses 6000; the default "
                         "limit's reserve hides linear frame undercounts — "
                         "round 108)")
    a = ap.parse_args()
    if a.limit:
        sys.setrecursionlimit(a.limit)
    c = fuzz(a.seed, a.n, do_shrink=not a.no_shrink)
    print(c.summary())
    if a.show:
        for sig, cr in c.crashers.items():
            print("\n### %s\n%s" % (" | ".join(sig), cr.minimized or cr.src))
