#!/usr/bin/env python3
"""reddebt.py — what is red RIGHT NOW, for how long, and who opened it.

Round 493 (harness A).

`harness/redattrib.py` (round 455/461) answers a HISTORICAL question: over
the whole retained corpus of per-round health logs, what share of red
episodes were opened by a round that could not have seen the red by running
its own track's suite? That number is 83%, and it is a fact about the
program's shape.

This module answers the OPERATIONAL question the same files can answer and
nobody was asking: **which nodes are red at this moment, since when, and
whose commit opened them** — computed before a round starts and put in the
round agent's prompt, so the answer reaches somebody who can act on it.

WHY IT EXISTS — a recurrence that diagnosed itself four times and was never
instrumented. `harness/wiring-registry.json` carries four entries whose
`reason` fields, written by rounds 473, 479 and 485, describe the SAME
event: a round builds a new `nuc/*.py`, does not declare it, W001 goes red,
and three nodes of `harness/tests/test_wiring_audit.py` go red with it.
Round 485's entry drew the mechanism explicitly —

    "a track that does not run harness/tests/ cannot see the check its own
     commit reddens, and the reader is always a D round"

— and closed its instance at a latency of ONE round, as rounds 473 and 479
had. Round 490 (E) built `nuc/record_union.py`. Round 491 was a D round; it
ran on that red and did not close it. Round 492 (C) did not either. Round
493 found it at a latency of THREE rounds.

So the second half of that sentence is refuted — the reader is NOT always a
D round, it was a D round three times running by luck — and the first half
is sharper than it was written: nothing in this program TELLS the next round
which checks are red. `run_driver.sh` computes exactly one pre-round
diagnostic into the prompt, `$ROUND_GAP_NOTE` from
`check_round_recorded.py`. A round learns about record gaps because it is
told; it learns about red tests only if it goes looking, and for three
rounds nobody did.

THREE THINGS THIS GETS RIGHT THAT A NAIVE READER GETS WRONG
-----------------------------------------------------------
1. **A log with no `FAILED` line is not a green run.** A check killed at its
   budget writes no `FAILED` lines at all, so "last log wins" reads it as
   clean and the debt silently disappears on exactly the rounds the tree is
   least healthy. That is the defect `knowledge/round-349-a-suite-that-
   cannot-run-is-not-a-suite-that-passes.md` is named after; `redattrib`
   already owns the detector (`COUNT_LINE` / `could_not_run`) and this
   module CONSUMES it rather than re-deriving it. A check whose most recent
   log has no verdict is reported against its last round WITH a verdict, and
   the note says how many rounds stale that makes it.

2. **Red is not one shape, and the first cut at saying so was wrong.** One
   of the four harness reds is not a defect at all:
   `test_swe_mutation.py::test_the_grandchild_pid_survives_a_grandchild_
   slower_than_the_cap` passes solo in 4.2 s, passes under three spinning
   CPU hogs, passes under a three-process fork storm, and passes in whole-
   file order — and is red in 490, 491 and 492. Telling a round "fix these
   four" when one of them cannot be reproduced by anything the round can run
   is how an instrument loses its reader.

   This module's FIRST classifier called a node `flapping` if it had any
   green round in a trailing window. Run against the live logs it returned
   `0 standing, 14 flapping` — every node younger than the window scores
   green rounds from BEFORE its own episode started, so the rule was a
   restatement of "the episode is recent". The rule that survives contact
   with the data counts EPISODES, not green rounds, and it separates the
   corpus cleanly:

     * `new`       — no prior episode. This node has never been red before.
                     Whatever opened it, opened it once. (The five
                     `test_testcorpus_census.py` reds, first red ever at 492.)
     * `recurrent` — it has closed before and re-opened. The grandchild test
                     has four episodes (459-460, 475, 485, 490-); the wiring
                     trio has six. The instrument does NOT claim to know
                     which of those is a flake and which is a real cause that
                     keeps recurring — the wiring trio's episodes each have a
                     findable cause and the grandchild's do not — so it says
                     the number and tells the reader to reproduce first.

   The distinction it will not fake: a recurrent red and a flaky red look
   identical in these logs, and a classifier that guessed between them would
   be reporting a verdict it cannot derive.

3. **The opener is not the owner.** The wiring trio is owned by
   `harness/tests` and was opened by an `NUC-integration(E)` round. That gap
   IS the mechanism, so the note prints both and never collapses them.

Commands
--------
`--root PATH` is a TOP-LEVEL option and must come BEFORE the subcommand
(`reddebt.py --root /tmp note`, not `reddebt.py note --root /tmp`). It exists
because the first version hardcoded this repo, so `debt --strict` run in any
other tree silently answered about THIS one — which is the same class of
defect this module was built to report, committed by the module itself.

    python3 harness/reddebt.py [--root PATH] debt [--json] [--window N] [--strict]
        Every currently-red node with its age, shape, opener and owner.
        `--strict` exits 1 if ANY currently-red node is at least one full
        rotation (6 rounds) old — a red no track's own suite has closed in a
        complete pass of the rotation. Deliberately not wired into the
        driver; see `note`.

    python3 harness/reddebt.py [--root PATH] note [--window N] [--min-logs N]
        The prompt-shaped paragraph `run_driver.sh` appends to $PROMPT.
        Prints nothing and exits 0 when there is no debt, so a healthy tree
        costs the prompt zero bytes. Always exit 0: this is a measurement
        the driver quotes, never a gate that can stop a round. `--min-logs`
        lowers the evidence floor and exists so a test can exercise the
        reporting path without fabricating 50 logs; the floor stays live.

    python3 harness/reddebt.py [--root PATH] state [--json]
        Per-check: the last round with a verdict, that verdict, and how many
        trailing rounds had none.

Exit codes are 0 except for `debt --strict`.
"""

