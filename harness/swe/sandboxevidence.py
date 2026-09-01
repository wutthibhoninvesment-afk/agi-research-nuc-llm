"""What the mutation SANDBOX did not run — from the sandbox's own report.

    from swe.sandboxevidence import check, verdict, format_block

WHY THIS EXISTS
---------------
`mutation.baseline_check` is the gate every mutation campaign passes through:
it runs the suite once against an unmutated `_copy_project` copy and grades
the result on ONE INTEGER, the exit code. Round 425 pointed
`swe.copyparity run` at the real tree and found the hole in that grade:

    REGRESSED  tests.test_v37::test_the_host_is_byte_unchanged_by_this_decision
               passed -> skipped
               "not a git checkout, or 768954b is not present"

    in_place  rc=0        copied  rc=0

`_copy_project` excludes `.git`; the test shells out to `git show` and round
404 gave it a defensive `pytest.skip` guard. In the sandbox that guard turns
a real assertion into a no-op, both sides exit zero, and the gate is green.
A test that stops being evidence is invisible to every exit-code check in
this repo.

THE COST ARGUMENT, WHICH IS THE WHOLE DESIGN
--------------------------------------------
`harness/pristine_check.py` (round 427) answers the same question for the
GIT tree by running the suite TWICE and differencing per-node outcomes. That
is the right shape when you have two trees and no history. It is the wrong
shape here, because the sandbox baseline is a run this repo is ALREADY
paying for: adding `--junitxml` to it and comparing the skip list against a
signed registry costs **zero extra suite runs**. The second tree is only
needed to ESTABLISH the registry (that is what `copyparity run` is for), not
to re-check it every campaign.

So this module is deliberately ONE-SIDED. It cannot, by itself, tell a skip
the copy caused from a skip that happens everywhere — and it does not try
to. It asks a question a one-sided run can actually answer:

    is every test the sandbox did not run signed off by a round that
    looked at it?

which is a STRONGER statement than "nothing changed", because it also covers
the skips that were already there when the differential was taken.

THREE HOLES, NOT ONE
--------------------
An exit-code gate is blind to three different losses, and they need three
different checks:

  1. `passed -> skipped`    — the round-425 class. Caught by the skip list.
  2. skipped in BOTH trees  — never a copy defect, still evidence the score
                              was computed without. Caught by the same list;
                              this is why the registry signs every skip and
                              not only the evaporations.
  3. silently FEWER NODES   — a conftest that stops collecting a file when
                              something it reads is absent. Exit code 0, no
                              skip, no failure, fewer tests. Nothing in this
                              repo could see this before; `node_floor`
                              catches it with one integer.

WHAT AN ACKNOWLEDGEMENT MEANS HERE, AND WHY IT CARRIES `kills_mutants`
----------------------------------------------------------------------
`pristine_check`'s registry has two states: signed or not. That is right for
its subject (is this repo's evidence complete in a fresh clone?). This
subject has a sharper question available, because the consumer of the
baseline is a MUTATION SCORE: a skipped test that never executes a line of
the files being mutated cannot kill any mutant of them, so its evaporation
costs the campaign exactly nothing. One that does execute them costs
`killed` counts nobody can recover.

`kills_mutants` records which, with the evidence that decided it. An
acknowledgement with `kills_mutants: true` is printed LOUDLY on every run
(`acknowledged_costly`) and never goes quiet: it is a standing debt against
every score the engine publishes, not a silenced warning.

DIRECTION, SINCE THE RECORD HAS IT BACKWARDS
--------------------------------------------
Round 425 wrote that an evaporated test leaves "the mutation score inflated
by exactly the amount nobody can see". It is the other way round.
`MutationReport.score` is `killed / total`; a test that evaporates moves the
mutants it would have killed from `killed` to `survived`, so the score goes
DOWN and the survivor list grows. The harm is real and is NOT round 349's
flattering inversion: it is phantom test gaps, and every phantom is then
paid for again by `killers.py` and `repair.py` hunting a killer that already
exists in the tree. See `knowledge/round-431-*.md`.

REGISTRY
--------
`state/known-sandbox-skips.json`:

    {"suites":       {"<suite>": {"node_floor": 2093, ...}},
     "acknowledged": [{"suite": ..., "key": "<classname>::<name>",
                       "nid": ..., "class": "sandbox_only"|"both"|"unknown",
                       "reason_pin": "<exact skip message>",
                       "kills_mutants": true|false|null,
                       "acknowledged_round": 431, "why": "..."}]}

The key is junit's `(classname, name)` pair and never a file:line — see
`pristine_check`'s decision 1; `pytest -rs` keys by line and reports a
phantom every time somebody adds an import. A missing or corrupt registry
reads as EMPTY, i.e. acknowledges nothing, so deleting the file cannot
silence the check.
"""

