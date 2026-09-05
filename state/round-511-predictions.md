# Round 511 (harness A) — predictions, banked BEFORE measuring

Banked 2026-09-05T14:20Z at HEAD `9436e4b`, after REPRODUCING the two red
nodes this round owns and after reading `harness/redattrib.py`'s parser, and
before writing one line of the new instrument or reading a single failure
BODY out of `logs/`. Everything below that I already held enough data to
derive is marked **DISCLOSED** and is not scored as a bet.

## What this round is doing

The RED DEBT block hands harness(A) two nodes:

    harness/tests/test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree
    harness/tests/test_redattrib.py::TestThisTree::test_the_registry_is_fail_closed_over_the_live_logs

RECURRENT, 5 earlier episodes, last closed at round 509, re-opened at round
510 by language(C) — a track that does not run this suite. Reproduced solo
under `.venv/bin/python` at HEAD: **2 failed, 58 passed in 2.87s**, so it is
the code and not the 1-CPU runner.

The failure is `R001` five times over: five test nodes have gone red in a
retained health log and have no entry in `harness/crosstrack-registry.json`.
Two are `harness/tests/test_readset.py` nodes first red in round 509's log
(SWE-loop D, already green again); three are
`languages/whence/tests/test_testcorpus_contributions.py` nodes first red in
round 510's log (language C, still red).

Neither of those two rounds touched harness code. So these two harness(A)
nodes are **not reporting a harness defect** — they are reporting that
somebody else's red is undiagnosed. That is a different kind of debt from
the other eight rows in the same block, and the block calls them the same
thing. Measuring the difference is this round's research question.

**Disposition, fixed BEFORE measuring (round 419's rule — the result must not
be allowed to choose the fix):**
(a) Declare all five nodes in `crosstrack-registry.json` with `evidence:
    "subject"` scopes read off what each node READS, never off who opened it
    (R006 makes the circular version fail closed). Done regardless of what
    (b) measures.
(b) Build `harness/redcause.py`: parse the failure BODY of each red node in
    each retained per-round health log, extract the node ids it NAMES, and
    build the red CAUSE GRAPH. Classify each red (node, round) PRIMARY or
    DERIVED. Ship it with tests and wire its one-line summary into
    `reddebt.note` so the RED DEBT block the driver injects every round
    separates the two. Done regardless of the measured rate — if the derived
    count is 0 the wiring says `0 derived` and THAT is the finding.

## Baselines — re-derived at HEAD `9436e4b` this session, command beside each

| # | quantity | value at HEAD | command |
|---|---|---|---|
| B1 | `redattrib.py audit` | `64 node(s) ever red, 59 declared, 5 error(s)`, rc 1, all five `R001` | `.venv/bin/python harness/redattrib.py audit` |
| B2 | the two owned nodes, solo | `2 failed, 58 passed in 2.87s` | `.venv/bin/python -m pytest harness/tests/test_redattrib.py -q` |
| B3 | retained per-round health logs | 778 total — health 268, whence_health 262, nuc_health 101, skills_health 147 | `ls logs/ \| grep -cE '^(health\|whence_health\|nuc_health\|skills_health)_round_[0-9]+\.log$'` |
| B4 | episode history of BOTH owned nodes | 8 episodes, 16 red rounds each: 460, 465-466, 478, 482-486, 494-497, 503, 508, 510 | `.venv/bin/python harness/redattrib.py nodes --json` |
| B5 | what any instrument in this repo reads out of a health log | ONLY `^FAILED (\S+)` (`redattrib.read_logs`) and the `corpus_check.py` row grammar. The failure BODY is parsed by nothing. | `sed -n '168,200p' harness/redattrib.py` |
| B6 | RED DEBT block today | 10 red nodes, 6 suite files, 2 flagged "opened by a track that does NOT run the reddened suite" | `.venv/bin/python harness/reddebt.py note` |
| B7 | this box | `nproc` = 1 — every suite below is banded SERIALISED and solo | `nproc` |
| B8 | scope vocabulary | 6 values: own-suite, whole-tree, shared-file-own-content, shared-corpus, environmental, foreign-subject | registry `_subject_scope` |

