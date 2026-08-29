"""Guest-differential oracle (round 17): host interpreter vs the Whence-in-
Whence evaluator (`examples/self_eval.lang`, self-hosting round 4).

Round 14 differentially tested the guest evaluator against a HAND corpus of
50 programs. This module makes that unbounded: a guest-safe program
generator (the fuzz grammar minus provenance builtins, minus the host-scale
stress templates) plus a fifth oracle, `self_eval`, that runs each program
under both evaluators and compares:

  - the final value of every top-level binding (miss-scrubbed through
    `rescue` so one bad binding cannot collapse the rest into one miss),
  - check results (label, pass) in order,
  - missed-ness of the whole run.

Exemptions, by design (documented in self_eval.lang's header):
  - miss REASON wordings differ between host and guest; only missed-ness
    is compared (the scrub maps every miss to one sentinel string),
  - functions compare by "both sides think it is a function": host Closure/
    Builtin vs guest records tagged __tag: closure|builtin,
  - depth skew: the guest pays ~6.8 host frames per guest call, so a
    program can exhaust max_depth under one evaluator only. A one-sided
    miss whose reasons mention the depth budget is `depth_skew`, not a
    finding. Round 295: `harness_for`/`oracle_self_eval` now build the
    guest's own interpreter with the SAME `max_depth` the host side uses
    (both default 2000) rather than the guest silently getting the raw
    interpreter's `DEFAULT_MAX_DEPTH` (20000) regardless of the host's own
    cap — the exemption above is for real, unavoidable interpretation
    overhead, not a caller-facing asymmetry that widens which mismatches it
    swallows.

Everything else that differs is a real divergence between the language and
its self-hosted definition — exactly the bug class no other oracle sees.
"""

import os
import re

from .fuzz import ProgramGen, WHENCE_ROOT, shrink
from .killers import load_whence
from . import oracles as O

MISS_SENTINEL = "&MISS&"
DEPTH_SENTINEL = "&DEPTHMISS&"
GUEST_ORACLE = "self_eval"
LIB_MARKER = "# ==== SELF-TESTS"

# provenance builtins the guest evaluator does not (and cannot yet) mirror.
# `guess`/`is_guess`/`confidence`/`sure` (v0.15, round 168) are NO LONGER
# banned as of round 176: self_eval.lang's `arities`/`apply_builtin` tables
# now delegate all four straight to the real host builtins (a guest Guess
# IS the host's own `Guess` payload), so the guest-differential fuzzer can
# generate them like any other builtin call.
#
# `steps` gained the SAME straight-to-host delegation in round 206 (closing
# a real guest-parity gap self_host.lang's own test corpus found — see
# knowledge/round-206-whence-v16-guest-steps-parity.md) but STAYS banned
# here on purpose, unlike guess/confidence: this oracle compares bare
# PAYLOAD values, and `len(steps(x))`/`steps(x)` IS a direct readout of the
# provenance GRAPH SIZE, which legitimately differs between host-direct
# eval and self_eval.lang-mediated eval of the "same" program — self_eval's
# own interpreter loop adds many more real host Prov nodes per guest
# operation (every guest `put`/`merge`/field-access is itself a real,
# additional host builtin call) than a host directly evaluating the same
# expression would. Unlike a Guess's confidence float or a boolean sure()
# outcome (provenance-shape-independent), a step COUNT would diverge for
# nearly any nontrivial fuzzed program — not a language bug, an inherent
# property of what self-hosting layering costs, exactly the "expected
# architectural difference, not a finding" class `depth_skew` and miss-
# reason-wording already carve out above. `at`/`blame`/`diverge`/`contrast`
# are the same family (steps-shaped output) and stay banned for the
# identical reason, on top of not having guest support built yet at all.
BANNED = re.compile(r"\b(why|snip|steps|at|blame|diverge|contrast|print)\b")


def guest_safe(src):
    """Drop whole lines that use non-guest constructs. Dropping a `let` that
    a later line references is fine: the name is then unbound for BOTH
    evaluators and both sides agree on the miss."""
    return "\n".join(ln for ln in src.split("\n") if not BANNED.search(ln))


