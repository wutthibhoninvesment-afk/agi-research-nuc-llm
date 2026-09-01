#!/usr/bin/env python3
"""polarity — which mutation DIRECTION can each guest `check` statement see?

Round 420 (language C). Round 416 ran 30 check-pins over the guest evaluator
in `examples/self_eval.lang`, pointing eleven mechanisms in BOTH directions
(`-` the rule does less, `+` the rule does more) and found *both directions
guarded: 0 of 11*. Five pins ended `shadowed` — the label that names the rule
stayed green while other checks went red — and round 416 argued each one by
hand, in the pin's `why` field. Three of the five arguments have the same
shape, and it is a shape a machine can check:

    EP05p  "A `missed(...)` guardian is monotone in exactly this direction."
    EP08p  "A `not is_num(...)` guardian is monotone in this direction by
            construction."
    EP09p  "`missed(...)` is monotone in 'refuses more'."   (round 416's own
            comment in the guest file, above the killer it wrote)

That is not a fact about the mutant. It is a fact about the PREDICATE, and it
is decidable from the check's expression AST with nothing running: a
predicate that is monotone increasing along "the evaluator refuses more /
says more" cannot be falsified by an edit that makes the evaluator refuse
more or say more, whatever the edit does.

So this module answers, statically, for each `check` in a guest file:

    blind(check) subset of {'+', '-'}

`'+'` in the set means *this check cannot go red when the rule it names
starts doing MORE*; `'-'`, likewise, for doing less. A check with an empty
set is TWO-SIDED as far as this analysis can tell, and the honest reading of
the empty set is the second half of that sentence — see `Coverage` below.

The direction axis, and the two orders round 420 found were not one order
------------------------------------------------------------------------
The order this monotonicity is taken over is not numeric, and — this is the
round's finding — it is NOT the order round 416's `dir` field names. `dir`
records a change to the RULE ("the rule does more"); monotonicity is a
property of the OBSERVATION ("the value this check reads got bigger"). The
two coincide often enough that round 416's hand argument read as general,
and they came apart twice in 34 pins:

    EP11p  `contains(reasons(...)[0], "return value expected num, got str")`
           is monotone under APPENDING to the reason. The `+` edit made the
           evaluator say strictly more — and said it in the MIDDLE
           ("return value" -> "return value of g"), which destroys
           containment. Guarded, though this analysis calls it `+`-blind.
    EP10m  `is_guess(gv(...))` is monotone under a rule that ACCEPTS more.
           The `-` edit made `apply_binop` delegate LESS, and the observed
           value stopped being a Guess at all. Guarded, though this analysis
           calls it `-`-blind.

So each atom below carries the PRECONDITION its monotonicity rests on
(`refusal`, `append_only`, `kind_stable`), and `law` prints a violation
together with that precondition — because the useful output is not "the law
is false" but "this edit left the order the check is monotone along".

Coverage, and why the empty set is not a claim
----------------------------------------------
`blind` is a LOWER bound: it collects the directions this analysis can PROVE
are invisible. An empty set therefore means "not shown one-sided", not "shown
two-sided". Every check whose top-level shape this module does not have a
rule for is reported `unknown=True` alongside its empty set, and the summary
prints the unknown share, because a coverage number that hides its own
denominator is the failure round 417 named. The `law` command below counts
only POSITIVE blindness for exactly this reason: an `unknown` check can never
create a violation, so the law stays falsifiable rather than merely unrefuted.

The law this module tests
-------------------------
    BLIND(guardian, d)  =>  NOT guarded(pin)      for a pin with dir d

Necessary-condition-shaped, not sufficient: a non-blind guardian may still be
`inert` because the edit changed nothing it looks at. So the falsifiable
direction is the contrapositive — a pin measured `guarded` must never have a
guardian this module calls blind in that pin's `dir`.

MEASURED, round 420, over round 416's 34 pins: **2 violations**, both named
above, both a broken precondition rather than a broken predicate. The law is
therefore reported as CONDITIONAL — sound exactly when the pin's edit
respects the guardian's precondition — and `law` partitions its output that
way instead of printing a pass/fail.

All THREE preconditions are DECIDED from the edit alone
-------------------------------------------------------
Round 426 built `edit_precondition` for `append_only`; round 428 built
`refusal_precondition` for `refusal`; round 434 built `kind_precondition`
for `kind_stable`, the last one. A conditional law whose condition is only
ever PRINTED is indistinguishable from an unconditional one and becomes an
unfalsifiable excuse, which is why all three deciders read the edit and
never a verdict, return three values with `broken` as a positive finding,
and are reported rather than applied.

Measured consequence, round 434: EP10m -- the ONE `guarded`-although-blind
pin in this program's whole recorded corpus that nothing had decided -- is
`broken`, mechanising round 420's hand argument. The law-scoped contingency
table goes [[9,0],[0,2]] -> [[10,0],[0,3]], Fisher p 0.0182 -> 0.0035, with
no campaign re-run. `test_no_violation_in_the_recorded_corpus_is_undecided_any_more`.

With two deciders there is a new way to be wrong, and round 428 checks for
it rather than arguing it: each pin is ROUTED to the precondition its own
guardian's blindness rests on, and a `holds` or `broken` produced by any
other decider is DEMOTED to undecided (`pre_mismatch`). On round 422's
23-pin registry 14 pins rest on something other than `append_only` — 9 on
`refusal`, 5 on nothing at all because their guardian is not blind — and
round 426's single decider answered for all 23 alike. No recorded number is
wrong: not one of those 14 has ever been a violation, so the hazard was
latent. `test_the_wrong_question_hazard_is_latent_in_every_recorded_artefact`
is what says so, and what goes red if a future campaign changes it.

What it deliberately does NOT explain
-------------------------------------
A `shadowed` verdict has (at least) two independent causes, and this module
sees exactly one of them:

  (a) PREDICATE BLINDNESS — the guardian's predicate is monotone in the
      edit's direction. Static; this module finds it; the fix is a new
      PREDICATE over the same probe.
  (b) PROBE AGREEMENT — the probe is a value on which the original rule and
      its replacement AGREE, so nothing the predicate looks at changed at
      all. Round 414's finding ("the probe that agreed with both rules", pin
      CP02). Dynamic; invisible here; a new predicate over the same probe
      fixes NOTHING, and the fix is a new PROBE.

Confusing the two costs a round: they call for opposite edits. Which one a
given `shadowed` pin has is settled by experiment, not by this file — add the
two-sided predicate over the same probe and re-measure. See round 420's
knowledge file, §4.

Usage
-----
    python3 polarity.py classify examples/self_eval.lang [--verbose]
    python3 polarity.py law <pins.json> <run.json>
    python3 polarity.py audit <pins.json> [run.json]
    python3 polarity.py repoint <pins.json> <run.json> [--emit out.json]
    python3 polarity.py precondition <pins.json> [run.json]
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from whence import ast_nodes as A          # noqa: E402
from whence import parser as P             # noqa: E402
import checkpin as CP                      # noqa: E402

PLUS = "+"
MINUS = "-"
BOTH = frozenset((PLUS, MINUS))
NEITHER = frozenset()

#: The order this analysis is monotone along is NOT "the rule does more".
#: It is an order on what the check OBSERVES, and round 420 measured the two
#: coming apart. Every atom below is therefore recorded with the PRECONDITION
#: its monotonicity rests on, and `law` reports a violation together with the
#: precondition the edit broke rather than as a bare counterexample.
#:
#: `refusal`      an edge that only ever turns a value into a miss. `missed(E)`
#:                is monotone along it unconditionally: nothing turns a miss
#:                back into a value.
#: `append_only`  an edge that only ever APPENDS to the observed text.
#:                `contains(A, s)` is monotone along THAT and not along text
#:                growth in general -- an INFIX insertion ("return value" ->
#:                "return value of g") destroys containment while making the
#:                evaluator say strictly more. Round 416's killers were all
#:                append-shaped ("appending a clause the host never emits"),
#:                which is why the argument read as general when it is not.
#: `kind_stable`  an edge that does not change the KIND of the observed value.
#:                `is_guess(E)` is a test on the evaluator's OUTPUT, not on
#:                how permissive the rule is, so an edit that makes the rule
#:                fire LESS and thereby returns a plain bool instead of a
#:                Guess is seen by it, in the direction this table calls blind.
PRE_REFUSAL = "refusal"
PRE_APPEND_ONLY = "append_only"
PRE_KIND_STABLE = "kind_stable"

#: name -> (blind direction, precondition). `has` sits with `contains`: a
#: record only ever gains fields along `+`, so presence survives, and the
#: analogue of an infix insertion (a key RENAMED rather than added) breaks it
#: the same way.
MONOTONE_BUILTINS = {
    "missed": (PLUS, PRE_REFUSAL),
    "contains": (PLUS, PRE_APPEND_ONLY),
    "has": (PLUS, PRE_APPEND_ONLY),
    "is_guess": (MINUS, PRE_KIND_STABLE),
}

#: A guest-defined predicate named `is_*` is read as a positive type test,
#: i.e. `-`-blind under `kind_stable`. This is a NAMING convention, not a
#: proof, and it is the one assumption here that the corpus rather than the
#: language justifies: `self_eval.lang` defines `is_num`, `is_list`,
#: `is_bool`, `is_str`, `is_callable`, `is_guess_val` and `is_rec`, every one
#: a single-argument value test returning a bool. `classify_file` reports how
#: many checks the convention was used on, so it carries its own denominator.
IS_PREFIX = "is_"

TWO_SIDED_OPS = ("==", "!=", "<", ">", "<=", ">=")


class Verdict(object):
    """One check's static polarity.

    `blind` is the proven-invisible direction set; `unknown` records that
    some node on the way down had no rule, so `blind` is a lower bound for
    a reason this object can name rather than a lower bound in general.
    """

    __slots__ = ("label", "line", "blind", "unknown", "reason", "pre",
                 "kinds")

    def __init__(self, label, line, blind, unknown, reason, pre=(),
                 kinds=()):
        self.label = label
        self.line = line
        self.blind = frozenset(blind)
        self.unknown = bool(unknown)
        self.reason = reason
        #: the preconditions every blind direction above rests on. Empty
        #: when `blind` is empty. A caller that reports blindness WITHOUT
        #: reporting these is making the claim round 420 disproved.
        self.pre = tuple(sorted(set(pre)))
        #: Round 434. The KINDS this guardian's type tests probe, which is
        #: what `kind_stable`'s decider has to be routed to: the question is
        #: not "did the kind change" but "did the value stop being a K", for
        #: the K this check looks at. Empty for a guardian with no resolvable
        #: type test, which is `unknown` and never `holds`.
        self.kinds = tuple(sorted(set(kinds)))

    @property
    def one_sided(self):
        return bool(self.blind)

    def __repr__(self):
        return "Verdict(%r, blind=%s, pre=%s, unknown=%s)" % (
            self.label, "".join(sorted(self.blind)) or "-none-",
            ",".join(self.pre) or "-", self.unknown)


def _flip(dirs):
    """`not p` inverts monotonicity: blind to `+` becomes blind to `-`."""
    out = set()
    if PLUS in dirs:
        out.add(MINUS)
    if MINUS in dirs:
        out.add(PLUS)
    return frozenset(out)


def _callee_name(node):
    if isinstance(node, A.Call) and isinstance(node.fn, A.NameRef):
        return node.fn.name
    return None


def _analyse(expr, guest_fns):
    """`(blind_dirs, unknown, reason, preconditions)` for one expression.

    `and`/`or` intersect their operands' direction sets, which is the only
    correct rule and not merely the conservative one: monotonicity along a
    fixed order is closed under both connectives, so a conjunction is blind to
    `d` exactly when BOTH conjuncts are. That is what makes round 416's EP03
    guardian -- `contains(A, s) and not contains(A, t)`, a `+`-blind conjunct
    meeting a `-`-blind one -- come out two-sided, which is the answer its
    author intended and the reason it is the one check in the file that caught
    a direction nobody wrote it for.

    Preconditions UNION rather than intersect, and they do so even across a
    connective that empties the direction set. A caller therefore reads them
    as "the assumptions this verdict would rest on", not "the assumptions it
    does rest on"; `blind` empty means no assumption is load-bearing.
    """
    if isinstance(expr, A.Unary) and expr.op == "not":
        inner, unk, why, pre = _analyse(expr.operand, guest_fns)
        return _flip(inner), unk, "not(%s)" % why, pre

    if isinstance(expr, A.Binary):
        if expr.op in ("and", "or"):
            lb, lu, lw, lp = _analyse(expr.left, guest_fns)
            rb, ru, rw, rp = _analyse(expr.right, guest_fns)
            return (lb & rb, lu or ru, "%s %s %s" % (lw, expr.op, rw),
                    tuple(lp) + tuple(rp))
        if expr.op in TWO_SIDED_OPS:
            return NEITHER, False, "two-sided `%s`" % expr.op, ()
        # Arithmetic in predicate position is not a boolean claim at all.
        return NEITHER, True, "non-boolean binary `%s`" % expr.op, ()

    name = _callee_name(expr)
    if name is not None:
        hit = MONOTONE_BUILTINS.get(name)
        if hit is not None:
            d, pre = hit
            return frozenset((d,)), False, "%s(...)" % name, (pre,)
        if name.startswith(IS_PREFIX) and name in guest_fns:
            return (frozenset((MINUS,)), False,
                    "guest type test %s(...)" % name, (PRE_KIND_STABLE,))
        return NEITHER, True, "call to `%s`" % name, ()

    if isinstance(expr, A.BoolLit):
        # A constant predicate is blind to everything; it is also not a
        # check. Reported as BOTH rather than swallowed, so `classify` names
        # it instead of scoring it as two-sided.
        return BOTH, False, "constant", ()

    return NEITHER, True, type(expr).__name__, ()


def guest_functions(prog):
    """Names defined by the guest file itself: `fn f(..)` and `let f = fn`."""
    out = set()
    for st in prog.stmts:
        if isinstance(st, A.FnDef):
            out.add(st.name)
        elif isinstance(st, A.Let) and isinstance(st.expr, A.FnExpr):
            out.add(st.name)
    return out


def classify_source(src):
    """`[Verdict]`, one per top-level `check` in guest source `src`."""
    prog = P.parse(src)
    guest_fns = guest_functions(prog)
    out = []
    for st in prog.stmts:
        if not isinstance(st, A.Check):
            continue
        blind, unknown, reason, pre = _analyse(st.expr, guest_fns)
        out.append(Verdict(st.label, st.line, blind, unknown, reason, pre,
                           guardian_kinds(st.expr, guest_fns)))
    return out


def classify_file(path):
    with open(path, encoding="utf-8") as f:
        return classify_source(f.read())


def summarise(verdicts):
    n = len(verdicts)
    plus = sum(1 for v in verdicts if PLUS in v.blind)
    minus = sum(1 for v in verdicts if MINUS in v.blind)
    both = sum(1 for v in verdicts if v.blind == BOTH)
    one = sum(1 for v in verdicts if v.one_sided)
    unknown = sum(1 for v in verdicts if v.unknown)
    kinded = sum(1 for v in verdicts if v.kinds)
    kind_rests = sum(1 for v in verdicts if PRE_KIND_STABLE in v.pre)
    return {
        "n": n,
        #: Round 434. `kind_stable` rests on a NAMING convention twice over:
        #: `is_*` means a type test, and `is_<k>` names the kind `k`. The
        #: first denominator has been printed since round 420; this is the
        #: second, and a check that rests on `kind_stable` while resolving
        #: no kind is the case `kind_precondition` answers `unknown` for.
        "kind_tested": kinded,
        "rests_on_kind_stable": kind_rests,
        "kind_unresolved": sum(1 for v in verdicts
                               if PRE_KIND_STABLE in v.pre and not v.kinds),
        "blind_plus": plus,
        "blind_minus": minus,
        "blind_both": both,
        "one_sided": one,
        "two_sided_or_unknown": n - one,
        "unknown": unknown,
        "one_sided_pct": (100.0 * one / n) if n else None,
        "unknown_pct": (100.0 * unknown / n) if n else None,
    }


# --- the law: BLIND(guardian, dir) => NOT guarded --------------------------

def check_law(pins, results, verdicts, pre_status=None):
    """Join measured pin verdicts to static polarity and test the law.

    `pins` is the registry's `pins` list (each carrying `dir` and
    `guardian`), `results` a `checkpin run` result list (each carrying
    `id` and `verdict`), `verdicts` the output of `classify_file` on the
    guest file those pins were measured against.

    Returns a dict with `violations` (guarded pins whose guardian is blind
    in that pin's dir -- these refute the law), `confirmations` (non-guarded
    pins whose guardian IS blind, the cases the law explains) and `unmatched`
    (a guardian label with no check of that name, i.e. registry rot).

    `pre_status` (round 426, optional) is `precondition_map`'s output. The
    law is conditional on each atom's precondition, and with the map present
    `violations` is partitioned three ways: `strict_violations` (the
    precondition is ESTABLISHED for this pin's edit, so the counterexample
    stands), `excused` (the edit demonstrably BREAKS it) and `undecided`
    (nothing decided it). All three are returned and all three are printed;
    the partition is reported, never applied silently. WITHOUT the map every
    violation is strict -- an absent precondition decision does not excuse
    anything, which is the only reading that leaves the law falsifiable.

    Round 428 adds the fourth way a row lands in `undecided`: `pre_mismatch`,
    set when the decider that produced `pre_status` did not ask about the
    precondition this pin's guardian actually rests on. Round 426 shipped one
    decider (`append_only`) and applied its answer to every pin alike; on
    round 422's registry 14 of 23 pins rest on something else. No recorded
    violation was ever mis-bucketed by it -- every violation this program has
    measured happens to rest on `append_only` -- but with a second decider in
    the module the mistake becomes reachable, so it is checked rather than
    argued. A mismatched row is demoted to `undecided`, never promoted:
    excusing a violation on the wrong precondition is the unfalsifiability
    the three guards exist to prevent.
    """
    by_label = {}
    dupes = set()
    for v in verdicts:
        if v.label in by_label:
            dupes.add(v.label)
        by_label[v.label] = v
    by_id = {p["id"]: p for p in pins}

    violations, confirmations, unmatched, other = [], [], [], []
    for r in results:
        pin = by_id.get(r["id"])
        if pin is None or "dir" not in pin:
            continue                       # a control has no direction
        d = pin["dir"]
        v = by_label.get(r["guardian"])
        if v is None:
            unmatched.append((r["id"], r["guardian"]))
            continue
        blind = d in v.blind
        row = {"id": r["id"], "dir": d, "verdict": r["verdict"],
               "guardian": r["guardian"], "blind": blind,
               "shape": v.reason, "unknown": v.unknown, "pre": list(v.pre),
               "dupe_label": v.label in dupes}
        if blind and r["verdict"] == "guarded":
            violations.append(row)
        elif blind:
            confirmations.append(row)
        else:
            other.append(row)
    for row in violations:
        m = ((pre_status or {}).get(row["id"]) or {})
        row["pre_status"] = m.get("status")
        # ROUND 428. `pre` is what THIS pin's guardian's blindness rests on;
        # `decided_over` is what the decider that produced `pre_status`
        # actually asked about. Rounds 426-427 compared neither, so a
        # `missed(...)` pin could be called STRICT ("`append_only`
        # established, the law is refuted here") on an answer to a question
        # it never asked. A row with no `decided_over` predates the field
        # and is read as `append_only`, which is what it was.
        decided = tuple(m.get("decided_over", (PRE_APPEND_ONLY,)))
        row["pre_decided_over"] = list(decided)
        row["pre_mismatch"] = bool(row["pre"]) and not set(row["pre"]) <= set(
            decided)
    if pre_status is None:
        excused, undecided, strict = [], [], list(violations)
    else:
        excused = [r for r in violations
                   if r["pre_status"] == PRE_BROKEN and not r["pre_mismatch"]]
        strict = [r for r in violations
                  if r["pre_status"] == PRE_HOLDS and not r["pre_mismatch"]]
        settled = {id(r) for r in excused} | {id(r) for r in strict}
        undecided = [r for r in violations if id(r) not in settled]
    return {"violations": violations, "confirmations": confirmations,
            "unmatched": unmatched, "sighted": other,
            "excused": excused, "undecided": undecided,
            "strict_violations": strict,
            "n_scored": len(violations) + len(confirmations) + len(other)}


# --- audit: a pin whose DIRECTION its guardian cannot see -----------------

def audit_registry(pins, verdicts, results=None):
    """Flag every pin whose `dir` lies in its guardian's blind set.

    This is the round-420 instrument, and it runs BEFORE any campaign: a pin
    that points a `+` edit at a `+`-blind guardian cannot come back `guarded`
    no matter what the code does, so measuring it costs a run and learns
    nothing about the code. Round 416 paid ~100 s per pin to discover five of
    these and read all five as coverage gaps in the FILE. They are not; each
    is a mispointed pin, and each one's own campaign already reddened a check
    that IS sighted in that direction.

    `results` (a `checkpin run` result list) is optional and only makes the
    report better: when it is present, a mispointed pin's candidate
    replacement guardians are drawn from the checks that ACTUALLY went red
    under that pin (`co_red`), filtered to the ones sighted in its direction.
    Without it the candidates are every sighted check in the file, which is a
    much weaker suggestion -- so the two modes are reported distinctly rather
    than blended.
    """
    by_label = {v.label: v for v in verdicts}
    co_red, measured = {}, {}
    if results:
        for r in results:
            co_red[r["id"]] = list(r.get("co_red") or ())
            measured[r["id"]] = r.get("verdict")
    sighted_all = None

    rows = []
    for pin in pins:
        d = pin.get("dir")
        if d not in (PLUS, MINUS):
            continue
        v = by_label.get(pin["guardian"])
        if v is None:
            rows.append({"id": pin["id"], "dir": d, "status": "unlocatable",
                         "guardian": pin["guardian"], "candidates": [],
                         "candidate_source": None, "pre": []})
            continue
        if d not in v.blind:
            rows.append({"id": pin["id"], "dir": d, "status": "ok",
                         "guardian": pin["guardian"], "candidates": [],
                         "candidate_source": None, "pre": list(v.pre)})
            continue
        if measured.get(pin["id"]) == "guarded":
            # Measured guarded although statically blind: the edit did not
            # respect the precondition this blindness rests on, so the flag
            # is a FALSE POSITIVE and the run says so. Reported as its own
            # status rather than dropped, because the precondition it names
            # is the round-420 finding and suppressing it silently would
            # hide the very thing that makes the static rule conditional.
            rows.append({"id": pin["id"], "dir": d,
                         "status": "precondition_broken",
                         "guardian": pin["guardian"], "candidates": [],
                         "candidate_source": None, "pre": list(v.pre),
                         "shape": v.reason})
            continue
        gap = None
        if pin["id"] in co_red:
            known = [c for c in co_red[pin["id"]] if c in by_label]
            cands = [c for c in known if d not in by_label[c].blind]
            dropped = [c for c in known if d in by_label[c].blind]
            gap = not known
            src = "co_red"
        else:
            if sighted_all is None:
                sighted_all = [x.label for x in verdicts]
            cands = [c for c in sighted_all if d not in by_label[c].blind]
            dropped = []
            src = "whole file"
        rows.append({"id": pin["id"], "dir": d, "status": "mispointed",
                     "guardian": pin["guardian"], "candidates": cands,
                     "dropped_blind": dropped, "gap": gap,
                     "candidate_source": src, "pre": list(v.pre),
                     "shape": v.reason})
    return rows


def _cmd_audit(args):
    if not args:
        print("usage: polarity.py audit <pins.json> [run.json]",
              file=sys.stderr)
        return 2
    with open(args[0], encoding="utf-8") as f:
        reg = json.load(f)
    results = None
    if len(args) > 1:
        with open(args[1], encoding="utf-8") as f:
            results = json.load(f)["results"]
    guest_files = sorted({p["guest_file"] for p in reg["pins"]})
    if len(guest_files) != 1:
        print("audit: registry spans %d guest files; run one at a time"
              % len(guest_files), file=sys.stderr)
        return 2
    vs = classify_file(os.path.join(_HERE, guest_files[0]))
    rows = audit_registry(reg["pins"], vs, results)
    bad = [r for r in rows if r["status"] == "mispointed"]
    lost = [r for r in rows if r["status"] == "unlocatable"]
    fp = [r for r in rows if r["status"] == "precondition_broken"]
    print("audit: %s — %d directional pin(s), %d MISPOINTED, %d unlocatable, "
          "%d precondition-broken" % (guest_files[0], len(rows), len(bad),
                                      len(lost), len(fp)))
    for r in bad:
        print("  *** %-7s dir %s is in the blind set of its guardian"
              % (r["id"], r["dir"]))
        print("        guardian : %s" % r["guardian"])
        print("        shape    : %s   (precondition: %s)"
              % (r["shape"], ",".join(r["pre"]) or "-"))
        if r["candidates"]:
            print("        sighted candidates (%s):" % r["candidate_source"])
            for c in r["candidates"]:
                print("          - %s" % c)
        elif r["gap"]:
            print("        NO candidate at all — nothing in the file went "
                  "red. This one IS a coverage gap.")
        elif r["gap"] is False:
            print("        no SIGHTED candidate, but %d red check(s) were "
                  "dropped by the sightedness filter — NOT a coverage gap: %s"
                  % (len(r["dropped_blind"]), "; ".join(r["dropped_blind"])))
        else:
            print("        NO sighted candidate in the whole file. Whether "
                  "this is a coverage gap needs a run — pass run.json.")
    for r in fp:
        print("  (fp) %-7s dir %s statically %s-blind [%s] but MEASURED "
              "guarded:" % (r["id"], r["dir"], r["dir"], r["shape"][:30]))
        print("        the edit broke the precondition `%s`, so the check "
              "saw it after all" % (",".join(r["pre"]) or "-"))
    for r in lost:
        print("  ??? %-7s guardian names no check in the file: %s"
              % (r["id"], r["guardian"]))
    if os.environ.get("POLARITY_JSON"):
        with open(os.environ["POLARITY_JSON"], "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        print("wrote %s" % os.environ["POLARITY_JSON"])
    return 0 if not bad and not lost else 1


def repoint(pins, verdicts, results):
    """For every pin that did NOT come back `guarded`, name the checks that
    could have.

    This is the post-run half of the audit, and it is strictly stronger than
    the static half because it reads what actually went red. A `shadowed`
    verdict says "the file distinguished the rule; the named check did not",
    so the file already contains the right guardian -- it is in `co_red`.
    Filtering `co_red` by polarity leaves the ones that are also SIGHTED in
    the pin's direction, and those are the honest replacements.

    Round 420 measured this over round 416's five `shadowed` findings: all
    five have at least one sighted, already-red candidate. Round 416 read
    them as five coverage gaps in `self_eval.lang`; they are five mispointed
    pins, and the difference matters because the two call for opposite
    repairs -- a new `check` in the guest file versus one edited string in
    the registry.
    """
    by_label = {v.label: v for v in verdicts}
    by_id = {p["id"]: p for p in pins}
    out = []
    for r in results:
        if r["verdict"] == "guarded":
            continue
        pin = by_id.get(r["id"])
        if pin is None or pin.get("dir") not in (PLUS, MINUS):
            continue
        d = pin["dir"]
        co = [c for c in (r.get("co_red") or ()) if c in by_label]
        cands = [c for c in co if d not in by_label[c].blind]
        blind_cands = [c for c in co if d in by_label[c].blind]
        out.append({"id": r["id"], "dir": d, "verdict": r["verdict"],
                    "guardian": r["guardian"],
                    "guardian_blind": bool(by_label.get(r["guardian"]) and
                                           d in by_label[r["guardian"]].blind),
                    "sighted_candidates": cands,
                    "blind_candidates": blind_cands,
                    "gap": not co})
    return out


def cored_polarity(pins, results, verdicts):
    """How much of the measured evidence does the sightedness filter drop?

    Round 426. `repoint` and `audit` both keep only the co-red checks that
    are SIGHTED in the pin's direction, and both then call an empty result a
    coverage gap. That filter is a same-rule theorem applied across rules:
    `d in blind(C)` says check `C` cannot see an edit to the rule `C` NAMES
    moving in direction `d`; a co-red check names a DIFFERENT rule, and the
    pin's edit is not an edit to it in any direction, so the blindness has
    no purchase. This function measures the size of the mistake instead of
    arguing about it -- `blind` here is the count of checks that DID go red
    and are nevertheless discarded.
    """
    by_label = {v.label: v for v in verdicts}
    by_id = {p["id"]: p for p in pins}
    total = blind = unmatched = 0
    false_gaps = []
    for r in results:
        pin = by_id.get(r["id"])
        if pin is None or pin.get("dir") not in (PLUS, MINUS):
            continue
        if r.get("verdict") == "guarded":
            continue          # the filter never runs on a guarded pin
        d = pin["dir"]
        co = list(r.get("co_red") or ())
        known = [c for c in co if c in by_label]
        unmatched += len(co) - len(known)
        total += len(known)
        b = [c for c in known if d in by_label[c].blind]
        blind += len(b)
        if known and len(b) == len(known):
            false_gaps.append(r["id"])
    return {"co_red_total": total, "co_red_blind": blind,
            "co_red_unmatched": unmatched, "false_gaps": false_gaps}


def _cmd_repoint(args):
    if len(args) < 2:
        print("usage: polarity.py repoint <pins.json> <run.json> "
              "[--emit out.json]", file=sys.stderr)
        return 2
    emit = None
    if "--emit" in args:
        emit = args[args.index("--emit") + 1]
        args = [a for i, a in enumerate(args)
                if a != "--emit" and args[i - 1] != "--emit"]
    with open(args[0], encoding="utf-8") as f:
        reg = json.load(f)
    with open(args[1], encoding="utf-8") as f:
        run = json.load(f)
    guest_files = sorted({p["guest_file"] for p in reg["pins"]})
    vs = classify_file(os.path.join(_HERE, guest_files[0]))
    rows = repoint(reg["pins"], vs, run["results"])
    print("repoint: %d non-guarded directional pin(s)" % len(rows))
    for r in rows:
        print("  %-7s dir %s  %-10s guardian %s-blind=%s"
              % (r["id"], r["dir"], r["verdict"], r["dir"],
                 r["guardian_blind"]))
        print("      named   : %s" % r["guardian"])
        if r["sighted_candidates"]:
            for c in r["sighted_candidates"]:
                print("      sighted : %s" % c)
        elif r["gap"]:
            print("      sighted : (none) — a genuine coverage gap: NOTHING "
                  "in the file went red")
        else:
            print("      sighted : (none sighted) — but %d check(s) below DID "
                  "go red, so this is NOT a coverage gap"
                  % len(r["blind_candidates"]))
        for c in r["blind_candidates"]:
            print("      blind   : %s   (red, and dropped by the sightedness "
                  "filter)" % c)
    share = cored_polarity(reg["pins"], run["results"], vs)
    print("  co-red evidence: %d red check(s) named across these pins, %d of "
          "them (%.1f%%) dropped by the sightedness filter; %d pin(s) have a "
          "red check and NO sighted one (%s)"
          % (share["co_red_total"], share["co_red_blind"],
             100.0 * share["co_red_blind"] / max(share["co_red_total"], 1),
             len(share["false_gaps"]), ", ".join(share["false_gaps"]) or "-"))
    gaps = [r["id"] for r in rows if r["gap"]]
    print("  %d genuine coverage gap(s) — nothing red at all: %s"
          % (len(gaps), ", ".join(gaps) or "-"))
    if emit:
        new = json.loads(json.dumps(reg))
        picked = {r["id"]: r["sighted_candidates"][0] for r in rows
                  if r["sighted_candidates"]}
        for pin in new["pins"]:
            if pin["id"] in picked:
                pin["guardian_was"] = pin["guardian"]
                pin["guardian"] = picked[pin["id"]]
        new["_"] = ("Round 420: %d guardian(s) re-pointed by `polarity.py "
                    "repoint` to a check SIGHTED in the pin's own direction. "
                    "`guardian_was` keeps the label round 416 named. Derived "
                    "file — regenerate, do not hand-edit. Round 434: the "
                    "registry's NEGATIVE CONTROL pins are carried through "
                    "unrepointed." % len(picked))
        # Round 434. A control is never `guarded`, so `repoint` never names
        # it and the filter below used to drop it: `state/whence/round-420/
        # run-repointed.json` records `controls: []`, i.e. a campaign whose
        # `inert`/`unreachable` verdicts are exactly as unfalsifiable as
        # round 408 §6.2 said they are without one. Round 422's host
        # repointed registry kept its control only because a human built it
        # by hand. Carrying controls costs one guest run and restores the
        # thing the emitted registry was missing.
        new["pins"] = [p for p in new["pins"]
                       if p["id"] in picked or p.get("control_expect")]
        with open(emit, "w", encoding="utf-8") as f:
            json.dump(new, f, indent=2)
        print("wrote %s (%d re-pointed pin(s))" % (emit, len(picked)))
        left = [r["id"] for r in rows
                if not r["sighted_candidates"] and not r["gap"]]
        if left:
            print("  NOT re-pointed, and not gaps either — a red check exists "
                  "but the sightedness filter dropped it: %s" % ", ".join(left))
    return 0


# --- the PRECONDITION: is this pin's EDIT an append? ----------------------
#
# Round 426 (language C). Round 420 found that this module's blindness is a
# property of an order on the OBSERVATION, not of the `dir` field, and it
# recorded the assumption each atom's monotonicity rests on in `pre`. It
# recorded it as PROSE. `law` prints "precondition broken: append_only"
# beside every violation without ever deciding whether the edit broke it —
# the sentence is emitted for all violations alike, so it carries no
# information and cannot be wrong.
#
# It is decidable, and the guest file is the reason: `examples/self_host.lang`
# is Whence, so the edit that a pin applies to it can be parsed with the same
# parser the language ships. `append_only` says the edit only ever APPENDS to
# the observed text; on the AST that is a statement about `+`-chains:
#
#     old:  "expected " + what + ", got "      + show_tok(k) + tok_at(t, p)
#     new:  "expected " + what + ", got "      + show_tok(k) + tok_at(t, p)
#                                                            + " [parser]"
#             -> the old chain is a strict PREFIX of the new one   APPEND
#
#     old:  "expected " + what + ", got "      + show_tok(k) + tok_at(t, p)
#     new:  "expected " + what + " here, got " + show_tok(k) + tok_at(t, p)
#             -> same length, a non-final atom rewritten            INFIX
#
# Those two are pins CP22p and CP22p2 of round 422's registry: the SAME
# direction on the SAME rule under the SAME guardian, planted by that round
# as a discriminator with the note "if both come back the same way the
# precondition is decoration". They did not: CP22p is a finding and CP22p2 is
# `guarded` — the one violation of the law in that whole campaign. So the
# precondition is load-bearing, and this section is what makes it checkable
# by something other than a human reading two Whence functions side by side.
#
# THE HONESTY PROBLEM, and how it is handled. A precondition that excuses
# violations can make any law unfalsifiable: declare every counterexample's
# precondition broken and the law is unrefuted for ever. Three guards:
#
#   1. The decision is made from the EDIT ALONE (`pins.json` + the guest
#      source) and never reads a verdict. `precondition_map` does not take a
#      run.
#   2. It returns THREE values, not two. `broken` is a positive finding — a
#      string-valued expression demonstrably rewritten other than at its end.
#      `unknown` is a delta that is not string-shaped at all, where appending
#      is neither established nor refuted. Only `holds` is a claim.
#   3. `check_law` treats a violation with no `holds` as still a violation
#      unless a precondition map is supplied, and reports `strict_violations`
#      (the law's real counterexamples, precondition established) SEPARATELY
#      from `excused`, with both counts printed. A reader who distrusts the
#      excuse can read the first number and ignore the second.

_PARSE_CACHE = {}


def _parse_cached(src):
    prog = _PARSE_CACHE.get(src)
    if prog is None:
        prog = P.parse(src)
        _PARSE_CACHE[src] = prog
    return prog


#: Slots the PARSER fills in as analysis rather than as a record of what the
#: source says. They must be excluded from both the equality and the delta
#: walk. Measured, round 426: including `Call.tail` alone made CP04p --
#: `str(k.v)` -> `str(k.v) + " (a number)"`, the textbook append -- come out
#: `infix`, because moving a call out of tail position flips the flag the
#: parser set on it and the two `str(k.v)` nodes stop comparing equal.
DERIVED_SLOTS = frozenset((
    "tail",                 # A.Call, set by parser.mark_tails
    "tail_alias_tag",       # A.Block, set by parser.block
    "tail_param_name",      # A.Block, set by parser.block
    "param_call_fact",      # A.FnExpr, set by parser.py
))


def _slots(node):
    return [f for f in type(node).__slots__ if f not in DERIVED_SLOTS]


def _is_concat(node):
    return isinstance(node, A.Binary) and node.op == "+"


def _chain_op(node):
    return node.op if isinstance(node, A.Binary) else None


def _chain_atoms(node, op):
    """Flatten a left-associative chain of one operator into its atoms."""
    if isinstance(node, A.Binary) and node.op == op:
        return _chain_atoms(node.left, op) + _chain_atoms(node.right, op)
    return [node]


def _concat_atoms(node):
    """Flatten a left-associative `+` chain into its atoms, in text order."""
    return _chain_atoms(node, "+")


def _block_value(node):
    """The expression a single-value `{ ... }` block evaluates to.

    An `if`/`else` arm in Whence is a Block, so a branch-selection delta
    (below) would otherwise compare two Blocks and learn nothing. Only the
    unambiguous case is unwrapped -- a block whose tail statement is a bare
    expression -- and anything else is handed back untouched.
    """
    if isinstance(node, A.Block) and node.stmts:
        tail = node.stmts[-1]
        if isinstance(tail, A.ExprStmt) and len(node.stmts) == 1:
            return tail.expr
    return node


def _node_eq(a, b):
    """Structural equality over the source-bearing fields `_simple` declares.

    `Node.line` is deliberately NOT compared: every edit moves the lines
    below it, and a line shift is not a semantic delta. Neither are
    `DERIVED_SLOTS`.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, A.Node):
        return all(_node_eq(getattr(a, f), getattr(b, f)) for f in _slots(a))
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_node_eq(x, y) for x, y in zip(a, b))
    return a == b