import json
import os
import sys

from .proc import AGI_RESEARCH_ROOT

# One junit parser for this repo, not three. `pristine_check` owns the
# `(classname, name)` key, the `pytest.xfail` exclusion and the node-id
# reconstruction heuristic; re-deriving any of them here is how the two
# copies drift into disagreeing about the same XML.
# `harness/` has no `__init__.py` (implicit namespace package), so the REPO
# ROOT is what has to be importable -- `harness/` alone is already on
# `sys.path` for `swe.*` and that is not the same entry.
if AGI_RESEARCH_ROOT not in sys.path:
    sys.path.insert(0, AGI_RESEARCH_ROOT)

from harness.pristine_check import (junit_node_id, parse_junit,   # noqa: E402
                                    skip_key)

REGISTRY = os.path.join(AGI_RESEARCH_ROOT, "state", "known-sandbox-skips.json")

#: Ack states. `costly` is not a failure state -- it is an acknowledgement
#: that was signed with `kills_mutants: true`, i.e. a known, adjudicated,
#: still-unpaid cost against every score the engine produces.
ACK_HOLDS = "holds"
ACK_PIN_EXPIRED = "pin_expired"
ACK_DEAD = "dead"
ACK_COSTLY = "costly"

#: Verdicts, in precedence order. `node_loss` outranks `skip_evaporation`
#: because a suite that collected fewer tests has lost evidence it cannot
#: even name, and the skip list of such a run is not trustworthy either.
V_NODE_LOSS = "node_loss"
V_SKIP_EVAPORATION = "skip_evaporation"
V_UNAVAILABLE = "unavailable"
V_OK = "ok"


def load_registry(path=None):
    """`(suites, acknowledged)`. Never raises.

    Missing or corrupt reads as `({}, [])` -- acknowledges nothing and pins
    no floor. That is the fail-loud direction: the worst a broken registry
    can do is make a known skip go red again. The opposite default would let
    `rm` silence the checker.
    """
    try:
        with open(path or REGISTRY, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}, []
    if not isinstance(data, dict):
        return {}, []
    suites = data.get("suites")
    if not isinstance(suites, dict):
        suites = {}
    acks = [e for e in (data.get("acknowledged") or [])
            if isinstance(e, dict) and e.get("suite") and e.get("key")]
    return suites, acks


def check(junit, suite=None, registry_path=None, suites=None, acks=None):
    """Grade one sandbox run's own junit report.

    `junit` is a `pristine_check.parse_junit` record (or anything with the
    same `ok`/`statuses`/`skips` shape). `suite` names the (tree, test
    command) pair the registry is keyed by; `None` matches every entry, which
    is what a caller with no suite name gets and is deliberately the
    PERMISSIVE direction for matching but not for the verdict -- an
    unacknowledged skip is still unacknowledged.

    Rule 3 (round 355, applied here): if the report is unavailable the answer
    is `evidence: "unavailable"`, NO bucket is populated and NO verdict is
    produced. A run that left no report has not shown that nothing was lost.
    """
    out = {"suite": suite, "evidence": "unavailable", "error": None,
           "n_nodes": None, "n_skipped": None, "node_floor": None,
           "unacknowledged": [], "acknowledged": [], "acknowledged_costly": [],
           "pin_expired": [], "dead_acknowledgements": [], "verdict": V_UNAVAILABLE}
    junit = junit or {}
    if not junit.get("ok"):
        out["error"] = junit.get("error") or "no junit report"
        return out
    if suites is None or acks is None:
        r_suites, r_acks = load_registry(registry_path)
        suites = r_suites if suites is None else suites
        acks = r_acks if acks is None else acks
    out["evidence"] = "available"
    statuses = junit.get("statuses") or {}
    skips = junit.get("skips") or []
    out["n_nodes"] = len(statuses)
    out["n_skipped"] = len(skips)
    by_key = {}
    for e in acks:
        if suite is None or e.get("suite") == suite:
            by_key[e.get("key")] = e
    matched = set()
    for sk in skips:
        row = {"key": sk["key"], "nid": sk.get("nid") or sk["key"],
               "reason": sk.get("reason", "")}
        ack = by_key.get(sk["key"])
        if ack is None:
            row["ack"] = None
            out["unacknowledged"].append(row)
            continue
        matched.add(sk["key"])
        # The registry's `why` is a paragraph and is deliberately NOT copied
        # into the row: this block is written into `baseline.json` on every
        # campaign, and the paragraph is already in git at a known path keyed
        # by `key`. Round 427 learned that one the expensive way (11 KB of an
        # 18 KB block, every run).
        row["ack"] = {k: ack.get(k) for k in
                      ("acknowledged_round", "acknowledged_utc", "class",
                       "kills_mutants")}
        if ack.get("reason_pin") != sk.get("reason", ""):
            row["ack_state"] = ACK_PIN_EXPIRED
            row["ack"]["reason_pin"] = ack.get("reason_pin")
            out["pin_expired"].append(row)
        elif ack.get("kills_mutants") is True:
            row["ack_state"] = ACK_COSTLY
            out["acknowledged_costly"].append(row)
            out["acknowledged"].append(row)
        else:
            row["ack_state"] = ACK_HOLDS
            out["acknowledged"].append(row)
    for key, ack in sorted(by_key.items()):
        if key not in matched:
            out["dead_acknowledgements"].append(
                {"key": key, "nid": ack.get("nid") or key,
                 "state": ACK_DEAD, "why": ack.get("why")})
    floor = (suites.get(suite) or {}).get("node_floor") if suite else None
    if isinstance(floor, int):
        out["node_floor"] = floor
    out["verdict"] = verdict(out)
    return out