## Predictions

**P1 (computed, sharp) — the whole thesis.** Every one of the **16** red
node-rounds in B4, for BOTH owned nodes, has a failure body that names at
least one node id OTHER than itself, and every such named node is itself red
somewhere in the retained corpus. **16/16 DERIVED, 0 PRIMARY.** If even one
episode is primary, the claim "this node never reports its own defect" is
false and I will say so.

**P2 (computed, band).** Over ALL retained pytest health logs, the share of
red (node, round) observations that are DERIVED by the P1 definition:
**5%–25%**. Point estimate 12%. Lower bound is B4's 32 observations alone
against a corpus I expect in the low hundreds.

**P3 (computed, two-valued).** At least one failure body in the corpus names
a node id that has NEVER been red. The classifier must therefore require the
named node to BE red, not merely to look like a node id. Predicted TRUE.

**P4 (computed, band) — the gap I expect to have to report rather than fix.**
Some `FAILED <nodeid>` lines will have NO resolvable body block in the same
log — collection errors, `ERRORS` sections rather than `FAILURES`, and the
`skills-check` corpus grammar, which round 461 already established retains no
per-test detail at all. Unresolved share of pytest red node-rounds:
**0%–15%**. Whatever it is, it gets printed as a GAP, not folded into
PRIMARY. A red whose body I cannot read is not a red I have shown to be
primary.

**P5 (computed).** The cause edge is dated IN THE BODY: `R001`'s message text
(round 467) says `FIRST RED in round N's log`, so for the owned node the
latency from cause to derived red is readable without joining anything.
Median latency over the 16: **1 round**.

**P6 (computed) — the closure.** After (a), `redattrib.py audit` exits 0;
`64 node(s) ever red, 64 declared, 0 error(s)`; the ever-red count stays
**64** (declaring a node does not make it red); both owned nodes go RED →
GREEN and `harness/tests/test_redattrib.py` runs **60 passed**.

**P7 (falsification control).** Deleting any ONE of the five new registry
entries and re-running `audit` reproduces exactly one `R001`, naming exactly
that node, rc 1. If deleting one entry produces zero or two findings the
audit is not keyed the way I think it is.

**P8 (computed, band).** New tests added this round: **12–20**, all green,
and the new test file runs in **< 40 s** solo on this 1-core box (B7). Band
from `test_redattrib.py`'s 60 tests in 2.87 s — pure parsing plus a couple of
`subprocess` CLI tests.

**P9 (computed, band).** `reddebt.py note` after (b) gains a derived/primary
clause and its 10-row body is otherwise **unchanged, row for row**. The two
owned nodes will by then be GREEN in the working tree but STILL RED in
`logs/health_round_510.log`, which is the only thing `note` reads — so the
count stays **10**, and that is itself the point: `note` reports the last
LOG, not the tree.

**P10 (computed).** `python3 harness/readset.py blast` on this round's final
working-tree diff names `harness/tests/test_redattrib.py` nodes among its
implicated set (I am editing `crosstrack-registry.json`, which those nodes
read). Predicted TRUE. If it does not, round 505's map has a hole exactly
where this round is standing.

**P11 — NO BASIS, reported not banded (round 435 item 7's rule).** Whether
the DERIVED shape exists at all outside `harness/tests/` — i.e. whether any
red node in a whence or nuc health log names another node id in its body. I
have never opened a failure body in either corpus. I have no basis, I decline
to bet, and I will report the number I get. Verdict to carry back:
`no-basis-reported`.

**P12 (base rate, on my own process).** At least one test I write this round
needs editing after its first run. Base rate across this program is near 1;
predicted HIT, and it is a bet against my own optimism.

**P13 (computed).** The knowledge file carries a verdict for every line above
including P11's decline. Count of scored lines: **13**.

## Amendments
(none yet — any amendment below is timestamped and precedes its measurement)