def _walk_delta(a, b, out):
    """Collect the SHALLOWEST differing (old, new) pairs of two ASTs.

    A `+` chain is treated as one unit: a difference anywhere inside it
    surfaces as the whole chain, because "is this an append" is a question
    about the chain and left-associativity misaligns a pairwise descent as
    soon as the two chains have different lengths.

    Any OTHER associative chain (`or`, `and`, ...) gets the same treatment
    when the two chains have different LENGTHS, and for the same reason —
    but the opposite consequence. Round 426 measured what happens without
    it: CP06p adds one disjunct to `t == "(" or t == "[" or t == "@{" or
    last_continues(acc)`, a pairwise descent then lines `"["` up against
    `"@{"` and `"@{"` against `"{"`, and the edit is reported as two INFIX
    string rewrites -- a positive `broken` finding manufactured entirely by
    misalignment, on an edit that touches no rendered text at all. Chains of
    equal length are still descended pairwise, which is where a real delta
    inside one disjunct is found.
    """
    if _is_concat(a) or _is_concat(b):
        if not _node_eq(a, b):
            out.append((a, b))
        return
    if type(a) is not type(b):
        out.append((a, b))
        return
    if isinstance(a, A.If) and isinstance(b, A.If):
        # BRANCH SELECTION. A pin whose edit pins a condition to a constant
        # does not rewrite any text at all -- it changes WHICH text is
        # produced, and the two branches may stand in any relation to each
        # other. Round 420 read exactly this shape by hand on EP11p
        # (`if fn_name == "(anonymous)"` -> `if false`, so "return value"
        # becomes "return value of g") and called it the infix insertion
        # that broke `append_only`. Without this case the delta is
        # `<Binary> -> <BoolLit>`, i.e. structural, i.e. undecided: the
        # decider would leave round 420's own worked example unexplained.
        # The test itself lives in `_pinned_branch` (round 428): `refusal`
        # reads the same edit shape and must read it identically.
        picked = _pinned_branch(a, b)
        if picked is not None:
            out.append(picked)
            return
    if isinstance(a, A.Node):
        op = _chain_op(a)
        if op is not None and op == _chain_op(b):
            lhs, rhs = _chain_atoms(a, op), _chain_atoms(b, op)
            if len(lhs) != len(rhs):
                out.append((a, b))
                return
        for f in _slots(a):
            x, y = getattr(a, f), getattr(b, f)
            if isinstance(x, (A.Node, list, tuple)) or \
               isinstance(y, (A.Node, list, tuple)):
                _walk_delta(x, y, out)
            elif x != y:
                out.append((a, b))
                return
        return
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            out.append((a, b))
            return
        for x, y in zip(a, b):
            _walk_delta(x, y, out)
        return
    if a != b:
        out.append((a, b))