def escape(src):
    """Embed a program as a Whence string literal (round-14 escaping)."""
    return (src.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\t", "\\t"))


class GuestGen(ProgramGen):
    """The fuzz grammar with guest-scale stress templates and payload-visible
    probes. Guest interpretation costs ~2ms per guest call (round 14), so
    iteration counts stay two orders of magnitude below the host fuzzer's.

    `typed_params`/`maybe_ret_type` used to be overridden to a no-op (round
    134): `self_eval.lang`'s hand-copied lexer/parser predated v0.12/v0.13
    and did not tokenize `->` or erase `: Type` at parse time, so a
    generated annotation would fail on the GUEST side alone — a guest-
    parity gap, not a host bug. Round 158 closed that gap (self_host.lang
    + self_eval.lang's shared parser section now parses `: TAG`/`-> TAG`,
    primitive tags only, and self_eval.lang's evaluator gained a `typed`
    builtin + a return-type check mirroring the host's `_check_ret`), so
    `GuestGen` now inherits `ProgramGen`'s real `typed_params`/
    `maybe_ret_type` unchanged — type-guarded programs are guest-safe like
    everything else this generator produces. Shapes remain unsupported on
    the guest side (`self_eval.lang` still doesn't implement `shape`), but
    the fuzzer never generates a shape name as a type tag (`TYPE_TAGS` is
    primitives only), so that gap is out of scope for this generator by
    construction, not worked around here.

    `maybe_effects` (round 162: `ProgramGen` gained `effects [...]`
    generation for the v0.14 effect system, round 146) used to be
    overridden to a no-op here, one host-round earlier in its own parity
    arc than type annotations were at round 134 — `self_eval.lang`/
    `self_host.lang`'s shared parser section had no `effects` contextual
    keyword at all, so a generated clause would not fail closed the way an
    unknown type tag does: the guest parser read `effects` as an ordinary
    NAME token, then choked on the literal `[` where it expected `->` or
    `{`. Round 164 closed that PARSING gap (both files' shared parser
    section now recognizes and skips `effects [name, ...]`), so `GuestGen`
    now inherits `ProgramGen`'s real `maybe_effects` unchanged.

    The guest still does not ENFORCE a declaration (no threaded
    `effects_stack` — see the parser section's own `parse_effects_clause`
    docstring for why that is a materially bigger change than the erasure
    return-type annotations got). That is safe to leave unenforced here
    specifically because `BANNED` above already strips every line
    containing `print` — the ONE effectful builtin (`_EFFECTFUL_BUILTINS`
    in `whence/parser.py`) — from every program this generator emits,
    on BOTH sides of the comparison, regardless of what any `effects [...]`
    clause says. A generated declaration is therefore always vacuously
    satisfied (there is no call left in the body for it to restrict), so
    there is no way for the host's parse-time rejection and the guest's
    silent non-enforcement to disagree through this generator. Shapes
    remain unsupported on the guest side for the same reason `typed_params`
    stays inherited unchanged (see above) — out of scope for this
    generator by construction, not worked around here."""

    def template(self):
        r = self.r
        k = r.choice([3, 5, 8, 12, 20])
        which = r.randrange(11)
        if which == 8:      # record pipeline: map -> find -> fold (round 20)
            self.scope.extend(["recs", "toti", "hit"])
            return ["let recs = map(fn(i) { @{id: i, sc: i * 3} }, range(%d))" % k,
                    "let toti = fold(fn(a, r) { a + r.sc }, 0, recs)",
                    "let hit = (find(fn(r) { r.sc > 9 }, recs)).id rescue -1"]
        if which == 9:      # env-as-record: fold put, then get/has (round 20)
            self.scope.extend(["envr", "gotv", "hasv"])
            return ['let envr = fold(fn(e, i) { put(e, "k" + str(i), i * i) },'
                    ' @{}, range(%d))' % k,
                    'let gotv = get(envr, "k2") rescue -1',
                    'let hasv = [has(envr, "k1"), has(envr, "zz")]']
        if which == 10:     # put-overwrite + a miss-valued field (round 20)
            self.scope.extend(["base", "mval", "mhas", "mget"])
            return ['let base = put(put(@{}, "a", 1), "a", 2)',
                    'let mval = put(base, "m", num("xx"))',
                    'let mhas = has(mval, "m")',
                    'let mget = get(mval, "m") rescue -7']
        if which == 0:
            self.fns.append(("fib", 1)); self.scope.append("fibv")
            return ["fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }",
                    "let fibv = fib(%d)" % (k % 9 + 2)]
        if which == 1:
            self.fns.append(("go", 2)); self.scope.append("tailv")
            return ["fn go(n, acc) { if n == 0 { acc } else { go(n - 1, acc + n) } }",
                    "let tailv = go(%d, 0)" % k]
        if which == 2:
            self.fns.append(("even", 1)); self.fns.append(("odd", 1)); self.scope.append("parv")
            return ["fn even(n) { if n == 0 { true } else { odd(n - 1) } }",
                    "fn odd(n) { if n == 0 { false } else { even(n - 1) } }",
                    "let parv = even(%d)" % k]
        if which == 3:
            self.scope.append("grownv")
            return ["let grownv = fold(fn(acc, x) { push(acc, len(acc) + x) }, [], range(%d))" % k]
        if which == 4:
            self.fns.append(("adder", 1)); self.scope.append("addv")
            return ["fn adder(a) { fn(b) { a + b } }",
                    "let addv = adder(%d)(2) + adder(1)(%d)" % (k, k)]
        if which == 5:
            self.scope.append("bigv")
            return ["let bigv = fold(fn(a, x) { a * 3 }, 1, range(%d))" % k]
        if which == 6:
            self.fns.append(("wrap", 1)); self.scope.append("recv")
            return ["fn wrap(n) { if n == 0 { @{v: 0} } else { @{v: wrap(n - 1)} } }",
                    "let recv = wrap(%d)" % min(k, 8)]
        self.scope.append("strv")
        return ['let strv = join(map(str, range(%d)), "-")' % k]

    def program(self):
        """Base recipe, but banned constructs are filtered per STATEMENT
        (a multi-line `fn` body must be dropped whole; line-level stripping
        would leave dangling fragments that parse on neither side)."""
        r = self.r
        stmts = []
        if r.random() < self.stress_rate:
            stmts.extend(self.template())
        for _ in range(r.randint(2, 7)):
            stmts.append(self.statement())
        probes = r.sample(self.scope, min(len(self.scope), 3)) if self.scope else []
        for name in probes:
            stmts.append(self.probe(name))
        return "\n".join(s for s in stmts if not BANNED.search(s)) + "\n"

    def probe(self, name):
        r = self.r
        return r.choice([
            'check "p_%s": missed(%s)',
            'check "q_%s": %s == %s',
            'check "r_%s": (len(%s) rescue 0) >= 0',
            "str(%s)",
            "(%s + %s) rescue 0",
            "contains([%s], %s)",
        ]).replace("%s", name)


def generate_guest_program(seed, stress_rate=0.7, max_names=8):
    """One finalized guest-safe program: generated body, banned lines
    stripped, then a scrubbed record of every (surviving) top-level binding
    so the differential compares bindings independently."""
    g = GuestGen(seed, stress_rate=stress_rate)
    src = g.program()    # GuestGen filters banned statements itself
    names = []
    for n in g.scope + [f for f, _ in g.fns]:
        if n not in names:
            names.append(n)
    # a missed binding becomes a sentinel string (reason wordings are exempt
    # by design); a DEPTH miss gets its own sentinel because the guest pays
    # ~6.8 host frames per guest call and can exhaust the budget one-sided
    return src + scrub_record_line(names[:max_names])


# -------------------------------------------------------------- comparator --

def _is_host_fn(V, p):
    return isinstance(p, (V.Closure, V.Builtin))


def _is_guest_fn(V, p):
    if not isinstance(p, V.Record):
        return False
    tag = p.fields.get("__tag")
    return tag is not None and tag.payload in ("closure", "builtin")


def agree(V, h, g):
    """Structural agreement between a host payload and a guest payload.
    Returns (ok, path) where path names the first disagreement."""
    if h == DEPTH_SENTINEL or g == DEPTH_SENTINEL:
        return True, ""    # one-sided depth exhaustion: exempt by design
    if isinstance(h, V.Miss) or isinstance(g, V.Miss):
        ok = isinstance(h, V.Miss) and isinstance(g, V.Miss)
        return ok, "" if ok else "missedness %s-vs-%s" % (type(h).__name__, type(g).__name__)
    # v0.15 guest parity (round 176): a guest Guess IS the host's own
    # `Guess` payload (self_eval.lang delegates `guess`/`sure`/etc. straight
    # to the real builtins, see its `apply_host_builtin`), so this compares
    # confidence/sources exactly (not just the wrapped answer, unlike
    # `deep_eq`'s own Guess-vs-Guess case, which the guest's `raw_deep_eq`
    # mirrors separately for NESTED comparisons — this oracle wants the
    # stronger check since it is specifically hunting for guest bugs).
    if isinstance(h, V.Guess) or isinstance(g, V.Guess):
        ok = (isinstance(h, V.Guess) and isinstance(g, V.Guess) and
              h.confidence == g.confidence and h.sources == g.sources)
        if not ok:
            return False, "guess %s-vs-%s" % (type(h).__name__, type(g).__name__)
        return agree(V, h.node.payload, g.node.payload)
    if _is_host_fn(V, h):
        ok = _is_guest_fn(V, g) or _is_host_fn(V, g)
        return ok, "" if ok else "fn-vs-%s" % type(g).__name__
    if isinstance(h, bool) or isinstance(g, bool):
        ok = isinstance(h, bool) and isinstance(g, bool) and h == g
        return ok, "" if ok else "bool %r-vs-%r" % (h, g)
    if isinstance(h, (int, float)) and isinstance(g, (int, float)):
        return (True, "") if h == g else (False, "num %r-vs-%r" % (h, g))
    if isinstance(h, str) and isinstance(g, str):
        if h == g or _both_exempt_strings(h, g):
            return True, ""
        return False, "str %r-vs-%r" % (h[:40], g[:40])
    if isinstance(h, V.WList) and isinstance(g, V.WList):
        if len(h) != len(g):
            return False, "list-len %d-vs-%d" % (len(h), len(g))
        for i, (a, b) in enumerate(zip(h, g)):
            ok, path = agree(V, a.payload, b.payload)
            if not ok:
                return False, "[%d].%s" % (i, path)
        return True, ""
    if isinstance(h, V.Record) and isinstance(g, V.Record):
        if set(h.fields) != set(g.fields):
            return False, "record-keys %s-vs-%s" % (sorted(h.fields), sorted(g.fields))
        for k in h.fields:
            ok, path = agree(V, h.fields[k].payload, g.fields[k].payload)
            if not ok:
                return False, "%s.%s" % (k, path)
        return True, ""
    return False, "type %s-vs-%s" % (type(h).__name__, type(g).__name__)


_REASONISH = re.compile(r"\(line \d+\)|^miss: ")
_FN_RENDER = re.compile(r"<fn\b|<builtin\b|__tag")


def _both_exempt_strings(h, g):
    """The two design exemptions (miss WORDINGS, function RENDERINGS) leak
    into ordinary string values through `reasons(x)` and `str(x)` — the
    first campaign's dominant false-positive family (round 17). Two strings
    are exempt-equal when BOTH are reason-shaped (line-number suffix or
    `miss:` prefix) or BOTH render a function. Missed-ness itself still
    compares: a reason-shaped string on one side against a plain value on
    the other remains a mismatch."""
    if _REASONISH.search(h) and _REASONISH.search(g):
        return True
    return bool(_FN_RENDER.search(h) and _FN_RENDER.search(g))


def _depth_missed(V, p):
    return isinstance(p, V.Miss) and any("depth" in r for r in p.reasons)


# ------------------------------------------------------------ why-shape probe
# Round 20 (backlog #6): provenance fuzzing, not just value fuzzing. The
# guest's `why` reifies its box graph into guest records @{v, op, ins}
# whose op strings mirror host labels (round 18). The probe re-runs the
# program under the guest with an op-collecting walk appended and checks
# CONTAINMENT: every op token the guest reports for a binding must appear
# as a host node op in that binding's host derivation. Containment, not
# equality: guest reify is budget-capped (300 nodes), so deep host ops can
# legitimately be absent from the guest set — but the guest inventing an op
# the host never performed is a mirroring bug.

# ops whose host `Prov.op` is a stable single token the guest mirrors
#
# `guess`/`is_guess`/`confidence`/`sure` (round 236) join this set: all four
# are free-delegation builtins (round 176 for the first three, round 234 for
# `sure`'s two Guess-carrying cases) that call the real host builtin on real
# host-provenance arguments, so their `Prov.op` is exactly `"guess"`/
# `"is_guess"`/`"confidence"`/`"sure"` on both sides by construction — round
# 234 hand-verified `sure` across 6 shapes (op-LIST equality, not just this
# containment check) but never added the tokens here, so the probe still
# could not see either evaluator omit or invent one on a real fuzz run; round
# 236 hand-verified the other three (`guess` itself, `is_guess`, `confidence`,
# including guess-of-guess flattening and three miss-producing edge cases —
# 12 shapes total, all exact matches) before adding them here too. See
# `knowledge/round-236-whence-guess-sure-why-vocab-and-fuzz-comment-staleness.md`.
#
# `matches`/`shapeof`/`typed` (round 246) join this set the same way: all
# three are free-delegation builtins (round 224 for `matches`/`shapeof`,
# round 158 for `typed`) whose top-level `Prov.op` is forced to the
# builtin's own name (or `"builtin"` on a propagated-miss argument) by
# `apply_host_builtin`'s generic wrapper — or, for `typed`'s on-match case,
# is a pure pass-through of the original value's own node, no new op at
# all — regardless of which internal branch computed the payload. Round
# 246 hand-verified 15 shapes (op-LIST equality) covering every dispatch
# path each of the three has, including `shapeof`/`matches`'s
# `is_callable` guard branch (a guest closure, the one path that does NOT
# call the real host builtin) and `matches`'s `strip()`-based structural-
# Record-spec path (round 240) — all 15 exact matches, no divergence
# found. See `knowledge/round-246-whence-matches-shapeof-typed-why-vocab.md`.
WHY_VOCAB = frozenset([
    "let", "arg", "call", "if", "literal", "list", "record", "index",
    "field", "fold", "map", "filter", "find", "push", "len", "range", "num",
    "str", "abs", "sqrt", "missed", "reasons", "note", "contains", "join",
    "keys", "merge", "get", "put", "has", "builtin", "fn", "miss", "rescue",
    "key", "reason", "guess", "is_guess", "confidence", "sure",
    "matches", "shapeof", "typed",
    "+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">=",
    "and", "or", "not",
])

OPWALK_HELPER = "fn __opwalk(acc, n) { fold(__opwalk, push(acc, n.op), n.ins) }\n"


def why_shape_probe(V, harness, src, host_env_vars, names, max_names=2):
    """Compare guest-reified why-op tokens against host derivation ops for
    up to `max_names` non-miss, non-function bindings. Returns (kind,
    detail): ok | mismatch. A probe that cannot run (guest parse/depth
    trouble in the extra walk) is skipped as ok — the VALUE comparison has
    already passed by the time this runs."""
    from importlib import import_module
    values_mod = import_module(V.__name__)
    picked = []
    for n in names:
        hv = host_env_vars.get(n)
        if hv is None or isinstance(hv.payload, V.Miss):
            continue
        if _is_host_fn(V, hv.payload):
            continue
        picked.append(n)
        if len(picked) >= max_names:
            break
    if not picked:
        return "ok", "why_probe_no_target"
    fields = ", ".join("%s: __opwalk([], why %s)" % (n, n) for n in picked)
    probe_src = src + OPWALK_HELPER + "let __whyops = @{%s}\n__whyops\n" % fields
    rec = harness.eval_program(probe_src)
    if isinstance(rec, V.Miss):
        return "ok", "why_probe_derailed"
    if rec.fields["parse_error"].payload is True:
        return "mismatch", "why_probe_parse_error"
    wrec = rec.fields["v"].payload
    if isinstance(wrec, V.Miss) or not isinstance(wrec, V.Record):
        return "ok", "why_probe_derailed"
    for n in picked:
        ops_v = wrec.fields[n].payload
        if isinstance(ops_v, V.Miss):        # e.g. opwalk hit the depth budget
            continue
        guest_tokens = set()
        for e in ops_v:
            if isinstance(e.payload, str):
                guest_tokens.add(e.payload.split(" ")[0])
        host_ops = set(node.op for node, _ in
                       values_mod.walk_steps(host_env_vars[n]))
        extra = (guest_tokens & WHY_VOCAB) - host_ops
        if extra:
            return "mismatch", "why_shape %s\nguest-only ops: %s\nhost ops: %s" % (
                n, sorted(extra), sorted(host_ops)[:20])
    return "ok", "why_probe_ok"


# ----------------------------------------------------------------- harness --

class GuestHarness(object):
    """The self_eval.lang library loaded ONCE into a host interpreter; each
    program is then one `let __gN = run_src("...")` executed into the same
    long-lived env (the library is ~800 lines; re-parsing it per program
    would dominate the campaign)."""

    def __init__(self, root=WHENCE_ROOT, pkg=None, lib_source=None, max_depth=2000):
        self.root = root
        self.pkg = pkg or load_whence(root, "guesthost")
        name = self.pkg["name"]
        self.V = __import__(name + ".values", fromlist=["Miss"])
        self._parser = __import__(name + ".parser", fromlist=["parse"])
        if lib_source is None:
            with open(os.path.join(root, "examples", "self_eval.lang"), encoding="utf-8") as f:
                lib_source = f.read().split(LIB_MARKER)[0]
        self.swallowed = []
        self.max_depth = max_depth
        kwargs = {"out": self.swallowed.append}
        if max_depth is not None:
            kwargs["max_depth"] = max_depth
        self.interp = self.pkg["Interpreter"](**kwargs)
        self.env = self.pkg["Env"](self.interp.globals)
        for stmt in self._parser.parse(lib_source).stmts:
            self.interp.exec_stmt(stmt, self.env)
        self.n = 0

    def eval_program(self, src):
        """Guest-evaluate `src`; returns the payload of run_src's record
        (fields v / checks / parse_error) — or a Miss if the evaluator
        itself derailed."""
        self.n += 1
        name = "__g%d" % self.n
        stmt_src = 'let %s = run_src("%s")\n' % (name, escape(src))
        for stmt in self._parser.parse(stmt_src).stmts:
            self.interp.exec_stmt(stmt, self.env)
        return self.env.vars[name].payload


_HARNESSES = {}


def harness_for(pkg, max_depth=2000):
    """Round 289 flagged this as always building with `max_depth=None` (the
    interpreter's own `DEFAULT_MAX_DEPTH` = 20000), regardless of whatever
    `max_depth` the HOST side of the same comparison uses — an asymmetry
    that widens `compare_behaviours`' one-sided-depth-miss exemption into a
    real coverage gap: a genuine mismatch that only manifests in a guest
    recursion whose host-side counterpart Misses under its own (lower,
    caller-supplied) cap but whose SELF-HOSTED cost (~6.8 host frames per
    guest call, see module docstring) still fits under the guest's
    unrelated, much higher 20000 default would be silently exempted as
    `depth_skew` instead of compared. Defaulting this to 2000 — the same
    default `oracle_self_eval`/`fuzz_guest` already use for the HOST side —
    and having `oracle_self_eval` (below) pass its own `max_depth` through
    when it builds the cached harness closes that gap for the normal,
    no-explicit-`harness=` campaign path; a caller needing a specific depth
    still gets a fresh harness built for it (the cache key now includes
    `max_depth`, so two different depths for the same package never share
    a cached instance)."""
    key = pkg["name"]
    cached = _HARNESSES.get(key)
    if cached is None or cached.max_depth != max_depth:
        cached = GuestHarness(pkg.get("root", WHENCE_ROOT), pkg, max_depth=max_depth)
        _HARNESSES[key] = cached
    return cached


def compare_behaviours(V, host_env_vars, host_checks, guest_rec):
    """The oracle's comparison. Returns (kind, detail): kind ok | mismatch |
    depth_skew; detail's FIRST LINE is the coarse signature."""
    if isinstance(guest_rec, V.Miss):
        return "mismatch", "guest_internal_miss\nreasons: %s" % list(guest_rec.reasons)[:3]
    gv = guest_rec.fields["v"].payload
    if guest_rec.fields["parse_error"].payload is True:
        return "mismatch", "guest_parse_error\nreasons: %s" % (
            list(gv.reasons)[:3] if isinstance(gv, V.Miss) else gv)
    host_result = host_env_vars.get("__result")
    hv = host_result.payload if host_result is not None else None
    if hv is None:
        return "mismatch", "host_missing_result"
    # depth skew: exactly one side ran out of depth budget
    if _depth_missed(V, hv) != _depth_missed(V, gv) and \
       (isinstance(hv, V.Miss) != isinstance(gv, V.Miss)):
        return "depth_skew", "one-sided depth miss"
    ok, path = agree(V, hv, gv)
    if not ok:
        return "mismatch", "value %s\nhost:  %s\nguest: %s" % (
            path, _render(V, hv), _render(V, gv))
    hchecks = [(label, bool(okc)) for label, okc in host_checks]
    gc = guest_rec.fields["checks"].payload
    if isinstance(gc, V.Miss):
        return "mismatch", "guest_checks_miss"
    gchecks = [(c.payload.fields["label"].payload, c.payload.fields["pass"].payload is True)
               for c in gc]
    if hchecks != gchecks:
        return "mismatch", "checks %d-vs-%d\nhost:  %s\nguest: %s" % (
            len(hchecks), len(gchecks), hchecks[:6], gchecks[:6])
    return "ok", ""


def _render(V, p):
    try:
        from importlib import import_module
        return import_module(V.__name__).full_show(p)[:200]
    except Exception:  # noqa: BLE001 — rendering is best-effort diagnostics
        return repr(p)[:200]


def scrub_record_line(names):
    scrub = ('%s: (%s rescue (if contains(join(reasons(%s), "|"), "depth") '
             '{ "%s" } else { "%s" }))')
    fields = ", ".join(scrub % (n, n, n, DEPTH_SENTINEL, MISS_SENTINEL) for n in names)
    return "let __result = @{%s}\n" % fields


def oracle_self_eval(pkg, src, max_depth=2000, harness=None, why_probe=True):
    """Fifth oracle: run `src` under the host interpreter and under the
    guest evaluator; any non-exempt behavioural difference is a mismatch.
    `src` must be guest-safe; if it does not already end with the __result
    scrub record, one is appended covering every top-level binding (so a
    model can submit a plain program). Round 20: when values agree, the
    why-shape probe re-runs the guest with an op-collecting walk and flags
    guest-reified derivation ops the host derivation never performed."""
    h = harness or harness_for(pkg, max_depth=max_depth)
    V = h.V
    if BANNED.search(src.split("let __result")[0]):
        return O.OracleOutcome(
            "parse_error", GUEST_ORACLE,
            "not guest-safe: uses a provenance builtin (why/snip/steps/at/"
            "blame/diverge/contrast/print) the guest evaluator does not mirror")
    try:
        program = O._parse(pkg, src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return O.OracleOutcome("parse_error", GUEST_ORACLE, type(e).__name__)
    if "__result" not in src:
        names = []
        for stmt in program.stmts:
            n = getattr(stmt, "name", None)
            if n and n not in names:
                names.append(n)
        if not names:
            return O.OracleOutcome("parse_error", GUEST_ORACLE,
                                   "no top-level bindings to compare")
        src = src.rstrip("\n") + "\n" + scrub_record_line(names[:8])
        try:
            program = O._parse(pkg, src)
        except (pkg["LexError"], pkg["ParseError"]) as e:
            return O.OracleOutcome("parse_error", GUEST_ORACLE, type(e).__name__)
    # Round 149: `h` is a long-lived, mutable `GuestHarness` shared across
    # every program in the campaign (built once to avoid re-parsing the
    # ~800-line self_eval.lang library per program). `run_oracle`'s SIGALRM
    # can fire at ANY point inside `h.eval_program`'s call into the shared
    # `self.interp`/`self.env` — a genuine wall-clock race, not a bug in the
    # interrupted statement itself. If it fires mid-mutation (e.g. partway
    # through binding `__gN`), the shared harness is left in an unknown
    # state that can then corrupt an unrelated LATER program's result.
    # Found via 3 guest-differential "mismatches" (round 137, seeds 141/142)
    # that could not be reproduced standalone OR by replaying the identical
    # program sequence into a fresh harness — real, wall-clock-load-
    # dependent timeouts elsewhere in the same campaign are the only
    # remaining variable, and round 137 ran this campaign alongside a live
    # 5-worker mutation campaign saturating the CPU. Evicting the cached
    # harness on ANY exception (timeout or otherwise) bounds the blast
    # radius of one bad interrupt to the one program that hit it — the next
    # program pays a fresh-harness rebuild instead of inheriting corruption.
    try:
        interp, env, _out = O._run_ast(pkg, program, max_depth=max_depth)
        guest_rec = h.eval_program(src)
    except BaseException:
        _HARNESSES.pop(pkg["name"], None)
        raise
    kind, detail = compare_behaviours(
        V, env.vars, [(c["label"], c["ok"]) for c in interp.checks], guest_rec)
    if kind == "depth_skew":
        return O.OracleOutcome("ok", GUEST_ORACLE, "depth_skew (exempt)")
    if kind == "ok" and why_probe:
        names = [getattr(s, "name", None) for s in program.stmts]
        names = [n for n in names if n and not n.startswith("__")]
        pk, pd = why_shape_probe(V, h, src, env.vars, names)
        if pk == "mismatch":
            return O.OracleOutcome("mismatch", GUEST_ORACLE, pd)
    return O.OracleOutcome(kind, GUEST_ORACLE, detail)


O.ORACLES[GUEST_ORACLE] = oracle_self_eval


# ---------------------------------------------------------------- campaign --

def fuzz_guest(seed=0, n=200, root=WHENCE_ROOT, timeout_s=8.0, max_depth=2000,
               stress_rate=0.7, do_shrink=True, on_program=None):
    """A guest-differential campaign: n generated guest-safe programs, one
    shrunk reproducer per mismatch signature."""
    pkg = load_whence(root, "guestcamp")
    pkg["root"] = root
    camp = O.OracleCampaign((GUEST_ORACLE,))
    import time
    t0 = time.time()
    for i in range(n):
        s = seed * 1000003 + i
        src = generate_guest_program(s, stress_rate=stress_rate)
        camp.programs += 1
        o = O.run_oracle(GUEST_ORACLE, pkg, src, timeout_s=timeout_s,
                         max_depth=max_depth, root=root)
        camp.counts[(GUEST_ORACLE, o.kind)] = camp.counts.get((GUEST_ORACLE, o.kind), 0) + 1
        if on_program:
            on_program(s, src, o)
        sig = O.signature(o)
        if o.kind in ("crash", "mismatch") and sig not in camp.findings:
            f = O.Finding(sig, s, src, o)
            if do_shrink:
                def keep(cand, sig=sig):
                    return O.signature(O.run_oracle(
                        GUEST_ORACLE, pkg, cand, timeout_s=timeout_s,
                        max_depth=max_depth, root=root)) == sig
                f.minimized = shrink(src, keep)
            camp.findings[sig] = f
    camp.seconds = time.time() - t0
    return camp


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--no-shrink", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    c = fuzz_guest(a.seed, a.n, timeout_s=a.timeout, do_shrink=not a.no_shrink)
    print(c.summary())
    if a.show:
        for sig, f in c.findings.items():
            print("\n### %s\n%s\n--- detail:\n%s" % (" | ".join(sig),
                                                     f.minimized or f.src, f.outcome.detail))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(c.as_dict(), fh, indent=1)