import argparse
import json
import os
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import redattrib as RA  # noqa: E402

#: One full pass of the track rotation (CLAUDE.md ground rule 6). A red this
#: old has survived a round of every track, including the one that owns it.
ROTATION = 6

#: How many of each check's own verdict rounds the recurrence count looks
#: back over. A node that closed and re-opened inside this many of its own
#: runs is `recurrent`; one whose only prior episodes are older than it is
#: reported with the full history in `prior_episodes_all` and still counts as
#: `new` here, because a red last seen 80 rounds ago is not evidence about
#: this one. 0 means "the whole retained corpus".
DEFAULT_WINDOW = 40

GREEN, RED, NO_VERDICT = "green", "red", "no_verdict"


def check_rounds(root=ROOT):
    """prefix -> {round: (verdict, frozenset(red nodes))}, every retained log.

    `read_logs` maps a log with no `FAILED` line to an empty set for all four
    checks. For the three pytest checks that is ambiguous — a clean run and a
    killed run look identical there — so `could_not_run`, which asks the
    orthogonal question "is there a pytest count line", decides between them.
    `skills-check` is not pytest-shaped; `read_logs` builds its rows from
    `corpus_rows`, which only has a key for a round in which the table was
    actually written, so absence already means "did not run" there and
    applying the pytest heuristic to it would be round 455's own mistake.
    """
    runs = RA.read_logs(root)
    cnr = RA.could_not_run(root)
    out = {}
    for prefix, per_round in runs.items():
        blind = set(cnr.get(prefix, ()))
        rows = {}
        for rnd, nodes in per_round.items():
            if rnd in blind:
                rows[rnd] = (NO_VERDICT, frozenset())
            else:
                rows[rnd] = (RED if nodes else GREEN, nodes)
        out[prefix] = rows
    return out


def check_state(root=ROOT, rows=None):
    """prefix -> dict describing where each check actually stands.

    `last_verdict_round` is the most recent round the check produced a
    readable verdict in — NOT simply the most recent round it has a log for.
    `stale_rounds` is how many logs sit after it with no verdict, and it is
    the number that keeps this honest: a debt list computed at
    `stale_rounds = 3` is a claim about a three-round-old tree.
    """
    rows = rows if rows is not None else check_rounds(root)
    out = OrderedDict()
    for prefix in RA.CHECKS:
        per = rows.get(prefix, {})
        ordered = sorted(per)
        with_verdict = [r for r in ordered if per[r][0] != NO_VERDICT]
        last = with_verdict[-1] if with_verdict else None
        out[prefix] = {
            "check": RA.CHECK_LABEL[prefix],
            "n_logs": len(ordered),
            "last_log_round": ordered[-1] if ordered else None,
            "last_verdict_round": last,
            "verdict": per[last][0] if last is not None else None,
            "red_nodes": sorted(per[last][1]) if last is not None else [],
            "stale_rounds": (len([r for r in ordered if last is not None
                                  and r > last])),
        }
    return out


def _episode(node, rounds_with_verdict, per):
    """(first_red_round, age) of the red run ENDING at the last verdict round.

    Walks backwards from the end while the node is in each round's red set;
    the first round it is not red in terminates the episode. Only rounds the
    check produced a verdict in are walked, so a killed check extends nothing
    and closes nothing.
    """
    age, first = 0, None
    for rnd in reversed(rounds_with_verdict):
        if node in per[rnd][1]:
            age += 1
            first = rnd
        else:
            break
    return first, age


