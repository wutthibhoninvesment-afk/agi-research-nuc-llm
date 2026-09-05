# Round 505 (harness A) — predictions, banked BEFORE measuring

Written at the start of the round, after reproducing the four reds and
reading `harness/reddebt.py` / `harness/crosstrack-registry.json`, and
BEFORE a single line of `harness/readset.py` existed. Scored honestly in
`knowledge/round-505-*.md`; a miss is the interesting result.

## What is being built

`harness/readset.py`: record, per test node, the set of repo files the node
actually READS (audit-hook `open`/`import`) and the set of repo directories
it SCANS (`os.listdir`/`os.scandir`), then answer the question no instrument
in this program answers today — *given the diff in my working tree right
now, which test nodes in OTHER tracks' suites can it redden?*

This attacks the same quantity `redattrib`/`reddebt` measure (the 83%
invisible-open rate) from the other end: `reddebt` tells round N+1 what
round N reddened, which is the floor of one. A read-set answers it for round
N, before the commit.

## Predictions

P1 (attribution). `test_swe_copyparity_real_subject.py` builds its scan in a
MODULE-scoped fixture (`real_scan`). The audit hook attributes reads to
whichever node is executing, so all ~108 file reads will land on exactly ONE
of the file's nodes (the first one pytest runs) and the other nodes in that
file will show near-empty read sets. Confidence HIGH. If true, node-level
blast is unsound for module-scoped fixtures and the query must union at FILE
level.

P2 (the additions problem — the central design claim). A read set of FILES
alone will NOT implicate any node for round 504's diff, because
`languages/whence/builtinlive.py` and `languages/whence/tests/
test_builtinlive.py` did not exist when the map was recorded and therefore
cannot appear in any node's read set. The SCAN set (directories) will
implicate both nodes. Confidence HIGH. This is the reason the instrument
records two sets instead of one.

P3 (overhead). The audit hook costs less than 2x wall-clock on
`test_swe_copyparity_real_subject.py`, whose un-instrumented cost this round
already measured at 10.5 s inside a 13-test run. Predicted recorded run of
the whole harness fast tier: under 3x its normal time. Confidence MEDIUM.

P4 (size). `test_the_real_whence_tree_has_no_unguarded_escape` reads 108
`*.py` files under `languages/whence` (measured this round from the failure
text). Its recorded FILE set will be between 100 and 130 repo-relative
paths. Confidence MEDIUM-HIGH.

P5 (whenceslow). `test_the_real_tree_yields_the_units_round_469_measured`
will record at least 30 files under `languages/whence/tests/` and will
include `languages/whence/pytest.ini` in its file set. Confidence MEDIUM —
`whenceslow.dep_digests`/`subject_digest` are not called by this node, only
`slow_tier_units()`, so `pytest.ini` may not be read at all.

P6 (blast breadth). Replaying round 504's diff (`languages/whence/
builtinlive.py`, `languages/whence/tests/test_builtinlive.py` added) against
the recorded map will implicate BOTH reddened files, and MORE than those two
— an over-approximation is expected because several harness tests walk
`languages/whence`. Predicted implicated-file count: between 3 and 12
inclusive. Confidence LOW on the number, HIGH on "both, plus at least one
more".

P7 (the reddebt headline). `harness/reddebt.py`'s `note()` head string
hardcodes "The wiring-audit trio below is the fifth instance..." — a
sentence about round 493's OWN red set. Every round since 493 has been
handed a headline that misdescribes its own list, and this round's list is a
copyparity trio, not a wiring-audit one. Predicted: no test in
`harness/tests/test_reddebt.py` asserts anything about the head sentence's
agreement with the rows. Confidence HIGH.

P8 (the whence-side recurrence). `languages/whence/builtinlive.py:124` is
the SAME defect shape round 467 fixed in `languages/whence/specreg.py:179`
(an import-time `dirname(dirname(ROOT))` repo-root escape), and round 467 is
the round `reddebt` names as the last close of this very episode. Predicted:
the two-line `os.environ.get("AGI_RESEARCH_ROOT") or ...` form turns all
three copyparity nodes green with no other edit. Confidence HIGH.

P9 (cost of the fail-closed registries). `harness/readset.py` will have a
`__main__` guard, so it is an ENTRY POINT and `wiring_audit` W001 will go
red unless this round declares it. Predicted: adding the file without a
`harness/wiring-registry.json` entry reddens exactly the three
`test_wiring_audit.py` nodes named in that registry's own prose. Confidence
HIGH — this is the recurrence the RED DEBT headline is about, and this round
is in a position to walk into it on purpose and check.