DELTA_APPEND = "append"
DELTA_INFIX = "infix"
DELTA_STRUCTURAL = "structural"


def delta_kind(old, new):
    """Classify one (old, new) delta as `append`, `infix` or `structural`."""
    string_shaped = (_is_concat(old) or _is_concat(new)
                     or (isinstance(old, A.Str) and isinstance(new, A.Str)))
    if not string_shaped:
        return DELTA_STRUCTURAL
    lhs, rhs = _concat_atoms(old), _concat_atoms(new)
    if len(rhs) > len(lhs) and all(_node_eq(x, y) for x, y in zip(lhs, rhs)):
        return DELTA_APPEND
    if (len(lhs) == len(rhs) and lhs
            and all(_node_eq(x, y) for x, y in zip(lhs[:-1], rhs[:-1]))):
        x, y = lhs[-1], rhs[-1]
        if (isinstance(x, A.Str) and isinstance(y, A.Str)
                and y.value.startswith(x.value)
                and len(y.value) > len(x.value)):
            return DELTA_APPEND
    return DELTA_INFIX


def _expr_text(node, depth=0):
    """Render an expression back to Whence-ish source. DISPLAY ONLY.

    Never parsed back, and not required to round-trip. It exists because
    `_brief` names a node by its CLASS, and round 428 printed

        unknown: contains(...)  ->  <Binary>

    for the three pins its own next-steps then called "the largest single
    class". That line says something is undecided and hides WHAT is
    undecided, which for a residual proof obligation is the entire content
    of the finding. `+` chains keep `_brief`'s existing rendering, so the
    `append_only` deltas are unchanged.
    """
    if depth > 6:
        return "…"
    if isinstance(node, A.Str):
        return repr(node.value)
    if isinstance(node, A.Num):
        return repr(node.value)
    if isinstance(node, A.BoolLit):
        return "true" if node.value else "false"
    if isinstance(node, A.NameRef):
        return node.name
    if isinstance(node, A.MissLit):
        return "miss"
    if isinstance(node, A.FieldAccess):
        return "%s.%s" % (_expr_text(node.obj, depth + 1), node.name)
    if isinstance(node, A.Index):
        return "%s[%s]" % (_expr_text(node.obj, depth + 1),
                           _expr_text(node.index, depth + 1))
    if isinstance(node, A.Unary):
        inner = _expr_text(node.operand, depth + 1)
        return "not %s" % inner if node.op == "not" else "%s%s" % (node.op,
                                                                   inner)
    if isinstance(node, A.Binary):
        return "(%s %s %s)" % (_expr_text(node.left, depth + 1), node.op,
                               _expr_text(node.right, depth + 1))
    if isinstance(node, A.Call):
        fn = (node.fn.name if isinstance(node.fn, A.NameRef)
              else _expr_text(node.fn, depth + 1))
        return "%s(%s)" % (fn, ", ".join(_expr_text(a, depth + 1)
                                         for a in node.args))
    if isinstance(node, A.ListLit):
        return "[%s]" % ", ".join(_expr_text(x, depth + 1) for x in node.items)
    if isinstance(node, A.If):
        other = ("" if node.otherwise is None
                 else " else { %s }" % _expr_text(
                     _block_value(node.otherwise), depth + 1))
        return "if %s { %s }%s" % (_expr_text(node.cond, depth + 1),
                                   _expr_text(_block_value(node.then),
                                              depth + 1), other)
    if isinstance(node, A.Block):
        v = _block_value(node)
        return _expr_text(v, depth + 1) if v is not node else "{…}"
    if isinstance(node, A.Node):
        return "<%s>" % type(node).__name__
    return repr(node)


