#!/usr/bin/env python3
"""What fraction of a WRONG ARGUMENT ORDER does the v0.22 hint actually catch?

Round 480 (language C), closing round 476's next-step 3 (carried by rounds
477 and 478):

    "The order-hint coverage ratio is NEW and un-swept. `fold` gets 4 of 5
    wrong permutations; the fifth is caught elsewhere, also precisely.
    Nobody has taken that ratio for the other builtins `_order_hint` serves
    -- `put`, `typed`, `guess`, `map`, `filter`, `find`, `push`, `at`,
    `steps`. Cheap, and the kind of number that turns out to be worse
    somewhere."

It turned out to be worse somewhere. This module is the measurement, landed
as an ARTEFACT rather than run once as a script, so the next round to ask
re-derives the number instead of quoting round 480's -- the rule
`depthcensus.py` was built under (round 452) and the same rule round 434's
next-step 10 states for carried claims.

THE METRIC, DEFINED BEFORE IT WAS TAKEN
---------------------------------------
`state/whence/round-480/PREDICTIONS.md` §1 fixes this text; it is repeated
here because an instrument whose metric lives only in a bank is a metric
nobody re-reads.

A **witness** for builtin `f` of declared arity `n >= 2` is a tuple of `n`
Whence source expressions (plus an optional preamble) such that the call
`f(w0, ..., w[n-1])`, in the order `_BUILTIN_SIGS` declares, does NOT miss.
For each of the `n! - 1` non-identity permutations the permuted program is
run through all three host evaluation modes and classified:

    HINTED         the result is a Miss whose reason carries the v0.22
                   clause ` (arguments fit NAME(...))`
    BARE           the result is a Miss and it does not
    ACCEPTED_DIFF  the result is NOT a miss and renders differently from
                   the correct call -- a wrong argument order that returned
                   a wrong answer silently
    ACCEPTED_SAME  the result is not a miss and renders identically: the
                   permutation is inert FOR THIS WITNESS

Orthogonally each permutation carries `kind_blind`, true when
`_sig_fits(sig, permuted_payloads)` holds. `_order_hint`'s second declared
silence is `if _sig_fits(sig, payloads): return ""`, so on a `kind_blind`
permutation the hint is structurally incapable of firing -- no miss site,
however placed, can produce one. `kind_blind` is therefore the CEILING:

    coverage = HINTED / (n! - 1)          <=      1 - kind_blind_fraction

WHY THE RATIO IS NOT A PROPERTY OF THE BUILTIN
----------------------------------------------
It is a property of the (builtin, witness) PAIR, and the difference is
large enough to change the headline. `note(label:str, v)` called with a
NUMBER in `v` has a kind-distinguishable transposition (`note(5, "hi")` is
one of `tests/test_v22.py`'s own HINT_CASES); called with a STRING in `v`
the transposition fits the declared kinds exactly, the hint cannot fire,
`b_note` cannot tell, and the program gets a differently-labelled value
with no diagnostic at all. Same builtin, same arity, opposite verdict.

So every number this module publishes is keyed by witness id, and
`census()` reports the per-witness rows as well as the pool. A caller that
wants "the coverage of `note`" is asking a question with no answer.

WHAT IS DELIBERATELY NOT MEASURED
---------------------------------
  * Arity errors. A builtin called with the wrong NUMBER of arguments is
    already a precise, different miss (`_call_gen`'s `_arity_ok` gate), and
    `_order_hint`'s first declared silence excludes them on purpose.
  * Builtins of arity < 2 (16 of the 37 in `_BUILTIN_SIGS`): there is no
    other order. `_order_hint`'s `len(args) < 2` silence.
  * `rand`, arity 0, for the same reason.
  * Whether the reordered call would SUCCEED. The hint promises only that
    the kinds line up that way, and this instrument promises no more --
    `ACCEPTED_*` is measured on the permuted call, never on the repaired one.
"""

import json
import sys
from itertools import permutations

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))

from whence import interp as _I          # noqa: E402
from whence.interp import Interpreter    # noqa: E402
from whence.values import Miss, full_show  # noqa: E402

HINT_MARK = " (arguments fit "

# The three host evaluation modes `tests/test_v20.py::host_modes` uses, for
# the reason it uses them: `fast=False` forces the trampoline (`_call_gen`),
# `direct=False` disables `_call_direct`, and the default reaches
# `_compile_builtin_call`. A hint present in one mode and absent in another
# is a defect this census must not average away, so `run_call` asserts the
# three agree and records the disagreement instead of a verdict when they
# do not.
MODES = ({"fast": False}, {"direct": False}, {})