def debt(root=ROOT, window=DEFAULT_WINDOW):
    """Every node red in its check's most recent verdict round.

    One record per node:
      check, node, owner       — the suite it lives in and that suite's track
      first_red_round, age     — the current episode, in verdict rounds
      opener                   — the track running when the episode opened
      invisible_open           — opener != owner: the mechanism, named
      shape                    — `new` | `recurrent` (see the module docstring;
                                 this is NOT a flake verdict)
      prior_episodes           — closed episodes inside the window
      prior_episodes_all       — closed episodes over the whole retained corpus
      last_closed_round        — the round the previous episode closed in
      overdue                  — age >= one full rotation of the tracks
      stale_rounds             — trailing no-verdict rounds after the verdict

    Episodes come from `redattrib.episodes_for`, so a node's history here and
    its history in the attribution table cannot drift apart.
    """
    rows = check_rounds(root)
    state = check_state(root, rows)
    tracks = RA.round_tracks(root)
    out = []
    for prefix, st in state.items():
        if st["last_verdict_round"] is None or st["verdict"] != RED:
            continue
        per = rows[prefix]
        wv = [r for r in sorted(per) if per[r][0] != NO_VERDICT]
        recent = wv[-window:] if window else wv
        for node in st["red_nodes"]:
            first, age = _episode(node, wv, per)
            red_all = {r for r in wv if node in per[r][1]}
            eps_all = RA.episodes_for(node, wv, red_all)
            eps_win = RA.episodes_for(node, recent,
                                      red_all & set(recent))
            # The last episode in each list is the OPEN one (close is None);
            # everything before it has closed at least once.
            prior_all = [e for e in eps_all if e["close"] is not None]
            prior_win = [e for e in eps_win if e["close"] is not None]
            suite = RA.node_suite(node)
            owner = RA.SUITE_OWNER.get(suite)
            opener = tracks.get(first)
            out.append(OrderedDict([
                ("check", st["check"]),
                ("node", node),
                ("owner", owner),
                ("first_red_round", first),
                ("age", age),
                ("opener", opener),
                ("invisible_open",
                 bool(opener and owner and opener != owner)),
                ("shape", "recurrent" if prior_win else "new"),
                ("prior_episodes", len(prior_win)),
                ("prior_episodes_all", len(prior_all)),
                ("last_closed_round",
                 prior_all[-1]["close"] if prior_all else None),
                ("overdue", age >= ROTATION),
                ("window", len(recent)),
                ("stale_rounds", st["stale_rounds"]),
            ]))
    out.sort(key=lambda r: (-r["age"], r["check"], r["node"]))
    return out


def _invisible_clause(items):
    """The one sentence in the head that has to be DERIVED, and the round-505
    finding that says why.

    Round 493 wrote this paragraph's headline with its own red set spelled
    into it -- "the wiring-audit trio below is the fifth instance of a
    recurrence `harness/wiring-registry.json` has diagnosed in prose four
    times since round 473". True when written. Round 505 was handed that
    sentence above a list of three `test_swe_copyparity_real_subject.py`
    nodes and one `test_whenceslow.py` node, none of which is a wiring
    audit and none of which is an instance of that recurrence. Twelve rounds
    were told about the wrong red.

    That is the same defect the module exists to fight, one level up: a
    finding written into prose instead of computed, which then rots while
    reading exactly as authoritative as it did on the day it was true. So
    the count, the suite files and this clause all come from `items`.
    """
    n = sum(1 for r in items if r["invisible_open"])
    if not n:
        return ("Every one of them was opened by the track that owns the "
                "suite, so every one was visible to its author at the time.")
    return ("%d of them %s opened by a track that does NOT run the reddened "
            "suite, so no run their author could have made would have shown "
            "it. `python3 harness/readset.py blast` (round 505) answers that "
            "from the opener's side -- it maps your working-tree diff onto "
            "the test nodes that read or scan what you changed, before you "
            "commit."
            % (n, "was" if n == 1 else "were"))