def _brief(node, limit=44):
    if isinstance(node, A.Str):
        s = repr(node.value)
    elif _is_concat(node):
        s = " + ".join(_brief(x, 18) for x in _concat_atoms(node))
    elif isinstance(node, A.NameRef):
        s = node.name
    elif isinstance(node, A.Num):
        s = repr(node.value)
    elif isinstance(node, (A.Call, A.Binary, A.Unary, A.If, A.BoolLit)):
        # Round 432: was `%s(...)` for a Call and `<Binary>` for the rest.
        # A residual obligation whose two sides both print as `(...)` is not
        # a report, and the truncation below still bounds the width.
        s = _expr_text(node)
    elif isinstance(node, A.Node):
        s = "<%s>" % type(node).__name__
    elif isinstance(node, (list, tuple)):
        s = "<%d item(s)>" % len(node)
    else:
        s = repr(node)
    return s if len(s) <= limit else s[:limit - 1] + "…"


PRE_HOLDS = "holds"
PRE_BROKEN = "broken"
PRE_UNKNOWN = "unknown"


def edit_precondition(base_src, pin, kinds=()):
    """Does this pin's edit respect `append_only`? Reads no verdict.

    Returns a dict with `status` in {holds, broken, unknown, identity,
    unlocatable, unparsable}, the per-delta `kinds`, and a human-readable
    `deltas` list. `holds` is the only value that is a claim; `broken` is a
    positive finding (a string-valued expression rewritten other than at its
    end) and `unknown` means the edit is not string-shaped, so appending is
    neither established nor refuted.
    """
    try:
        mutant = CP.apply_edit(base_src, pin)
    except Exception as exc:                                  # noqa: BLE001
        return {"status": "unlocatable", "why": str(exc),
                "kinds": [], "deltas": [], "decided_over": (PRE_APPEND_ONLY,)}
    try:
        old = _parse_cached(base_src)
        new = _parse_cached(mutant)
    except Exception as exc:                                  # noqa: BLE001
        return {"status": "unparsable", "why": str(exc),
                "kinds": [], "deltas": [], "decided_over": (PRE_APPEND_ONLY,)}
    pairs = []
    _walk_delta(old, new, pairs)
    kinds = [delta_kind(a, b) for a, b in pairs]
    shown = ["%s: %s  ->  %s" % (k, _brief(a), _brief(b))
             for k, (a, b) in zip(kinds, pairs)]
    if not pairs:
        status = "identity"
    elif DELTA_INFIX in kinds:
        status = PRE_BROKEN
    elif all(k == DELTA_APPEND for k in kinds):
        status = PRE_HOLDS
    else:
        status = PRE_UNKNOWN
    return {"status": status, "why": None, "kinds": kinds, "deltas": shown,
            "decided_over": (PRE_APPEND_ONLY,)}


# --- the SECOND precondition: does this pin's edit only REFUSE? -----------
#
# Round 428 (language C). Round 426 decided `append_only` and closed with
# "`kind_stable` and `refusal` are not decided at all … `refusal` is
# probably the easier of the two — 'does this edit only ever turn a value
# into a miss' is a question about `miss` literals in the mutant's control
# flow — and it is the precondition of `missed(...)`, the parser file's
# dominant guardian shape." This section is that decider.
#
# WHY IT MATTERS MORE THAN A SECOND DATA POINT. `check_law` already carried
# both halves of a comparison nobody was making. Each violation row holds
# `pre` — the preconditions THIS pin's guardian's blindness rests on, read
# off the guardian's own expression by `classify_file` — and `pre_status`,
# the verdict of a decider that only ever asks about `append_only`. The two
# were never compared, so a violation on a `missed(...)` pin was bucketed
# STRICT ("`append_only` established, the law is refuted here") or EXCUSED
# ("`append_only` demonstrably BROKEN") by the answer to a question that pin
# never asked. Measured on every artefact this program has: of the 23 pins
# in round 422's `host-pins-plus.json`, 14 rest on something other than
# `append_only` — 9 on `refusal`, and 5 whose guardian is not blind at all,
# so `pre` is empty. NONE of them is currently decided and NONE of them has
# ever been a violation, so the hazard is LATENT in the recorded corpus, not
# active: no published number of this program is wrong because of it. It
# stops being latent the moment a second decider exists, which is this
# section, so the routing (`routed_precondition`) and the refusal to excuse
# across a mismatch (`check_law`'s `pre_mismatch`) land in the same round as
# the decider itself.
#
# WHAT `refusal` SAYS, on the AST. `missed(E)` is monotone along an edge that
# only ever turns a value into a miss, because nothing turns a miss back into
# a value. Three shapes carry that, and they are the three the corpus uses:
#
#   1. SUBSTITUTION.   `@{type: name, ...}`  ->  `miss ("..." + tok_at(...))`
#      The edited expression yielded a value and now yields a miss.  (CP21p)
#
#   2. GUARD INSERTED. `X`  ->  `if C { miss ("...") } else { X }`
#      One arm is the untouched old expression, the other only ever misses,
#      so every input either lands where it landed before or refuses. This
#      is the shape a `+` pin on a refusal rule almost always takes, because
#      "the rule refuses MORE" is written by adding a rejection.  (CP13p,
#      CP16p)
#
#   3. GUARD REMOVED.  the converse of 2, and the only way to get a positive
#      `broken`: a miss arm deleted so an input that refused now returns a
#      value. Nothing in this corpus does it — see the round-428 knowledge
#      file, which records that as a prediction that came back a HIT and is
#      therefore weak evidence, not a property of the language.
#
# THE HONESTY PROBLEM IS THE SAME ONE, and so are the three guards round 426
# wrote for `append_only`: the decision reads the EDIT and the guest source
# and never a verdict; it returns three values, with `broken` a positive
# finding (shape 3) and `unknown` the default; and `check_law` reports the
# partition rather than applying it. One guard is NEW here, because a second
# decider makes it possible to be wrong in a way one decider could not be:
# a decider is only ever consulted about a precondition the pin's own
# guardian rests on, and a `holds` or `broken` from any other decider is
# demoted to undecided rather than used.
#
# WHAT IT CANNOT DO, stated because the corpus is mostly this. Six of the
# nine `refusal` pins edit a BOOLEAN that a downstream `if` turns into a
# miss — `contains(acc, nm.name)` -> `len(acc) > 0`, two statements above a
# `if dup { miss ... }`. Whether that boolean fires strictly more often is
# a question about value flow, and round 426's §9 already recorded that the
# decider cannot see value flow. They come back `unknown`, which is correct
# and is not a bug to be fixed by loosening the test.

REF_SAME = "same"
REF_REFUSE = "refuse"
REF_REVIVE = "revive"
REF_UNKNOWN = "unknown"

#: How two relations on sibling nodes combine. `revive` dominates because it
#: is a positive finding; `unknown` beats `refuse` because an edit that
#: refuses in one place and does something unclassified in another has NOT
#: been shown to only ever refuse.
_REF_RANK = {REF_SAME: 0, REF_REFUSE: 1, REF_UNKNOWN: 2, REF_REVIVE: 3}


def _ref_combine(rels):
    best = REF_SAME
    for r in rels:
        if _REF_RANK[r] > _REF_RANK[best]:
            best = r
    return best


def _yields_miss(node):
    """Is this expression's value a miss on EVERY path through it?

    Syntactic and deliberately conservative: a `MissLit`, a block whose tail
    is one, or an `if`/`else` both of whose arms are. A `Rescue` (`a ? b`)
    is not, and never can be -- it is the operator that turns a miss back
    into a value, which is precisely what `refusal` forbids.
    """
    if isinstance(node, A.MissLit):
        return True
    if isinstance(node, A.ExprStmt):
        return _yields_miss(node.expr)
    if isinstance(node, A.Block):
        return bool(node.stmts) and _yields_miss(node.stmts[-1])
    if isinstance(node, A.If):
        return (node.otherwise is not None and _yields_miss(node.then)
                and _yields_miss(node.otherwise))
    return False


def _pinned_branch(a, b):
    """`if C {X} else {Y}` -> `if false {X} else {Y}`: the two VALUES.

    Returns `(before, after)` -- what the edited `if` used to produce and
    what it produces now -- or None when this is not a branch-selection
    edit. Extracted from `_walk_delta`, which had this inline since round
    426 and is now one of two callers: the same edit shape has to be read
    the same way by both preconditions.
    """
    if not (isinstance(a, A.If) and isinstance(b, A.If)):
        return None
    if not (isinstance(b.cond, A.BoolLit) and not isinstance(a.cond, A.BoolLit)
            and a.otherwise is not None
            and _node_eq(a.then, b.then)
            and _node_eq(a.otherwise, b.otherwise)):
        return None
    before, after = a.then, a.otherwise
    if b.cond.value:
        before, after = a.otherwise, a.then
    return (_block_value(before), _block_value(after))


def _guard_relation(old, new):
    """Shapes 2 and 3: an `if` arm that only ever misses, added or removed.

    Returns `REF_REFUSE`, `REF_REVIVE` or None. The surviving arm must be
    STRUCTURALLY the other side of the delta -- an `if` that misses on one
    side and returns something merely similar on the other is not a guard,
    it is a rewrite, and belongs in `unknown`.
    """
    for node, other_side, verdict in ((new, old, REF_REFUSE),
                                      (old, new, REF_REVIVE)):
        if not (isinstance(node, A.If) and node.otherwise is not None):
            continue
        for keep, gone in ((node.then, node.otherwise),
                           (node.otherwise, node.then)):
            if _yields_miss(gone) and not _yields_miss(keep) and \
                    _node_eq(_block_value(keep), _block_value(other_side)):
                return verdict
    return None


#: Literal node types whose value `_fold_cmp` is willing to read. Whence's
#: `BoolLit` is its own node and is NOT an int here, so `0 == false` never
#: folds -- guessing a cross-type comparison is the one error that turns a
#: `holds` into a lie instead of into an `unknown`.
_LIT_TYPES = (A.Num, A.Str, A.BoolLit)


def _is_lit(node):
    return isinstance(node, _LIT_TYPES)


def _fold_cmp(op, a, b):
    """`<lit> op <lit>` -> True/False, or None for "not folded".

    Same-type literals only, and ORDERING folds only for numbers: this
    module has not measured what Whence's `<` does to two strings, and a
    report is not a place to find out.
    """
    if type(a) is not type(b):
        return None
    if not isinstance(a, A.Num) and op not in ("==", "!="):
        return None
    va, vb = a.value, b.value
    return {"==": va == vb, "!=": va != vb, "<": va < vb, ">": va > vb,
            "<=": va <= vb, ">=": va >= vb}[op]


def _distribute_if(iff, op, other, other_on_left):
    """`(if C {a} else {b}) op k` -> `(C and a op k) or (not C and b op k)`.

    Returns None unless both arms unwrap to a single expression: an `else
    if` chain leaves an `A.If` in the arm and a multi-statement block leaves
    an `A.Block`, and comparing either against `k` is not a claim this
    module can make.
    """
    if iff.otherwise is None:
        return None
    a = _block_value(iff.then)
    b = _block_value(iff.otherwise)
    if isinstance(a, (A.Block, A.If)) or isinstance(b, (A.Block, A.If)):
        return None
    ln = iff.line

    def cmp(v):
        return (A.Binary(ln, op, other, v) if other_on_left
                else A.Binary(ln, op, v, other))

    return A.Binary(ln, "or",
                    A.Binary(ln, "and", iff.cond, cmp(a)),
                    A.Binary(ln, "and", A.Unary(ln, "not", iff.cond), cmp(b)))