# --- witnesses ---------------------------------------------------------------
#
# One entry per (builtin, witness). `args` is in the DECLARED order; the
# census permutes it. Every witness is asserted non-missing by
# `tests/test_v46.py::test_every_witness_is_a_working_call`, which is what
# keeps this table from silently degenerating into a table of broken calls
# whose permutations all miss for the wrong reason.
#
# `note`, `at`, `contains`, `join`, `get` and `has` carry a SECOND witness
# differing only in a payload's kind. Those pairs are the evidence for the
# module docstring's claim that the ratio is not a property of the builtin.

WITNESSES = [
    # (builtin, witness id, preamble, [arg exprs in declared order])
    ("at",       "str-pat",   "let v = note(\"tag\", 1)\n", ["v", "\"tag\""]),
    ("at",       "both-str",  "let s = note(\"tag\", \"hi\")\n",
     ["s", "\"tag\""]),
    ("contains", "list-num",  "", ["[1, 2, 3]", "2"]),
    ("contains", "both-str",  "", ["\"abcd\"", "\"bc\""]),
    ("contrast", "num-num",   "", ["1", "2"]),
    ("diverge",  "num-num",   "", ["1", "2"]),
    ("filter",   "fn-list",   "", ["fn(x) { x > 1 }", "[1, 2, 3]"]),
    ("find",     "fn-list",   "", ["fn(x) { x > 1 }", "[1, 2, 3]"]),
    ("fold",     "fn-num-list", "", ["fn(a, x) { a + x }", "0", "[1, 2, 3]"]),
    ("get",      "rec-str",   "", ["@{a: 1}", "\"a\""]),
    ("guess",    "any-num-str", "", ["1", "0.5", "\"src\""]),
    ("has",      "rec-str",   "", ["@{a: 1}", "\"a\""]),
    ("join",     "list-str",  "", ["[\"a\", \"b\"]", "\", \""]),
    ("map",      "fn-list",   "", ["fn(x) { x + 1 }", "[1, 2, 3]"]),
    ("matches",  "num-tag",   "", ["1", "\"num\""]),
    ("merge",    "rec-rec",   "", ["@{a: 1}", "@{b: 2}"]),
    ("note",     "str-num",   "", ["\"tag\"", "5"]),
    ("note",     "both-str",  "", ["\"tag\"", "\"five\""]),
    ("push",     "list-num",  "", ["[1, 2]", "7"]),
    ("put",      "rec-str-num", "", ["@{a: 1}", "\"b\"", "9"]),
    ("range",    "num-num",   "", ["1", "4"]),
    ("steps",    "val-str",   "let v = note(\"tag\", 1)\n", ["v", "\"tag\""]),
    ("sure",     "guess-num", "", ["guess(1, 0.9, \"s\")", "0.5"]),
    ("typed",    "any-tag-str", "", ["1", "\"num\"", "\"lbl\""]),
]


def multi_arg_builtins():
    """Every `_BUILTIN_SIGS` name of declared arity >= 2 -- the population.

    Read off the live table rather than listed here, so a builtin added
    with a 2+ parameter `sig=` joins the population by existing and
    `tests/test_v46.py::test_the_witness_table_covers_the_population`
    goes red until somebody writes it a witness."""
    _I._make_builtin_table()
    return sorted(n for n, s in _I._BUILTIN_SIGS.items() if len(s) >= 2)


def hint_sites():
    """Builtin names that appear as `_order_hint("NAME", ...)` in the
    interpreter source -- the set of names any hint can be raised FOR,
    before this round's hoist. Derived from the source text on purpose: it
    is a claim about where the calls are, and the file is the only honest
    source for that."""
    import os
    import re
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "whence", "interp.py")).read()
    return sorted(set(re.findall(r'_order_hint\("([a-z_]+)"', src)))


# --- running one permuted call ----------------------------------------------

def _program(preamble, name, args):
    return "%slet result = %s(%s)\n" % (preamble, name, ", ".join(args))


def _payloads(preamble, args):
    """The runtime payloads of the witness's argument expressions, in the
    order given. Bound one per `let` and read back out of the finished Env,
    so `kind_blind` is computed against the SAME payload objects
    `_order_hint` would see rather than against a guess at their kinds."""
    lets = "".join("let __a%d = %s\n" % (i, a) for i, a in enumerate(args))
    env = Interpreter().run(preamble + lets)
    return [env.get("__a%d" % i).payload for i in range(len(args))]


