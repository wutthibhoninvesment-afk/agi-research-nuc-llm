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

    __slots__ = ("label", "line", "blind", "unknown", "reason", "pre")

    def __init__(self, label, line, blind, unknown, reason, pre=()):
        self.label = label
        self.line = line
        self.blind = frozenset(blind)
        self.unknown = bool(unknown)
        self.reason = reason
        #: the preconditions every blind direction above rests on. Empty
        #: when `blind` is empty. A caller that reports blindness WITHOUT
        #: reporting these is making the claim round 420 disproved.
        self.pre = tuple(sorted(set(pre)))

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
        out.append(Verdict(st.label, st.line, blind, unknown, reason, pre))
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
    return {
        "n": n,
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
    (the edit is not string-shaped, so appending is neither established nor
    refuted). All three are returned and all three are printed; the
    partition is reported, never applied silently. WITHOUT the map every
    violation is strict -- an absent precondition decision does not excuse
    anything, which is the only reading that leaves the law falsifiable.
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
        row["pre_status"] = ((pre_status or {}).get(row["id"]) or {}).get(
            "status")
    if pre_status is None:
        excused, undecided, strict = [], [], list(violations)
    else:
        excused = [r for r in violations if r["pre_status"] == PRE_BROKEN]
        strict = [r for r in violations if r["pre_status"] == PRE_HOLDS]
        undecided = [r for r in violations
                     if r["pre_status"] not in (PRE_BROKEN, PRE_HOLDS)]
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
                    "file — regenerate, do not hand-edit." % len(picked))
        new["pins"] = [p for p in new["pins"] if p["id"] in picked]
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
        if (isinstance(b.cond, A.BoolLit) and not isinstance(a.cond, A.BoolLit)
                and a.otherwise is not None
                and _node_eq(a.then, b.then)
                and _node_eq(a.otherwise, b.otherwise)):
            before, after = a.then, a.otherwise
            if b.cond.value:
                before, after = a.otherwise, a.then
            out.append((_block_value(before), _block_value(after)))
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


def _brief(node, limit=44):
    if isinstance(node, A.Str):
        s = repr(node.value)
    elif _is_concat(node):
        s = " + ".join(_brief(x, 18) for x in _concat_atoms(node))
    elif isinstance(node, A.NameRef):
        s = node.name
    elif isinstance(node, A.Num):
        s = repr(node.value)
    elif isinstance(node, A.Call):
        s = "%s(...)" % (_brief(node.fn, 18)
                         if not isinstance(node.fn, A.NameRef)
                         else node.fn.name)
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


def edit_precondition(base_src, pin):
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
                "kinds": [], "deltas": []}
    try:
        old = _parse_cached(base_src)
        new = _parse_cached(mutant)
    except Exception as exc:                                  # noqa: BLE001
        return {"status": "unparsable", "why": str(exc),
                "kinds": [], "deltas": []}
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
    return {"status": status, "why": None, "kinds": kinds, "deltas": shown}


def precondition_map(pins, base_src):
    """`{pin id: edit_precondition(...)}` for every pin in a registry."""
    return {p["id"]: edit_precondition(base_src, p) for p in pins}


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
    pre = precondition_map(reg["pins"], base)
    verdicts = None
    if len(args) > 1:
        with open(args[1], encoding="utf-8") as f:
            verdicts = {r["id"]: r["verdict"] for r in json.load(f)["results"]}
    counts = {}
    for row in pre.values():
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("precondition `append_only`, decided from the EDIT alone — %s"
          % guest_files[0])
    for pin in reg["pins"]:
        row = pre[pin["id"]]
        seen = "" if verdicts is None else "  measured %s" % verdicts.get(
            pin["id"], "?")
        print("  %-7s %-11s%s" % (pin["id"], row["status"], seen))
        for d in row["deltas"]:
            print("        %s" % d)
        if row.get("why"):
            print("        %s" % row["why"])
    print("  " + ", ".join("%s %d" % (k, counts[k]) for k in sorted(counts)))
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
        pre = precondition_map(reg["pins"], f.read())
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
        for d in (pre.get(r["id"]) or {}).get("deltas") or ():
            print("          %s" % d)
    print("  of those, %d STRICT (`append_only` established for the edit, so "
          "the law is refuted here), %d excused (`append_only` demonstrably "
          "BROKEN by the edit, so the law makes no claim) and %d undecided "
          "(the edit is not string-shaped; appending is neither established "
          "nor refuted)"
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