def _simplify_bool(op, l, r, line):
    """The connective folds that are valid under Whence's THREE outcomes.

    Each rule below preserves the set of inputs on which the expression is
    TRUE, and none of them preserves miss-vs-false. That is exactly the
    right trade for `_implies`, which only ever asks "whenever p is true, is
    q true": `p and false` is a miss when `p` is a miss and `false`
    otherwise, and it is TRUE in neither case, so folding it to `false`
    cannot make a proof succeed that should have failed.

    The rule NOT written is the load-bearing one. `p or true` is NOT folded
    to `true`, because nothing in this repo has measured whether Whence's
    `or` short-circuits past a miss on the left, and `true` is true
    everywhere. One unsound fold here silently turns every downstream
    `holds` into a guess.
    """
    lb = l.value if isinstance(l, A.BoolLit) else None
    rb = r.value if isinstance(r, A.BoolLit) else None
    if op == "and":
        if lb is False or rb is False:
            return A.BoolLit(line, False)
        if lb is True:
            return r
        if rb is True:
            return l
    elif op == "or":
        if lb is False:
            return r
        if rb is False:
            return l
    return None


def _norm(node, depth=0):
    """Rewrite an expression toward a boolean skeleton, TRUTH-preserving.

    Round 428's next-steps said `_implies` "is already the relation it
    needs" for the one-hop class. It is not, and this function is the gap:
    the four laws are shape rules over `and`/`or`, and the one-hop
    substitution hands them a COMPARISON with an `if` inside it
    (`(if nm == "" {0} else {bound_line(...)}) != 0`), which matches none of
    them. Normalisation is what turns that into the `and`/`or` skeleton the
    laws can work on.

    Deliberately shallow: it descends through `not`, `and`, `or` and the
    two-sided comparisons and stops. It does NOT rewrite inside call
    arguments or `if` arms, because nothing downstream asks about them.
    """
    if depth > 8 or not isinstance(node, A.Node):
        return node
    if isinstance(node, A.Unary) and node.op == "not":
        inner = _norm(node.operand, depth + 1)
        if isinstance(inner, A.BoolLit):
            return A.BoolLit(node.line, not inner.value)
        return (node if inner is node.operand
                else A.Unary(node.line, "not", inner))
    if isinstance(node, A.Binary) and node.op in ("and", "or"):
        l = _norm(node.left, depth + 1)
        r = _norm(node.right, depth + 1)
        s = _simplify_bool(node.op, l, r, node.line)
        if s is not None:
            return _norm(s, depth + 1)
        if l is node.left and r is node.right:
            return node
        return A.Binary(node.line, node.op, l, r)
    if isinstance(node, A.Binary) and node.op in TWO_SIDED_OPS:
        l = _norm(node.left, depth + 1)
        r = _norm(node.right, depth + 1)
        if _is_lit(l) and _is_lit(r):
            v = _fold_cmp(node.op, l, r)
            if v is not None:
                return A.BoolLit(node.line, v)
        d = None
        if isinstance(l, A.If) and _is_lit(r):
            d = _distribute_if(l, node.op, r, False)
        elif isinstance(r, A.If) and _is_lit(l):
            d = _distribute_if(r, node.op, l, True)
        if d is not None:
            return _norm(d, depth + 1)
        if l is node.left and r is node.right:
            return node
        return A.Binary(node.line, node.op, l, r)
    return node


def _implies(p, q, depth=0):
    """Is `p` -> `q` provable from the shape of the two conditions alone?

    Four valid laws, applied syntactically and nothing else: identity,
    `p -> (q1 or q2)` from `p -> qi`, `(p1 and p2) -> q` from `pi -> q`,
    and the two all-branches forms. It is a PROOF procedure, not a decision
    procedure -- `False` means "not shown", never "does not hold" -- which
    is the direction that keeps a `holds` honest.

    Round 432: both operands are `_norm`-alised once, at depth 0. The
    recursion below only ever descends into sub-nodes of an already
    normalised tree, so re-running it per level would be wasted work rather
    than a second effect.
    """
    if depth > 6:
        return False
    if depth == 0:
        p, q = _norm(p), _norm(q)
    if _node_eq(p, q):
        return True
    if isinstance(q, A.Binary) and q.op == "or":
        if any(_implies(p, d, depth + 1) for d in _chain_atoms(q, "or")):
            return True
    if isinstance(p, A.Binary) and p.op == "and":
        if any(_implies(c, q, depth + 1) for c in _chain_atoms(p, "and")):
            return True
    if isinstance(p, A.Binary) and p.op == "or":
        ds = _chain_atoms(p, "or")
        if len(ds) > 1 and all(_implies(d, q, depth + 1) for d in ds):
            return True
    if isinstance(q, A.Binary) and q.op == "and":
        cs = _chain_atoms(q, "and")
        if len(cs) > 1 and all(_implies(p, c, depth + 1) for c in cs):
            return True
    return False


def _guard_cond_relation(old, new):
    """Shape 4: an EXISTING miss guard whose condition moved.

    `if C { miss ... } else { X }` -> `if C or D { miss ... } else { X }`
    sends strictly more inputs to the miss and none back to a value, so it
    is a refusal edge even though no `miss` was added and no arm changed.
    Round 428 found this by measuring: CP16p ("comparisons do not chain")
    is exactly this shape, it is the pin round 422 planted as a `missed(...)`
    guardian's own killer, and the three shapes written first all missed it
    -- the decider descended into the two conditions, found `and` against
    `or`, and returned `unknown` on a pin a human reads in one glance.

    The polarity flips when the MISS is in the `else` arm: narrowing the
    condition is then what refuses more. Both are handled; a guard whose
    two arms both miss (or neither) is not a refusal edge at all and
    returns None.
    """
    if not (isinstance(old, A.If) and isinstance(new, A.If)):
        return None
    if old.otherwise is None or new.otherwise is None:
        return None
    if not (_node_eq(old.then, new.then)
            and _node_eq(old.otherwise, new.otherwise)):
        return None
    if _node_eq(old.cond, new.cond):
        return None
    miss_then, miss_else = _yields_miss(old.then), _yields_miss(old.otherwise)
    if miss_then == miss_else:
        return None
    widened = _implies(old.cond, new.cond)
    narrowed = _implies(new.cond, old.cond)
    if widened and narrowed:
        return None                     # provably equivalent, yet not equal
    if miss_then:
        return REF_REFUSE if widened else (REF_REVIVE if narrowed else None)
    return REF_REFUSE if narrowed else (REF_REVIVE if widened else None)


def _uses_name(node, name):
    """Does `name` occur free in this subtree?

    Conservative at a binder: a `fn` that BINDS `name` as a parameter
    reports True even though the inner occurrences are a different
    variable. That answer is wrong in the safe direction -- every caller
    below uses `_uses_name` to REFUSE to apply the one-hop rule -- and
    getting shadowing right is not worth a soundness risk on a corpus that
    contains no instance of it.
    """
    if isinstance(node, A.NameRef):
        return node.name == name
    if isinstance(node, (A.FnExpr, A.FnDef)) and _binder_mentions(node, name):
        return True
    if isinstance(node, A.Node):
        return any(_uses_name(getattr(node, f), name) for f in _slots(node))
    if isinstance(node, (list, tuple)):
        return any(_uses_name(x, name) for x in node)
    return False


def _binder_mentions(fn_node, name):
    """Does this `fn`'s parameter list mention `name` (in any encoding)?"""
    for p in (fn_node.params or ()):
        if p == name:
            return True
        if isinstance(p, (list, tuple)) and name in p:
            return True
        if getattr(p, "name", None) == name:
            return True
    return False


def _rebinds_name(stmt, name):
    return (isinstance(stmt, (A.Let, A.FnDef))
            and getattr(stmt, "name", None) == name)


def _substitute(node, name, repl):
    """Replace every free `NameRef(name)` with `repl`. Never enters a `fn`."""
    if isinstance(node, A.NameRef) and node.name == name:
        return repl
    if isinstance(node, (A.FnExpr, A.FnDef)):
        return node
    if isinstance(node, A.Node):
        return type(node)(node.line, *[
            _substitute(getattr(node, f), name, repl)
            for f in type(node).__slots__])
    if isinstance(node, list):
        return [_substitute(x, name, repl) for x in node]
    if isinstance(node, tuple):
        return tuple(_substitute(x, name, repl) for x in node)
    return node


def _let_hop_relation(olds, news, whole_old, whole_new, out):
    """Shape 5 (round 432): the delta is ONE `let`, read ONE hop later.

        let dup = contains(acc, nm.name)      # <- the whole delta
        let acc2 = push(acc, nm.name)
        ...
        if dup { miss (...) } else { ... }    # <- the guard, same block

    `_refusal_leaf`'s three shapes all ask about a node that is itself a
    miss or an `if`; this edit is neither, so the pairwise descent reaches
    two `let` RHSs, finds `<Call>` against `<Binary>`, and returns
    `unknown`. Nothing was wrong with that answer -- the decider genuinely
    could not see that `dup` reaches a guard -- it was just the wrong
    question. Substituting the two RHSs into the guard condition turns a
    value-flow question into the CONDITION question shape 4 already
    decides, and hands it to the same widening test.

    Preconditions, each of which is a soundness obligation and not a
    convenience:

    * **Exactly one statement differs**, and it is a `let` with the same
      name on both sides. More than one delta is more than one hop.
    * **The tail is byte-identical**, so the guard itself did not move.
    * **The name is read by exactly ONE later statement**, which is the
      guard. A value that also flows somewhere else can change that place
      too, and this rule would not have looked.
    * **Nothing rebinds the name in between.** Whence has no rebinding at
      all -- that is what CP17p's own rule says -- so on this corpus the
      check is vacuous. It is written anyway because the rule is not about
      this corpus, and a later round that reads it should not have to
      re-derive why it is safe.
    * **The guard's arms differ in missing-ness**, and the name is read by
      the CONDITION and, at most, by an arm that only ever misses. A use
      inside a surviving arm is a second consumer whose value changed; a
      use inside the miss arm cannot revive anything, because that arm
      misses whatever the value is. CP17p needs exactly this allowance --
      its miss arm interpolates `str(first)` into the message.
    """
    if len(olds) != len(news):
        return None
    diff = [i for i in range(len(olds)) if not _node_eq(olds[i], news[i])]
    if len(diff) != 1:
        return None
    i = diff[0]
    a, b = olds[i], news[i]
    if not (isinstance(a, A.Let) and isinstance(b, A.Let) and a.name == b.name):
        return None
    name = a.name
    rest = list(olds[i + 1:])
    if not _node_eq(rest, list(news[i + 1:])):
        return None
    users = [j for j, st in enumerate(rest) if _uses_name(st, name)]
    if len(users) != 1:
        return None
    if any(_rebinds_name(st, name) for st in rest[:users[0]]):
        return None
    guard = rest[users[0]]
    if isinstance(guard, A.ExprStmt):
        guard = guard.expr
    if not (isinstance(guard, A.If) and guard.otherwise is not None):
        return None
    miss_then = _yields_miss(guard.then)
    if miss_then == _yields_miss(guard.otherwise):
        return None
    survivor = guard.otherwise if miss_then else guard.then
    if _uses_name(survivor, name) or not _uses_name(guard.cond, name):
        return None
    old_cond = _substitute(guard.cond, name, a.expr)
    new_cond = _substitute(guard.cond, name, b.expr)
    widened = _implies(old_cond, new_cond)
    narrowed = _implies(new_cond, old_cond)
    if widened and narrowed:
        return None                     # provably equivalent, yet not equal
    if miss_then:
        rel = REF_REFUSE if widened else (REF_REVIVE if narrowed else None)
    else:
        rel = REF_REFUSE if narrowed else (REF_REVIVE if widened else None)
    # An undecided hop is recorded as `unknown` over the SUBSTITUTED
    # conditions rather than left to the pairwise descent. The status is the
    # same either way; the difference is that the report then names the
    # residual proof obligation instead of printing `<Call> -> <Binary>`.
    _record(out, rel or REF_UNKNOWN, old_cond, new_cond)
    return rel or REF_UNKNOWN


def _refusal_relation(old, new, out=None):
    """Relate two nodes as `same` / `refuse` / `revive` / `unknown`.

    `out`, when given, collects `(relation, old, new)` at the point each
    non-`same` verdict is DECIDED, so the report can show the reader the
    node that carried it rather than the whole function.
    """
    if _node_eq(old, new):
        return REF_SAME
    rel = _refusal_leaf(old, new, out)
    if rel is not None:
        return rel
    if isinstance(old, A.Block) and isinstance(new, A.Block):
        return _refusal_stmts(old.stmts, new.stmts, old, new, out)
    if isinstance(old, (list, tuple)) and isinstance(new, (list, tuple)):
        return _refusal_stmts(old, new, old, new, out)
    if type(old) is type(new) and isinstance(old, A.Node):
        return _ref_combine(
            _refusal_relation(getattr(old, f), getattr(new, f), out)
            for f in _slots(old))
    _record(out, REF_UNKNOWN, old, new)
    return REF_UNKNOWN


def _refusal_leaf(old, new, out):
    """The three shapes, in the order the corpus uses them. None = descend."""
    m_old, m_new = _yields_miss(old), _yields_miss(new)
    if m_new and not m_old:
        _record(out, REF_REFUSE, old, new)
        return REF_REFUSE
    if m_old and not m_new:
        _record(out, REF_REVIVE, old, new)
        return REF_REVIVE
    g = _guard_relation(old, new)
    if g is None:
        g = _guard_cond_relation(old, new)
    if g is not None:
        _record(out, g, old, new)
        return g
    picked = _pinned_branch(old, new)
    if picked is not None:
        return _refusal_relation(picked[0], picked[1], out)
    if isinstance(old, A.Node) != isinstance(new, A.Node) or \
            (isinstance(old, A.Node) and type(old) is not type(new)):
        _record(out, REF_UNKNOWN, old, new)
        return REF_UNKNOWN
    return None