def verdict(block):
    """The block's verdict, by the precedence the constants document."""
    if block.get("evidence") != "available":
        return V_UNAVAILABLE
    floor, n = block.get("node_floor"), block.get("n_nodes")
    if isinstance(floor, int) and isinstance(n, int) and n < floor:
        return V_NODE_LOSS
    if block.get("unacknowledged") or block.get("pin_expired"):
        return V_SKIP_EVAPORATION
    return V_OK


def is_lost(block):
    """True when this run's evidence is incomplete in a way nobody signed."""
    return verdict(block) in (V_NODE_LOSS, V_SKIP_EVAPORATION)


def format_block(block, indent="  "):
    """Human lines. Acknowledged rows are printed EVERY time on purpose: an
    acknowledgement that suppresses invisibly reads as coverage."""
    v = block.get("verdict") or verdict(block)
    if block.get("evidence") != "available":
        return ["%ssandbox evidence: UNAVAILABLE (%s) -- this run has not "
                "shown that nothing was lost" % (indent, block.get("error"))]
    out = ["%ssandbox evidence: %s -- %s node(s), %s skipped%s"
           % (indent, v.upper(), block.get("n_nodes"), block.get("n_skipped"),
              (", floor %d" % block["node_floor"]) if block.get("node_floor") else "")]
    if v == V_NODE_LOSS:
        out.append("%s  !! COLLECTED %d NODE(S), FLOOR IS %d -- the sandbox ran "
                   "fewer tests than the registry was taken against, and no "
                   "skip or failure says so"
                   % (indent, block["n_nodes"], block["node_floor"]))
    for r in block.get("pin_expired", []):
        out.append("%s  !! PIN EXPIRED %s\n%s     was: %s\n%s     now: %s"
                   % (indent, r["nid"], indent,
                      (r.get("ack") or {}).get("reason_pin"), indent, r["reason"]))
    for r in block.get("unacknowledged", []):
        out.append("%s  !! UNACKNOWLEDGED skip %s: %s" % (indent, r["nid"], r["reason"]))
    for r in block.get("acknowledged_costly", []):
        out.append("%s  !! acknowledged but COSTLY (round %s): %s -- this test "
                   "kills mutants and did not run"
                   % (indent, (r.get("ack") or {}).get("acknowledged_round"), r["nid"]))
    for r in block.get("acknowledged", []):
        if r.get("ack_state") == ACK_COSTLY:
            continue
        out.append("%s  skipped, acknowledged (round %s, %s): %s"
                   % (indent, (r.get("ack") or {}).get("acknowledged_round"),
                      (r.get("ack") or {}).get("class"), r["nid"]))
    for r in block.get("dead_acknowledgements", []):
        out.append("%s  DEAD acknowledgement (suppresses nothing, delete it): %s"
                   % (indent, r["nid"]))
    return out


__all__ = ["REGISTRY", "ACK_HOLDS", "ACK_PIN_EXPIRED", "ACK_DEAD", "ACK_COSTLY",
           "V_NODE_LOSS", "V_SKIP_EVAPORATION", "V_UNAVAILABLE", "V_OK",
           "load_registry", "check", "verdict", "is_lost", "format_block",
           "parse_junit", "skip_key", "junit_node_id"]