def run_call(preamble, name, args):
    """Run one call in all three host modes; return (payload, reason, text).

    `reason` is the first miss reason with no line number, or None for a
    non-miss; `text` is `full_show` of the payload. Raises if the modes
    disagree -- see MODES."""
    src = _program(preamble, name, args)
    seen = []
    for kw in MODES:
        v = Interpreter(**kw).run(src).get("result")
        p = v.payload
        if isinstance(p, Miss):
            seen.append(("miss", _strip_line(p.reasons[0])))
        else:
            seen.append(("value", full_show(p)))
    if len(set(seen)) != 1:
        raise AssertionError("host modes disagree for %s: %r" % (src, seen))
    kind, text = seen[0]
    return kind, text


def _strip_line(text):
    """Drop the trailing ` (line N)` a miss reason carries, the way
    `tests/test_v20.py::reason` does. Written out rather than imported
    because `tests/` is not on the import path of a module in the package
    root, and a tenth copy of a normaliser is what round 404 deleted --
    this is the FIRST copy outside `tests/`, and it is anchored."""
    import re
    return re.sub(r" \(line \d+\)$", "", text)


# --- the census --------------------------------------------------------------

def classify(preamble, name, args, correct_text):
    kind, text = run_call(preamble, name, args)
    if kind == "miss":
        return ("HINTED" if HINT_MARK in text else "BARE"), text
    return ("ACCEPTED_SAME" if text == correct_text
            else "ACCEPTED_DIFF"), text


def census(witnesses=None):
    """The full report. Pure data -- `main` renders it, tests assert on it."""
    _I._make_builtin_table()
    witnesses = WITNESSES if witnesses is None else witnesses
    sites = set(hint_sites())
    rows = []
    for name, wid, preamble, args in witnesses:
        sig = _I._BUILTIN_SIGS[name]
        payloads = _payloads(preamble, args)
        base_kind, base_text = run_call(preamble, name, args)
        if base_kind != "value":
            raise AssertionError(
                "witness %s/%s is not a working call: %s" % (name, wid,
                                                             base_text))
        perms = []
        idxs = list(range(len(args)))
        for order in permutations(idxs):
            if list(order) == idxs:
                continue
            permuted = [args[i] for i in order]
            cls, text = classify(preamble, name, permuted, base_text)
            perms.append({
                "order": list(order),
                "call": "%s(%s)" % (name, ", ".join(permuted)),
                "class": cls,
                "kind_blind": _I._sig_fits(sig, [payloads[i] for i in order]),
                "result": text,
            })
        n_hint = sum(1 for p in perms if p["class"] == "HINTED")
        n_blind = sum(1 for p in perms if p["kind_blind"])
        rows.append({
            "builtin": name,
            "witness": wid,
            "arity": len(args),
            "has_hint_site": name in sites,
            "n_perms": len(perms),
            "hinted": n_hint,
            "bare": sum(1 for p in perms if p["class"] == "BARE"),
            "accepted_diff": sum(1 for p in perms
                                 if p["class"] == "ACCEPTED_DIFF"),
            "accepted_same": sum(1 for p in perms
                                 if p["class"] == "ACCEPTED_SAME"),
            "kind_blind": n_blind,
            "coverage": n_hint / len(perms),
            "ceiling": (len(perms) - n_blind) / len(perms),
            "perms": perms,
        })
    pop = multi_arg_builtins()
    covered = sorted({r["builtin"] for r in rows})
    tot = sum(r["n_perms"] for r in rows)
    hit = sum(r["hinted"] for r in rows)
    blind = sum(r["kind_blind"] for r in rows)
    return {
        "population": pop,
        "population_size": len(pop),
        "witnessed": covered,
        "uncovered_builtins": [n for n in pop if n not in covered],
        "hint_sites": sorted(sites),
        "builtins_with_no_hint_site": [n for n in pop if n not in sites],
        "rows": rows,
        "totals": {
            "n_perms": tot,
            "hinted": hit,
            "bare": sum(r["bare"] for r in rows),
            "accepted_diff": sum(r["accepted_diff"] for r in rows),
            "accepted_same": sum(r["accepted_same"] for r in rows),
            "kind_blind": blind,
            "coverage": hit / tot,
            "ceiling": (tot - blind) / tot,
            "reachable_gap": (tot - blind - hit),
        },
    }