def _refusal_stmts(olds, news, whole_old, whole_new, out):
    """Relate two statement lists, including the guard-insertion shape.

    Equal lengths descend pairwise. Different lengths are the shape a `+`
    refusal pin takes when it wraps the tail of a function: a common prefix
    survives, and the REST of the old body reappears verbatim as one arm of
    a new trailing `if` whose other arm only ever misses. Round 428 measured
    that without this case CP13p -- `parse_args_rest` gaining a trailing
    comma rejection, the plainest refusal edit in the corpus -- comes back
    `unknown`, because `_walk_delta`'s list rule emits the two whole lists
    and nothing below it is comparable.
    """
    if len(olds) == len(news):
        hop = _let_hop_relation(olds, news, whole_old, whole_new, out)
        if hop is not None:
            return hop
        return _ref_combine(_refusal_relation(a, b, out)
                            for a, b in zip(olds, news))
    k = 0
    while k < len(olds) and k < len(news) and _node_eq(olds[k], news[k]):
        k += 1
    for short, long_, verdict in ((olds, news, REF_REFUSE),
                                  (news, olds, REF_REVIVE)):
        if len(long_) - k != 1:
            continue
        tail = long_[k]
        if isinstance(tail, A.ExprStmt):
            tail = tail.expr
        if not (isinstance(tail, A.If) and tail.otherwise is not None):
            continue
        rest = list(short[k:])
        for keep, gone in ((tail.then, tail.otherwise),
                           (tail.otherwise, tail.then)):
            if _yields_miss(gone) and not _yields_miss(keep) and \
                    isinstance(keep, A.Block) and \
                    _node_eq(list(keep.stmts), rest):
                _record(out, verdict, whole_old, whole_new)
                return verdict
    _record(out, REF_UNKNOWN, whole_old, whole_new)
    return REF_UNKNOWN


def _record(out, rel, old, new):
    """Note where a non-`same` verdict was DECIDED, for the report."""
    if out is not None:
        out.append((rel, old, new))


def refusal_precondition(base_src, pin, kinds=()):
    """Does this pin's edit respect `refusal`? Reads no verdict.

    Same return contract as `edit_precondition`: `status` in {holds, broken,
    unknown, identity, unlocatable, unparsable}, plus `kinds`, `deltas` and
    `decided_over`. `holds` is the only value that is a claim about the
    edit; `broken` is the positive finding that a miss became a value.
    """
    try:
        mutant = CP.apply_edit(base_src, pin)
    except Exception as exc:                                  # noqa: BLE001
        return {"status": "unlocatable", "why": str(exc), "kinds": [],
                "deltas": [], "decided_over": (PRE_REFUSAL,)}
    try:
        old = _parse_cached(base_src)
        new = _parse_cached(mutant)
    except Exception as exc:                                  # noqa: BLE001
        return {"status": "unparsable", "why": str(exc), "kinds": [],
                "deltas": [], "decided_over": (PRE_REFUSAL,)}
    seen = []
    rel = _refusal_relation(old, new, seen)
    status = {REF_SAME: "identity", REF_REFUSE: PRE_HOLDS,
              REF_REVIVE: PRE_BROKEN, REF_UNKNOWN: PRE_UNKNOWN}[rel]
    kinds = [r for r, _, _ in seen]
    shown = ["%s: %s  ->  %s" % (r, _brief(a), _brief(b)) for r, a, b in seen]
    return {"status": status, "why": None, "kinds": kinds, "deltas": shown,
            "decided_over": (PRE_REFUSAL,)}


# --- the THIRD precondition: does this pin's edit change the KIND? --------
#
# Round 434 (language C). Round 428 closed with "`kind_stable` has no decider
# and is the last one … EP10m in round 416's campaign is the pin waiting for
# it", and rounds 429-433 carried that item unchanged. This section is the
# decider, and it is the one that had a RESULT waiting on it: EP10m is the
# only violation in this program's entire recorded corpus that reads
# `undecided`, so until now the sentence "the law is CONDITIONAL and nothing
# strictly refutes it" rested on a pin nothing had decided.
#
# WHAT `kind_stable` SAYS. `is_guess(E)` -- and, by the `is_` naming
# convention, a guest `is_num(E)`/`is_list(E)`/... -- is a test on the KIND of
# the value it observes, not on how permissive the rule that produced it is.
# It is monotone along a "the rule does less" edge exactly while the edit
# cannot move E out of (or into) the kind being tested. So the question this
# decider asks is not "is the value the same" and not even "is the kind the
# same": it is
#
#     does the edit change whether the value at the edit site is a K,
#     for the specific K the pin's own guardian tests?
#
# ROUTED ONE LEVEL DEEPER THAN ROUND 428'S ROUTING. Round 428 made a decider
# answer only about the precondition the pin's guardian rests on. This one
# additionally needs to know WHICH KIND that guardian probes, so `Verdict`
# grew `kinds` and `routed_precondition` passes it through. A decider that
# asked "did the kind change at all" instead would be answering a strictly
# harder question than the law needs, and would come back `unknown` on
# EP10m: the base kind there is `{bool, guess}` (a comparison whose operand
# is a Guess is a Guess, but the analysis cannot rule out the bool) and the
# mutant kind is `{bool, miss}`. Those two sets are NOT disjoint. They differ
# on `guess`, which is the only kind the guardian looks at.
#
# THE LANGUAGE FACT THAT MAKES IT WORK, and the naive rule that would have
# inverted the answer. In most languages `x == y` is a bool and a kind
# analysis writes that rule without thinking. In Whence it is not:
# `_guess_binop` re-wraps a comparison whose operand is a Guess in a NEW
# Guess at weakest-link confidence (interp.py, v0.15), which is the entire
# mechanism EP10m pins. Under the naive rule `a.v == b.v` is `{bool}`,
# `guest_eq(a, b)` is `{bool, miss}`, `guess` is in neither, the membership
# does not change, and the decider returns `holds` -- which would move EP10m
# from `undecided` to STRICT, i.e. would report this program's conditional
# law as REFUTED, on a rule nobody would have questioned.
# `test_the_naive_comparison_kind_rule_would_invert_ep10m` is what stops that
# rule from being reintroduced.
#
# WHAT IT ABSTRACTS AWAY, stated because a `holds` is a claim. Whence turns a
# type error into an ordinary miss on almost any operation, so a sound
# may-analysis would put `miss` in nearly every kind set and nothing would
# ever be disjoint. This analysis models `miss` only where it is
# SYNTACTICALLY produced -- a `miss` literal, an arm reached under
# `missed(x)`, a callee whose own body produces one. That is safe for the
# decision rule above and only for it: the tested kind K comes from a type
# test in the guardian, `missed` is an atom of the OTHER precondition
# (`refusal`) and never appears as a K, so an unmodelled implicit miss can
# neither add nor remove K from a kind set. It would matter the day someone
# adds `is_miss` to the atom table; `test_miss_is_not_a_testable_kind` says
# so out loud.
#
# WHAT IT IS LOCAL ABOUT. Like `edit_precondition` and `refusal_precondition`
# it reads the EDIT and the guest source and never a verdict, and its claim
# is about the value AT THE EDIT SITE, not about the guardian's observed
# value -- which for EP10m is the result of interpreting a Whence program
# inside a Whence interpreter written in Whence, three call layers and one
# `gv(...)` string away. The two existing deciders make exactly the same
# local claim (`append_only` decides "every replaced string expression is
# rewritten at its end", not "the observed text only grew"), so this is the
# established strength of a `holds` on this axis rather than a new weakness.

#: `interp._kind`'s vocabulary, verbatim. Kept as a literal rather than
#: imported because importing the interpreter to run a static analysis over
#: the parser's output would make a 40 ms module take seconds; the two are
#: pinned together by `test_the_kind_vocabulary_matches_the_interpreter`.
KINDS = ("num", "str", "bool", "list", "record", "fn", "guess", "miss",
         "value")
KIND_TOP = frozenset(KINDS)
KIND_BOTTOM = frozenset()

#: `is_<k>` names a kind test when `<k>` is a kind. The guest spells three of
#: them differently and this is the whole exception list; it is corpus-
#: derived, like `IS_PREFIX` itself, so `classify` reports how many `is_*`
#: names in the file it resolved and how many it did not.
GUEST_KIND_ALIASES = {
    "guess_val": "guess",     # self_eval.lang:1382
    "callable": "fn",         # self_eval.lang:1417
    "closure": "fn",          # self_eval.lang:1415
    "builtin_ref": "fn",      # self_eval.lang:1416
}


def kind_tested_by(name):
    """The kind `name` tests, or None. `is_guess` -> guess, `is_op` -> None."""
    if not name.startswith(IS_PREFIX):
        return None
    rest = name[len(IS_PREFIX):]
    rest = GUEST_KIND_ALIASES.get(rest, rest)
    return rest if rest in KINDS else None


def guardian_kinds(expr, guest_fns):
    """Every kind the type tests in a guardian expression probe.

    Deliberately a SEPARATE walk from `_analyse` rather than a fifth value
    threaded through it: `_analyse` is the monotonicity algebra and 131
    tests pin its four-tuple. This collects a fact the algebra does not
    need and the new decider does.
    """
    out = []
    stack = [expr]
    while stack:
        node = stack.pop()
        if not isinstance(node, A.Node):
            continue
        nm = _callee_name(node)
        if nm is not None and (nm in MONOTONE_BUILTINS or nm in guest_fns):
            k = kind_tested_by(nm)
            if k is not None:
                out.append(k)
        for f in _slots(node):
            v = getattr(node, f)
            if isinstance(v, A.Node):
                stack.append(v)
            elif isinstance(v, (list, tuple)):
                stack.extend(x for x in v if isinstance(x, A.Node))
    return tuple(sorted(set(out)))


#: Builtin -> the kinds its result can have. Only the builtins this corpus's
#: guest files actually use in a position this analysis descends into; every
#: other call is TOP, which is `unknown` and costs a decision rather than
#: risking a wrong one. `sure` is TOP on purpose: it hands back whatever was
#: inside the Guess.
BUILTIN_KINDS = {
    "len": frozenset(("num",)),
    "str": frozenset(("str",)),
    "keys": frozenset(("list",)),
    "contains": frozenset(("bool",)),
    "has": frozenset(("bool",)),
    "missed": frozenset(("bool",)),
    "matches": frozenset(("bool",)),
    "is_guess": frozenset(("bool",)),
    "guess": frozenset(("guess",)),
    "confidence": frozenset(("num", "miss")),
    "split": frozenset(("list",)),
    "join": frozenset(("str",)),
    "upper": frozenset(("str",)),
    "lower": frozenset(("str",)),
    "abs": frozenset(("num",)),
    "num": frozenset(("num", "miss")),
    "shapeof": frozenset(("str",)),
    "reasons": frozenset(("list",)),
    "keys_of": frozenset(("list",)),
}

#: `+` is the one overloaded arithmetic operator; the rest are numeric.
_NUMERIC_OPS = ("-", "*", "/", "%")
_CONCAT_KINDS = frozenset(("num", "str", "list"))

#: How many times the interprocedural least fixpoint may re-derive one
#: function before giving up and answering TOP. The lattice is finite
#: (2**9 kind sets) so a monotone iteration terminates; the cap is a
#: runaway guard, not the termination argument.
_KIND_FIX_ROUNDS = 16

#: TWO caps, deliberately not one. `_KIND_DEPTH` bounds the descent through
#: one expression TREE; `_KIND_CALL_DEPTH` bounds the chain of guest calls.
#: Round 434 wrote them as a single counter and measured the consequence: a
#: function body is analysed starting from whatever depth its first caller
#: happened to sit at, so `raw_deep_eq` -- an eleven-arm `else if` chain --
#: blew a 40-deep cap and answered TOP when it was reached from inside
#: `apply_binop`'s tree, and `{bool, miss}` when it was asked for directly.
#: That made the DECISION for EP10p depend on which pin ran first in the
#: same process. A call frame resets the tree budget, which is the only
#: reading under which a function means the same thing wherever it is called.
_KIND_DEPTH = 160
_KIND_CALL_DEPTH = 24


def _path_key(node):
    """`a`, `a.v`, `a.v.w` -> a stable string key; anything else -> None."""
    if isinstance(node, A.NameRef):
        return node.name
    if isinstance(node, A.FieldAccess):
        base = _path_key(node.obj)
        return None if base is None else base + "." + node.name
    return None


def _may_guess(ks):
    return "guess" in ks


def _contagion(ks, operands):
    """Whence propagates a Guess operand through arithmetic, comparison and
    `not` (interp.py v0.15: "the only two places a v0.15 value can flow
    through without being resolved are the operators themselves")."""
    if any(_may_guess(o) for o in operands):
        return ks | frozenset(("guess",))
    return ks


class _KindCtx(object):
    """Per-program interprocedural state for `_kinds_of`.

    `done` holds converged answers; `approx` holds the current
    under-approximation of a function still inside its own fixpoint. A
    result computed while any in-progress function was consulted is NOT
    promoted to `done`, because it rests on an approximation that may still
    grow -- the standard hazard when an SCC is entered at more than one
    node, and the reason `guest_eq` (which reaches the mutually recursive
    `raw_deep_eq` / `raw_deep_eq_list` / `raw_deep_eq_fields` triangle)
    needs it.
    """

    __slots__ = ("fns", "done", "approx", "stack", "used_in_progress")

    def __init__(self, prog):
        self.fns = {}
        for st in prog.stmts:
            if isinstance(st, A.FnDef):
                self.fns[st.name] = (st.params, st.body)
            elif isinstance(st, A.Let) and isinstance(st.expr, A.FnExpr):
                self.fns[st.name] = (st.expr.params, st.expr.body)
        self.done = {}
        self.approx = {}
        self.stack = []
        self.used_in_progress = set()

    def fn_kinds(self, name, depth=0):
        if name in self.done:
            return self.done[name]
        if name not in self.fns:
            return KIND_TOP
        if name in self.stack:
            self.used_in_progress.add(name)
            return self.approx.get(name, KIND_BOTTOM)
        if len(self.stack) >= _KIND_CALL_DEPTH:
            return KIND_TOP
        params, body = self.fns[name]
        cur = self.approx.get(name, KIND_BOTTOM)
        outer_used = self.used_in_progress
        used = set()
        settled = False
        for _ in range(_KIND_FIX_ROUNDS):
            self.approx[name] = cur
            self.stack.append(name)
            self.used_in_progress = set()
            try:
                env = dict((p, KIND_TOP) for p in params)
                got = _kinds_of(body, env, self, 0) | cur
            finally:
                self.stack.pop()
                used = self.used_in_progress
                self.used_in_progress = outer_used
            if got == cur:
                settled = True
                break
            cur = got
        outer = used - set([name])
        if outer:
            # This SCC was entered at an inner node while an ancestor was
            # still iterating, so `cur` rests on the ancestor's current
            # approximation. Publish it as an APPROXIMATION and let the
            # ancestor's own loop re-derive it: caching it as final is the
            # order-dependence bug round 434 measured, where `guest_eq` came
            # out `{bool, miss}` on one call order and TOP on another, which
            # is the difference between deciding EP10p and not.
            self.approx[name] = cur
            self.used_in_progress |= outer
            return cur
        if not settled:
            cur = KIND_TOP          # did not settle: answer TOP, not a guess
        self.approx[name] = cur
        self.done[name] = cur
        return cur