def note(root=ROOT, window=DEFAULT_WINDOW, min_logs=None):
    """The paragraph `run_driver.sh` appends to the round prompt, or "".

    Deliberately shaped like `check_round_recorded.py`'s gap note, because a
    round already reads that one: a headline sentence that says what the
    thing is, then one line per item, then the single instruction that makes
    the difference between a reader and an actor.
    """
    floor = RA.MIN_EVIDENCE_LOGS if min_logs is None else min_logs
    n_logs = sum(len(v) for v in RA.read_logs(root).values())
    if n_logs < floor:
        return ("\n\nRED DEBT: NO EVIDENCE BASE — this checkout holds %d "
                "retained per-round health log(s), below the %d this "
                "measurement needs. `logs/` is not in git, so a fresh clone "
                "or a detached worktree sees almost none of it. Reporting "
                "'nothing is red' from here would be a claim about the "
                "checkout, not about the tree."
                % (n_logs, floor))
    items = debt(root, window)
    if not items:
        return ""
    stale = sorted({r["stale_rounds"] for r in items if r["stale_rounds"]})
    suite_files = sorted({r["node"].split("::")[0] for r in items})
    lines = []
    for r in items:
        lines.append(
            "   %-16s %s — red %d round(s)%s, since round %s (opened by %s%s); "
            "owner %s; %s"
            % (r["check"], r["node"], r["age"],
               " — PAST ONE FULL ROTATION" if r["overdue"] else "",
               r["first_red_round"],
               r["opener"] or "unknown",
               ", who does not run this suite" if r["invisible_open"] else "",
               r["owner"] or "unknown",
               "NEW — first time this node has ever been red"
               if r["shape"] == "new" else
               "RECURRENT — %d earlier episode(s), last closed at round %s. "
               "REPRODUCE IT BEFORE FIXING IT: a red that has closed by "
               "itself before may be the runner, not the code."
               % (r["prior_episodes"], r["last_closed_round"])))
    head = (("\n\nRED DEBT (added round 493, harness A — the per-round health "
             "logs, read before your round starts). %d test node(s) are red at "
             "the latest reading of their own check, in %d suite file(s): %s. "
             "This is the only route by which a red reaches you: the four "
             "health checks run AFTER your process exits and write to "
             "`logs/`, which is not in git, so a check your commit reddens is "
             "invisible to you unless you are told. %s Note OWNER vs OPENER: "
             "a red opened by a track that does not run the reddened suite "
             "will not be seen by the track that does unless somebody carries "
             "it. A RECURRENT node has closed by itself before, so it is not "
             "a defect you can fix by reading it — reproduce it first, and if "
             "it only fails under the driver's four concurrent suites on a "
             "box whose `nproc` is 1, say THAT instead of patching the "
             "test.\n")
            % (len(items), len(suite_files), ", ".join(suite_files),
               _invisible_clause(items)))
    tail = ""
    if stale:
        tail = ("\n   NOTE: %s of these come from a check whose most recent "
                "log(s) had NO readable verdict (killed at its budget), so "
                "the state above is up to %d round(s) old. A check that could "
                "not run is not a check that passed."
                % ("some" if len(stale) > 1 else "all", max(stale)))
    return head + "\n".join(lines) + tail


def cmd_debt(args):
    root = args.root
    items = debt(root, args.window)
    if args.json:
        print(json.dumps(items, indent=2))
    else:
        n_logs, enough = RA.evidence_base(root)
        if not enough:
            print("NO EVIDENCE BASE: %d retained log(s) < %d"
                  % (n_logs, RA.MIN_EVIDENCE_LOGS))
        for r in items:
            print("%-19s %-9s age %2d%s since %s  prior %d/%d  "
                  "opener %-20s owner %-20s %s"
                  % (r["check"], r["shape"], r["age"],
                     " OVERDUE " if r["overdue"] else "         ",
                     r["first_red_round"], r["prior_episodes"],
                     r["prior_episodes_all"],
                     r["opener"], r["owner"], r["node"]))
        print("red-debt: %d node(s) red, %d new, %d recurrent, "
              "%d invisible-open, %d at or past one rotation (%d rounds)"
              % (len(items),
                 sum(1 for r in items if r["shape"] == "new"),
                 sum(1 for r in items if r["shape"] == "recurrent"),
                 sum(1 for r in items if r["invisible_open"]),
                 sum(1 for r in items if r["overdue"]), ROTATION))
    if args.strict:
        return 1 if any(r["overdue"] for r in items) else 0
    return 0


def cmd_note(args):
    text = note(args.root, args.window, args.min_logs)
    if text:
        sys.stdout.write(text.lstrip("\n") + "\n")
    return 0


def cmd_state(args):
    st = check_state(args.root)
    if args.json:
        print(json.dumps(st, indent=2))
        return 0
    for prefix, r in st.items():
        print("%-16s logs %3d  last log %s  last verdict %s = %-10s "
              "stale %d  red %d"
              % (r["check"], r["n_logs"], r["last_log_round"],
                 r["last_verdict_round"], r["verdict"], r["stale_rounds"],
                 len(r["red_nodes"])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT,
                    help="repo root to read logs/ from (default: this one)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("debt", help="currently-red nodes with age and opener")
    p.add_argument("--json", action="store_true")
    p.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    p.add_argument("--strict", action="store_true",
                   help="exit 1 if a standing red is >= one rotation old")
    p.set_defaults(fn=cmd_debt)

    p = sub.add_parser("note", help="the paragraph run_driver.sh injects")
    p.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    p.add_argument("--min-logs", type=int, default=None, dest="min_logs")
    p.set_defaults(fn=cmd_note)

    p = sub.add_parser("state", help="per-check last verdict and staleness")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_state)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 0
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