# --- second population: an argument that is ALREADY a miss --------------------
#
# Round 480. `_order_hint` declares three silences and this is the fourth it
# needed. A `Miss` payload's `_kind()` tag is `"miss"`, which no `sig`
# declares, so a miss NEVER fits a kinded slot and ALWAYS fits an `any` one.
# A builtin that raises its own kind-miss instead of propagating its
# argument's therefore manufactures a fitting permutation for free, and the
# reader is advised to reorder arguments when the fault is three lines
# upstream. `note(bad, "hi")` is the instance that was found by hand:
#
#     note label must be a string, got miss (arguments fit note(label, v))
#
# This census asks the question of every (builtin, position) pair rather
# than of the ten calls somebody thought to type.

MISS_EXPR = 'get(@{}, "z")'
MISS_PREAMBLE = 'let bad = %s\n' % MISS_EXPR


def miss_arg_census(witnesses=None):
    """For each witness, substitute a propagated miss into each argument
    position IN THE DECLARED ORDER and classify the result.

    `propagated` means the reason is the argument's own miss reason,
    verbatim -- the builtin did not raise one of its own. `false_hint` is
    the defect: the builtin raised its own miss AND the v0.22 clause rode
    along, advising a reorder that cannot repair an upstream failure."""
    _I._make_builtin_table()
    witnesses = WITNESSES if witnesses is None else witnesses
    inner = _strip_line(run_call("", "get", ["@{}", '"z"'])[1])
    rows = []
    for name, wid, preamble, args in witnesses:
        for pos in range(len(args)):
            sub = list(args)
            sub[pos] = "bad"
            kind, text = run_call(preamble + MISS_PREAMBLE, name, sub)
            if kind == "value":
                cls = "NO_MISS"
            elif text == inner:
                cls = "PROPAGATED"
            elif HINT_MARK in text:
                cls = "FALSE_HINT"
            else:
                cls = "OWN_MISS"
            rows.append({"builtin": name, "witness": wid, "position": pos,
                         "param": _I._BUILTIN_SIGS[name][pos][0],
                         "class": cls, "result": text})
    pairs = {(r["builtin"], r["position"]) for r in rows}
    return {
        "inner_miss_reason": inner,
        "n_rows": len(rows),
        "n_pairs": len(pairs),
        "rows": rows,
        "totals": {c: sum(1 for r in rows if r["class"] == c)
                   for c in ("PROPAGATED", "OWN_MISS", "FALSE_HINT",
                             "NO_MISS")},
        "false_hints": [r for r in rows if r["class"] == "FALSE_HINT"],
    }


def main(argv):
    rep = census()
    if "--json" in argv:
        print(json.dumps(rep, indent=1, sort_keys=True))
        return 0
    t = rep["totals"]
    print("population %d builtins (arity>=2); %d witnesses; %d permutations"
          % (rep["population_size"], len(rep["rows"]), t["n_perms"]))
    if rep["uncovered_builtins"]:
        print("UNWITNESSED: %s" % ", ".join(rep["uncovered_builtins"]))
    print("no _order_hint call site: %s"
          % ", ".join(rep["builtins_with_no_hint_site"]))
    print()
    print("%-9s %-12s %5s %6s %5s %5s %5s %6s %6s"
          % ("builtin", "witness", "perms", "hinted", "bare", "diff",
             "same", "blind", "cover"))
    for r in rep["rows"]:
        print("%-9s %-12s %5d %6d %5d %5d %5d %6d %6.2f"
              % (r["builtin"], r["witness"], r["n_perms"], r["hinted"],
                 r["bare"], r["accepted_diff"], r["accepted_same"],
                 r["kind_blind"], r["coverage"]))
    print()
    print("POOLED  hinted %d/%d = %.3f   ceiling %.3f   reachable gap %d"
          % (t["hinted"], t["n_perms"], t["coverage"], t["ceiling"],
             t["reachable_gap"]))
    print("        silently wrong answers (ACCEPTED_DIFF): %d"
          % t["accepted_diff"])

    m = miss_arg_census()
    print()
    print("miss-argument census: %d rows over %d (builtin, position) pairs"
          % (m["n_rows"], m["n_pairs"]))
    print("  %s" % m["totals"])
    for r in m["false_hints"]:
        print("  FALSE HINT  %s pos %d (%s): %s"
              % (r["builtin"], r["position"], r["param"], r["result"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