def _kinds_of(node, env, ctx, depth=0):
    """The set of kinds `node`'s value can have. `KIND_TOP` = not known.

    A may-analysis over a finite lattice: every rule either names a set or
    answers TOP, and TOP is absorbing, so no rule here can make a kind set
    SMALLER than the truth except through the one documented abstraction
    (implicit type-error misses).
    """
    if depth > _KIND_DEPTH or not isinstance(node, A.Node):
        return KIND_TOP
    if isinstance(node, A.Num):
        return frozenset(("num",))
    if isinstance(node, A.Str):
        return frozenset(("str",))
    if isinstance(node, A.BoolLit):
        return frozenset(("bool",))
    if isinstance(node, A.ListLit):
        return frozenset(("list",))
    if isinstance(node, A.RecordLit):
        return frozenset(("record",))
    if isinstance(node, A.MissLit):
        return frozenset(("miss",))
    if isinstance(node, A.FnExpr):
        return frozenset(("fn",))
    if isinstance(node, (A.NameRef, A.FieldAccess)):
        key = _path_key(node)
        if key is not None and key in env:
            return env[key]
        if isinstance(node, A.NameRef) and node.name in ctx.fns:
            return frozenset(("fn",))
        return KIND_TOP
    if isinstance(node, A.Unary):
        inner = _kinds_of(node.operand, env, ctx, depth + 1)
        base = frozenset(("bool",)) if node.op == "not" \
            else frozenset(("num",))
        return _contagion(base, (inner,))
    if isinstance(node, A.Binary):
        return _binary_kinds(node, env, ctx, depth)
    if isinstance(node, A.Rescue):
        left = _kinds_of(node.left, env, ctx, depth + 1)
        right = _kinds_of(node.right, env, ctx, depth + 1)
        return (left - frozenset(("miss",))) | right
    if isinstance(node, A.If):
        return _if_kinds(node, env, ctx, depth)
    if isinstance(node, A.Block):
        return _block_kinds(node, env, ctx, depth)
    if isinstance(node, A.ExprStmt):
        return _kinds_of(node.expr, env, ctx, depth + 1)
    if isinstance(node, A.Call):
        name = _callee_name(node)
        if name is None:
            return KIND_TOP
        hit = BUILTIN_KINDS.get(name)
        if hit is not None and name not in ctx.fns:
            return hit
        return ctx.fn_kinds(name)
    return KIND_TOP


def _binary_kinds(node, env, ctx, depth):
    left = _kinds_of(node.left, env, ctx, depth + 1)
    right = _kinds_of(node.right, env, ctx, depth + 1)
    if node.op in ("and", "or"):
        # `and`/`or` require a definite bool in Whence (`_logic_left`), so a
        # Guess does NOT flow through them -- the one place contagion stops.
        return frozenset(("bool",))
    if node.op in TWO_SIDED_OPS:
        return _contagion(frozenset(("bool",)), (left, right))
    if node.op == "+":
        common = (left & right) & _CONCAT_KINDS
        base = common if common else _CONCAT_KINDS
        return _contagion(base, (left, right))
    if node.op in _NUMERIC_OPS:
        return _contagion(frozenset(("num",)), (left, right))
    return KIND_TOP


def _block_kinds(node, env, ctx, depth):
    """A block's value is its tail's, evaluated under its own `let`s."""
    if not node.stmts:
        return KIND_TOP
    local = dict(env)
    for st in node.stmts[:-1]:
        if isinstance(st, A.Let):
            local[st.name] = _kinds_of(st.expr, local, ctx, depth + 1)
    tail = node.stmts[-1]
    if isinstance(tail, A.Let):
        return KIND_TOP
    return _kinds_of(tail, local, ctx, depth + 1)


def _if_kinds(node, env, ctx, depth):
    then_envs = refine(node.cond, True, env, ctx)
    ks = KIND_BOTTOM
    for e in then_envs:
        ks |= _kinds_of(node.then, e, ctx, depth + 1)
    if node.otherwise is None:
        return KIND_TOP         # a one-armed `if` yields a miss-or-value
    for e in refine(node.cond, False, env, ctx):
        ks |= _kinds_of(node.otherwise, e, ctx, depth + 1)
    return ks


def refine(cond, truth, env, ctx):
    """Environments in which `cond` has truth value `truth`.

    Returns a LIST because a disjunction taken as true, and a conjunction
    taken as false, are case splits rather than single refinements: EP10m's
    guard is `is_guess_val(a.v) or is_guess_val(b.v)`, and the honest
    reading of it is "either a.v is a guess, or b.v is" -- two worlds, whose
    kind sets the caller joins. Collapsing them to one env by intersecting
    would claim BOTH operands are guesses, which the guard does not say.
    """
    if isinstance(cond, A.Unary) and cond.op == "not":
        return refine(cond.operand, not truth, env, ctx)
    if isinstance(cond, A.Binary) and cond.op in ("and", "or"):
        conj = (cond.op == "and") == bool(truth)
        if conj:
            out = env
            for part in _chain_atoms(cond, cond.op):
                envs = refine(part, truth, out, ctx)
                out = envs[0] if len(envs) == 1 else out
            return [out]
        out = []
        for part in _chain_atoms(cond, cond.op):
            out.extend(refine(part, truth, env, ctx))
        return out or [env]
    name = _callee_name(cond)
    if name is not None and len(getattr(cond, "args", ())) == 1:
        key = _path_key(cond.args[0])
        if key is None:
            return [env]
        k = kind_tested_by(name)
        if k is None and name == "missed":
            k = "miss"
        if k is None:
            return [env]
        known = env.get(key, KIND_TOP)
        got = frozenset((k,)) if truth else (known - frozenset((k,)))
        if truth:
            got = known & got if known != KIND_TOP else got
        out = dict(env)
        out[key] = got or KIND_BOTTOM
        return [out]
    return [env]


# --- relating two ASTs by the tested kind ---------------------------------

KIND_SAME = "same"
KIND_STABLE = "stable"
KIND_UNKNOWN = "unknown"
KIND_CHANGED = "changed"

#: `changed` dominates for the same reason `revive` does in `refusal`: it is
#: the POSITIVE finding, and one delta that provably moves the value out of
#: the tested kind breaks the precondition however stable the others are.
_KIND_RANK = {KIND_SAME: 0, KIND_STABLE: 1, KIND_UNKNOWN: 2, KIND_CHANGED: 3}


def _kind_combine(rels):
    best = KIND_SAME
    for r in rels:
        if _KIND_RANK[r] > _KIND_RANK[best]:
            best = r
    return best


def _delta_kind_relation(old, new, env_old, env_new, ctx_old, ctx_new,
                         tested, out, ks_old=None, ks_new=None):
    if ks_old is None:
        ks_old = _kinds_of(old, env_old, ctx_old)
    if ks_new is None:
        ks_new = _kinds_of(new, env_new, ctx_new)
    if ks_old == KIND_TOP or ks_new == KIND_TOP or not ks_old or not ks_new:
        rel = KIND_UNKNOWN
    elif any((k in ks_old) != (k in ks_new) for k in tested):
        rel = KIND_CHANGED
    else:
        rel = KIND_STABLE
    if out is not None:
        out.append((rel, old, new, ks_old, ks_new))
    return rel


def _kind_relation(old, new, env_old, env_new, ctx_old, ctx_new, tested,
                   out, depth=0):
    """Walk two ASTs together, carrying the kind facts each side is under.

    The shape is `_walk_delta`'s -- the same chain rule, the same
    branch-selection case -- but it cannot BE `_walk_delta`, because the
    environments are what make EP10m decidable and a pair-collecting walk
    throws them away. The two agree on which pairs are the deltas;
    `test_the_kind_walk_finds_the_same_deltas_as_walk_delta` says so.
    """
    if depth > _KIND_DEPTH:
        return KIND_UNKNOWN
    if _node_eq(old, new) and env_old == env_new:
        return KIND_SAME
    if isinstance(old, A.If) and isinstance(new, A.If):
        picked = _pinned_branch(old, new)
        if picked is not None:
            # The arm that USED to run was reached under the old condition;
            # the arm that runs NOW is unguarded, because the mutant's
            # condition is the constant that selected it.
            keep_true = isinstance(new.cond, A.BoolLit) and new.cond.value
            # The case split a disjunctive guard opens is JOINED here rather
            # than decided per world: "either a.v is a guess or b.v is" is
            # one fact about one value, and reporting it twice would put the
            # same delta in the report twice and let one world's `changed`
            # outrank the other world's `stable`.
            ks_before = KIND_BOTTOM
            for eb in refine(old.cond, not keep_true, env_old, ctx_old):
                ks_before |= _kinds_of(picked[0], eb, ctx_old)
            return _delta_kind_relation(
                picked[0], picked[1], env_old, env_new, ctx_old, ctx_new,
                tested, out, ks_old=ks_before)
    if type(old) is not type(new):
        return _delta_kind_relation(old, new, env_old, env_new, ctx_old,
                                    ctx_new, tested, out)
    if isinstance(old, (A.FnDef, A.FnExpr)):
        if list(old.params) != list(new.params):
            return _delta_kind_relation(old, new, env_old, env_new, ctx_old,
                                        ctx_new, tested, out)
        fresh = dict((p, KIND_TOP) for p in old.params)
        return _kind_relation(old.body, new.body, fresh, fresh, ctx_old,
                              ctx_new, tested, out, depth + 1)
    if isinstance(old, A.Block):
        return _kind_stmts(old.stmts, new.stmts, old, new, env_old, env_new,
                           ctx_old, ctx_new, tested, out, depth)
    if isinstance(old, A.If):
        if _node_eq(old.cond, new.cond):
            rel = _kind_relation(old.cond, new.cond, env_old, env_new,
                                 ctx_old, ctx_new, tested, out, depth + 1)
            for truth, a, b in ((True, old.then, new.then),
                                (False, old.otherwise, new.otherwise)):
                if a is None or b is None:
                    continue
                eo = refine(old.cond, truth, env_old, ctx_old)[0]
                en = refine(new.cond, truth, env_new, ctx_new)[0]
                rel = _kind_combine((rel, _kind_relation(
                    a, b, eo, en, ctx_old, ctx_new, tested, out, depth + 1)))
            return rel
        return _delta_kind_relation(old, new, env_old, env_new, ctx_old,
                                    ctx_new, tested, out)
    if isinstance(old, (list, tuple)):
        if len(old) != len(new):
            return _delta_kind_relation(old, new, env_old, env_new, ctx_old,
                                        ctx_new, tested, out)
        return _kind_combine(
            _kind_relation(a, b, env_old, env_new, ctx_old, ctx_new, tested,
                           out, depth + 1)
            for a, b in zip(old, new))
    if isinstance(old, A.Node):
        op = _chain_op(old)
        if op is not None and op == _chain_op(new):
            if len(_chain_atoms(old, op)) != len(_chain_atoms(new, op)):
                return _delta_kind_relation(old, new, env_old, env_new,
                                            ctx_old, ctx_new, tested, out)
        rels = []
        for f in _slots(old):
            x, y = getattr(old, f), getattr(new, f)
            if isinstance(x, (A.Node, list, tuple)) or \
               isinstance(y, (A.Node, list, tuple)):
                rels.append(_kind_relation(x, y, env_old, env_new, ctx_old,
                                           ctx_new, tested, out, depth + 1))
            elif x != y:
                return _delta_kind_relation(old, new, env_old, env_new,
                                            ctx_old, ctx_new, tested, out)
        return _kind_combine(rels) if rels else KIND_SAME
    if old != new:
        return _delta_kind_relation(old, new, env_old, env_new, ctx_old,
                                    ctx_new, tested, out)
    return KIND_SAME


def _kind_stmts(olds, news, whole_old, whole_new, env_old, env_new, ctx_old,
                ctx_new, tested, out, depth):
    """Statement lists, threading each side's `let` bindings as it goes."""
    if len(olds) != len(news):
        return _delta_kind_relation(whole_old, whole_new, env_old, env_new,
                                    ctx_old, ctx_new, tested, out)
    eo, en = dict(env_old), dict(env_new)
    rels = []
    for a, b in zip(olds, news):
        rels.append(_kind_relation(a, b, eo, en, ctx_old, ctx_new, tested,
                                   out, depth + 1))
        if isinstance(a, A.Let):
            eo[a.name] = _kinds_of(a.expr, eo, ctx_old)
        if isinstance(b, A.Let):
            en[b.name] = _kinds_of(b.expr, en, ctx_new)
    return _kind_combine(rels) if rels else KIND_SAME


def kind_precondition(base_src, pin, kinds=()):
    """Does this pin's edit respect `kind_stable`? Reads no verdict.

    Same return contract as the other two deciders. `kinds` is the guardian's
    own tested-kind tuple (`Verdict.kinds`); WITHOUT it there is no question
    to ask and the answer is `unknown` rather than a guess -- an `is_*`
    guardian this module cannot name a kind for is exactly the case round
    426's third guard was written for.
    """
    tested = tuple(k for k in kinds if k in KINDS)
    if not tested:
        return {"status": PRE_UNKNOWN,
                "why": "the guardian's type test names no kind this analysis "
                       "resolves", "kinds": [], "deltas": [],
                "decided_over": (PRE_KIND_STABLE,)}
    try:
        mutant = CP.apply_edit(base_src, pin)
    except Exception as exc:                                  # noqa: BLE001
        return {"status": "unlocatable", "why": str(exc), "kinds": [],
                "deltas": [], "decided_over": (PRE_KIND_STABLE,)}
    try:
        old = _parse_cached(base_src)
        new = _parse_cached(mutant)
    except Exception as exc:                                  # noqa: BLE001
        return {"status": "unparsable", "why": str(exc), "kinds": [],
                "deltas": [], "decided_over": (PRE_KIND_STABLE,)}
    seen = []
    rel = _kind_relation(old, new, {}, {}, _kind_ctx(old), _kind_ctx(new),
                         tested, seen)
    status = {KIND_SAME: "identity", KIND_STABLE: PRE_HOLDS,
              KIND_CHANGED: PRE_BROKEN, KIND_UNKNOWN: PRE_UNKNOWN}[rel]
    shown = ["%s (%s): %s {%s}  ->  %s {%s}"
             % (r, "/".join(tested), _brief(a), ",".join(sorted(ka)),
                _brief(b), ",".join(sorted(kb)))
             for r, a, b, ka, kb in seen]
    return {"status": status, "why": None,
            "kinds": [r for r, _, _, _, _ in seen], "deltas": shown,
            "decided_over": (PRE_KIND_STABLE,)}


_KIND_CTX_CACHE = {}


def _kind_ctx(prog):
    """One `_KindCtx` per parsed Program, so the interprocedural fixpoint is
    paid once per source rather than once per pin."""
    ctx = _KIND_CTX_CACHE.get(id(prog))
    if ctx is None or ctx[0] is not prog:
        ctx = (prog, _KindCtx(prog))
        _KIND_CTX_CACHE[id(prog)] = ctx
    return ctx[1]


# --- routing: decide the precondition THIS pin's guardian rests on --------

#: precondition name -> the decider that decides it from the edit alone.
#: Complete as of round 434: every precondition an atom in
#: `MONOTONE_BUILTINS` names is here, and
#: `test_every_precondition_in_the_atom_table_has_a_decider` is what keeps
#: it complete when a fourth atom arrives. The `no_decider` branch below is
#: NOT dead code waiting to be deleted -- it is the behaviour a fourth
#: precondition gets on the day it is named and before it is decided, and it
#: yields `no_decider`, which combines as undecided and therefore excuses
#: nothing. That is the same reading round 426 gave to an absent
#: precondition map, for the same reason: it is the only one that leaves the
#: law falsifiable.
PRECONDITION_DECIDERS = {
    PRE_APPEND_ONLY: edit_precondition,
    PRE_REFUSAL: refusal_precondition,
    PRE_KIND_STABLE: kind_precondition,
}

#: The guardian is not blind in any direction, so no precondition is in play
#: and there is nothing to decide. Distinct from `unknown`, which means a
#: decider ran and could not tell.
PRE_INAPPLICABLE = "inapplicable"
#: The pin's precondition is named but nothing can decide it (`kind_stable`).
PRE_NO_DECIDER = "no_decider"


def routed_precondition(base_src, pin, pres, kinds=()):
    """Decide every precondition in `pres` for this pin, and combine.

    `pres` is the guardian verdict's own `pre` tuple. The combination is
    conjunctive because the blindness rests on all of them at once: any
    `broken` breaks it, and it `holds` only when every named precondition
    does. An undecidable member drags the whole row to `unknown`, never to
    `broken` -- excusing a violation on a precondition nothing decided is
    exactly the unfalsifiability round 426 wrote its three guards against.
    """
    pres = tuple(pres)
    if not pres:
        return {"status": PRE_INAPPLICABLE, "why": "guardian is not blind in "
                "any direction, so no precondition is in play", "kinds": [],
                "deltas": [], "decided_over": (), "per_precondition": {}}
    rows = {}
    for name in pres:
        decider = PRECONDITION_DECIDERS.get(name)
        if decider is None:
            rows[name] = {"status": PRE_NO_DECIDER,
                          "why": "no decider for `%s`" % name,
                          "kinds": [], "deltas": [], "decided_over": (name,)}
        else:
            rows[name] = decider(base_src, pin, kinds)
    stats = [rows[n]["status"] for n in pres]
    for hard in ("unlocatable", "unparsable"):
        if hard in stats:
            status = hard
            break
    else:
        if all(s == "identity" for s in stats):
            status = "identity"
        elif PRE_BROKEN in stats:
            status = PRE_BROKEN
        elif all(s in (PRE_HOLDS, "identity") for s in stats):
            status = PRE_HOLDS
        else:
            status = PRE_UNKNOWN
    why = "; ".join("%s: %s" % (n, rows[n]["status"]) for n in pres)
    return {"status": status, "why": why,
            "kinds": [k for n in pres for k in rows[n]["kinds"]],
            "deltas": ["[%s] %s" % (n, d) for n in pres
                       for d in rows[n]["deltas"]] or
                      ["[%s] %s" % (n, rows[n].get("why") or rows[n]["status"])
                       for n in pres],
            "decided_over": pres, "per_precondition": rows}


def precondition_map(pins, base_src, verdicts=None):
    """`{pin id: <precondition row>}` for every pin in a registry.

    WITHOUT `verdicts` every pin is decided against `append_only`, which is
    what round 426 built and what every caller predating round 428 wants.
    That is not a safe default once a second decider exists -- 14 of round
    422's 23 pins rest on something else -- so the row carries
    `decided_over` and `check_law` refuses to excuse or strictly-refute
    across a mismatch. Passing `verdicts` (the `classify_file` output for
    the guest file these pins were measured against) routes each pin to the
    precondition its OWN guardian's blindness rests on, which is the
    version a caller with a guest file in hand should use.
    """
    if verdicts is None:
        return {p["id"]: edit_precondition(base_src, p) for p in pins}
    by_label = {v.label: v for v in verdicts}
    out = {}
    for p in pins:
        v = by_label.get(p.get("guardian"))
        if v is None:
            out[p["id"]] = {"status": PRE_INAPPLICABLE,
                            "why": "guardian names no check in this file",
                            "kinds": [], "deltas": [], "decided_over": (),
                            "per_precondition": {}}
        else:
            out[p["id"]] = routed_precondition(base_src, p, v.pre,
                                                v.kinds)
    return out


def _cmd_precondition(args):
    if not args:
        print("usage: polarity.py precondition <pins.json> [run.json]",
              file=sys.stderr)
        return 2
    with open(args[0], encoding="utf-8") as f:
        reg = json.load(f)
    guest_files = sorted({p["guest_file"] for p in reg["pins"]})
    if len(guest_files) != 1:
        print("precondition: registry spans %d guest files; run one at a time"
              % len(guest_files), file=sys.stderr)
        return 2
    with open(os.path.join(_HERE, guest_files[0]), encoding="utf-8") as f:
        base = f.read()
    vs = classify_file(os.path.join(_HERE, guest_files[0]))
    pre = precondition_map(reg["pins"], base, vs)
    unrouted = precondition_map(reg["pins"], base)
    verdicts = None
    if len(args) > 1:
        with open(args[1], encoding="utf-8") as f:
            verdicts = {r["id"]: r["verdict"] for r in json.load(f)["results"]}
    counts = {}
    for row in pre.values():
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("precondition, decided from the EDIT alone, ROUTED to the one each "
          "pin's own")
    print("guardian rests on (round 428) — %s" % guest_files[0])
    missing = sorted(set((PRE_REFUSAL, PRE_APPEND_ONLY, PRE_KIND_STABLE))
                     - set(PRECONDITION_DECIDERS))
    print("  deciders: " + ", ".join(sorted(PRECONDITION_DECIDERS)) +
          ("; no decider for: " + ", ".join(missing) if missing else
           "; every precondition in the atom table is decided (round 434)"))
    wrong = 0
    for pin in reg["pins"]:
        row = pre[pin["id"]]
        seen = "" if verdicts is None else "  measured %s" % verdicts.get(
            pin["id"], "?")
        over = ",".join(row.get("decided_over") or ()) or "-"
        print("  %-7s %-13s over %-24s%s"
              % (pin["id"], row["status"], over, seen))
        for d in row["deltas"]:
            print("        %s" % d)
        if row.get("why"):
            print("        %s" % row["why"])
        old = unrouted[pin["id"]]["status"]
        if PRE_APPEND_ONLY not in (row.get("decided_over") or ()) and \
                old in (PRE_HOLDS, PRE_BROKEN):
            wrong += 1
            print("        !! the unrouted decider called this `%s` on "
                  "`append_only`, which this pin does not rest on" % old)
    print("  " + ", ".join("%s %d" % (k, counts[k]) for k in sorted(counts)))
    print("  %d pin(s) whose UNROUTED answer was a decision to a question "
          "the pin never asked" % wrong)
    if os.environ.get("POLARITY_JSON"):
        with open(os.environ["POLARITY_JSON"], "w", encoding="utf-8") as f:
            json.dump(pre, f, indent=2)
        print("wrote %s" % os.environ["POLARITY_JSON"])
    return 0


# --- CLI ------------------------------------------------------------------

def _cmd_classify(args):
    verbose = "--verbose" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print("usage: polarity.py classify <file.lang>...", file=sys.stderr)
        return 2
    for path in paths:
        vs = classify_file(path)
        s = summarise(vs)
        print("=" * 72)
        print("%s: %d check(s)" % (path, s["n"]))
        print("  one-sided        %3d  (%.1f%%)   +blind %d, -blind %d, "
              "both %d" % (s["one_sided"], s["one_sided_pct"],
                           s["blind_plus"], s["blind_minus"], s["blind_both"]))
        print("  two-sided/unknown%3d              of which unknown shape %d "
              "(%.1f%%)" % (s["two_sided_or_unknown"], s["unknown"],
                            s["unknown_pct"]))
        print("  kind tests       %3d  of which %d rest on `kind_stable`; "
              "%d name no kind" % (s["kind_tested"], s["rests_on_kind_stable"],
                                   s["kind_unresolved"]))
        if verbose:
            for v in vs:
                print("  %-5s %-4s %-58s %s"
                      % (v.line, "".join(sorted(v.blind)) or ".",
                         v.label[:58], v.reason[:40]))
    return 0


def _cmd_law(args):
    if len(args) < 2:
        print("usage: polarity.py law <pins.json> <run.json>", file=sys.stderr)
        return 2
    with open(args[0], encoding="utf-8") as f:
        reg = json.load(f)
    with open(args[1], encoding="utf-8") as f:
        run = json.load(f)
    guest_files = sorted({p["guest_file"] for p in reg["pins"]})
    if len(guest_files) != 1:
        print("law: registry spans %d guest files; run one at a time"
              % len(guest_files), file=sys.stderr)
        return 2
    vs = classify_file(os.path.join(_HERE, guest_files[0]))
    with open(os.path.join(_HERE, guest_files[0]), encoding="utf-8") as f:
        pre = precondition_map(reg["pins"], f.read(), vs)
    out = check_law(reg["pins"], run["results"], vs, pre)
    print("law: BLIND(guardian, dir) => NOT guarded")
    print("  scored %d pin(s) against %s" % (out["n_scored"], guest_files[0]))
    print("  %d confirmation(s) — blind, and indeed not guarded:"
          % len(out["confirmations"]))
    for r in out["confirmations"]:
        print("    %-7s dir %s  %-11s %-46s [%s]"
              % (r["id"], r["dir"], r["verdict"], r["guardian"][:46],
                 r["shape"][:34]))
    print("  %d sighted pin(s) — not blind in that direction:"
          % len(out["sighted"]))
    for r in out["sighted"]:
        print("    %-7s dir %s  %-11s %-46s [%s]"
              % (r["id"], r["dir"], r["verdict"], r["guardian"][:46],
                 r["shape"][:34]))
    if out["unmatched"]:
        print("  %d guardian label(s) with no check of that name (registry "
              "rot):" % len(out["unmatched"]))
        for pid, lab in out["unmatched"]:
            print("    %-7s %s" % (pid, lab))
    print("  %d VIOLATION(s) — guarded although blind. The law is "
          "CONDITIONAL on the" % len(out["violations"]))
    print("  precondition named beside each; a violation is an edit that "
          "left the order,")
    print("  not a check that saw through its own blindness:")
    for r in out["violations"]:
        print("    *** %-7s dir %s  guarded but %s-blind  [%s]  precondition "
              "%s: %s"
              % (r["id"], r["dir"], r["dir"], r["shape"][:34],
                 r.get("pre_status") or "undecided",
                 ",".join(r["pre"]) or "-"))
        if r.get("pre_mismatch"):
            print("          DEMOTED to undecided: that verdict was decided "
                  "over %s, which is not what this pin rests on"
                  % (",".join(r.get("pre_decided_over") or ()) or "nothing"))
        for d in (pre.get(r["id"]) or {}).get("deltas") or ():
            print("          %s" % d)
    print("  of those, %d STRICT (the pin's OWN precondition established for "
          "the edit, so the law is refuted here), %d excused (that "
          "precondition demonstrably BROKEN by the edit, so the law makes no "
          "claim) and %d undecided (nothing decided it, or it was decided "
          "over a precondition this pin does not rest on)"
          % (len(out["strict_violations"]), len(out["excused"]),
             len(out["undecided"])))
    if os.environ.get("POLARITY_JSON"):
        with open(os.environ["POLARITY_JSON"], "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print("wrote %s" % os.environ["POLARITY_JSON"])
    # Exit 0: the violations are the RESULT, not a failure of the tool. A
    # non-zero here would make `law` unrunnable from a green-suite script and
    # would assert the unconditional law this round measured to be false.
    return 0


def main(argv):
    verbs = {"classify": _cmd_classify, "law": _cmd_law,
             "audit": _cmd_audit, "repoint": _cmd_repoint,
             "precondition": _cmd_precondition}
    if len(argv) < 2 or argv[1] not in verbs:
        print("usage: polarity.py {classify|law|audit|repoint|precondition} "
              "...", file=sys.stderr)
        return 2
    return verbs[argv[1]](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
