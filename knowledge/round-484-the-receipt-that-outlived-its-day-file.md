# Round 484 (NUC-integration E) — the receipt that outlived its day file by 3.7 seconds

**Track:** NUC-integration(E). **Base:** `b7604a1`. **Box:** UP, boot
`0d0e3188da124a4b9f78b26dd95d3ea2`, `uptime -s 2026-09-03 09:37:09Z`,
16h02m in — the SAME boot round 478 saw. Second consecutive up round; the
436–472 outage is still the last one.

**Artefacts:** `nuc/summary_fossil.py` (corrected + `sweep_margins`),
`nuc/fossil_ledger.py` (new), `nuc/tests/test_fossil_ledger.py` (new),
`nuc/tests/test_summary_fossil.py`, `nuc/tests/test_reachability_check.py`,
`state/nuc-capture-r484/`, `state/nuc-fossil-ledger.jsonl`,
`state/nuc-reachability-log.jsonl`, `state/known-escalated-diffs.json`,
`nuc/predictions-e-round484.md`, NUC `/work/logs/nuc-sweep-edge.md`.

## 0. The one-line finding

Round 478 proved that a missing `sarNN` cannot be rotation, from a theorem
that the two files "always share a verdict". **The first sweep this program
has ever observed split a pair by three and a half seconds** — and the
direction it splits in is the one that carries positive evidence, which the
instrument was discarding.

## 1. What the sweep actually did

`sysstat-summary` fired at **2026-09-04T00:07:18Z**. Round 478 forecast it
would delete eight files: `sa23 sa24 sa25 sa26 sar23 sar24 sar25 sar26`.
It deleted **seven**. `sar26` is still on the box.

    -rw-r--r-- 1 root root 483198 Aug 27 00:07 sar26     <- survived
    (sa26, Aug 26 23:50)                                 <- swept

`stat` gives `sar26` an mtime of **2026-08-27T00:07:21.677**. The sweep ran
at **00:07:18**. That is 8 days *less 3.7 seconds*.

## 2. Why, exactly

Three facts, each read rather than assumed:

* `/usr/lib/sysstat/sa2` **renders the receipt and THEN sweeps**, in that
  order, in one script — `sar.sysstat ... > ${RPT}` above
  `find "${SA_DIR}" -type f -mtime +${HISTORY} | xargs rm -f`.
* `sysstat-summary.timer` is `OnCalendar=00:07:00` with **no `AccuracySec=`
  override**, so systemd may fire it anywhere in a one-minute window. The six
  fire instants in this round's captured journal are `00:07:21, 00:07:21,
  00:07:04, 00:07:04, 00:07:05, 00:07:18` — a **17-second spread**.
* `find -mtime +7` is `int(age_s // 86400) > 7`, i.e. it bites at age
  **≥ 8 days exactly**.

Put together: `saNN` is stamped ~23:50 on day NN and `sarNN` ~00:07 on day
NN+1. At the sweep, the day file's age is (whole days **+ 17m14s**) and the
receipt's is (whole days) **± the jitter between two fires**. So the day file
is never near the boundary and **the receipt is always exactly on it**, once
per file, on precisely one day of its life. Round 478's arithmetic was right
in exact terms and wrong about which quantity is exact.

The split has **one direction**. The receipt is 17 minutes younger, so it can
only ever outlive its day file, never predecease it — by exactly one sweep,
then it dies (age 9 days; no jitter reaches 86400 s). The observable is a
**one-day window** with `sarNN` present and `saNN` gone: an *orphan receipt*.

Round 478 called an orphan "a genuine anomaly", in a code comment whose
parenthetical reason — "the receipt is younger and dies no earlier" — is the
false sentence. It is not an anomaly. It is routine, and it is scheduled.

## 3. Why that mattered more than it looks

Round 478's `fires()` keyed every verdict off the `saNN` file, listed orphans
in a side field, and scored none of them. But **a receipt is self-sufficient
evidence**: `sa2` writes it only when it runs, so it dates a fire whether or
not the day file it rendered still exists.

And the orphan is never a random day. It is always the **oldest decidable
day** — the frontier one, the one whose record is about to exist nowhere but
in a capture. Keying off the day file threw away evidence exactly where the
evidence was scarcest.

Fixed: orphan rows are scored `fire_ran` with `evidence: "receipt_only"`,
kept distinguishable from a day backed by a surviving day file, and still
listed in `orphan_receipts` so the existing grep target survives. On the live
capture the fossil goes **7 → 8 decidable fires**, recovering
2026-08-27T00:07 from a receipt whose day file is gone.

## 4. `sweep_margins` — the edge made computable, and confirmed twice

If the boundary is decided by which of two fires landed later in its minute,
then a capture that banks the journal can compute it. `sweep_margins()` reads
`Starting sysstat-summary.service` lines only (the *Starting* line, because
the render is near the top of `sa2` and the `find` at the bottom — scoring
off `Finished` would bias every margin by the service's own duration), and
for each fire `W` reports

    margin = (S − W) − (HISTORY + 1) days,   S = the fire at W + 8 days

Negative ⇒ the receipt clears a boundary its day file failed ⇒ orphan.

On `state/nuc-capture-r484` it returns **exactly one `orphaned` row, at
−3.0 s, for the receipt written 2026-08-27T00:07:21Z**, swept by
2026-09-04T00:07:18Z. That is `sar26`.

**Two disjoint sources agree.** `fires()` reads the filesystem *listing* and
finds `sar26` orphaned. `sweep_margins()` reads only journal *timestamps* and
names the same receipt. Neither input mentions the other. Pinned as
`test_the_live_journal_predicts_exactly_the_orphan_that_happened`.

An honest limit: a journal line has whole-second precision while the real
mtime carries a fraction (`.677`). Margins inside
`MARGIN_RESOLUTION_S = 2.0` are reported `undecidable` rather than guessed.
This round's case cleared by 3 s, so it is decidable.

## 5. The union ledger — round 478's next-steps 4 and 5

Round 478 wrote both as hypotheticals. This round watched item 4 stop being
one: the fossil read off the live box went **10 decidable fires → 8**
overnight, and 2026-08-24/-25/-26 are no longer derivable from the box at all.

`nuc/fossil_ledger.py` unions every capture, keyed by fire instant, into an
append-only JSONL. Design decisions worth naming:

* **Agreement is the null hypothesis.** Two captures read the same
  filesystem at different times; the underlying fact is immutable. A conflict
  is reported as a `DISAGREE` row and never reconciled — a receipt cannot
  un-exist, so a conflict means an instrument or a capture is wrong, and that
  must reach a human.
* **A refusal is not a vote.** `fire_pending` is the module declining to
  answer, and it must not drag a later capture's real verdict into a
  disagreement.
* **`now` is never a file mtime.** `ls -l` omits the year, so the listing
  needs the instant it was taken — and git does not preserve mtimes, so a
  fresh clone would date every capture to its checkout. It comes from the
  `LAST ENTRY` of boot 0 in the capture's own `journal-boots.txt`, labelled
  `now_source: boot_table`; captures predating that file must have it
  declared, labelled `declared`.
* **An unusable capture is named, not skipped.** Round 406's lesson. Five of
  the nine captures in this repo have no sysstat listing at all; a `glob`
  that quietly dropped them would report the union as covering everything.

Live result: **4 captures read, 5 named unusable, 11 fire instants, 0
disagreements**, against 10 for the best single capture (r478) and **8 for
the newest**. Append is idempotent on `(fire_utc, verdict)`; a changed
verdict is appended and flagged `contradicts_prior` rather than overwritten.

## 6. A defect this round's own test found in this round's own module

`test_a_capture_with_no_receipts_contributes_nothing_and_says_so` went red on
first run. `n_decidable` was summing `fires()["counts"]`, which counts verdict
words; the union skips rows with no fire instant. With **no receipt anywhere**
in a listing there is no schedule to derive (round 448's rule: never hardcode
00:07), so every row comes back carrying a verdict word and `fire_utc: None`.
A capture taken deep in an outage would have reported `n_decidable: 2` and
contributed **nothing** — a number that reads as coverage and unions to zero,
which is the exact failure mode the module exists to prevent. Fixed to count
what the capture actually contributes.

## 7. Round 478's own missing row, and what closing it cost

`coverage --strict` **exited 1** at this round's start. Round 478 connected,
took a capture, wrote a 90-line addendum — and never appended its own row to
`state/nuc-reachability-log.jsonl`.

The structural reason it went unnoticed: **`coverage` excludes the in-flight
round.** So a round that omits its own row always passes its own gate, and
reddens the *next* one, six rounds later. Round 478's own next-step 1 told
this round to run that gate first, which is the only reason it was caught at
all.

Backfilled as `backfill-prose-r478`, `precision: coarse` — the addendum
quotes no LastSeen and this round will not invent digits. Gates then read
**0 / 0 / 1**, the state rounds 460–478 left.

**And closing the gap made the published ignorance go up.** Two pins moved:
`unobserved_total_s` 396378.0 → **426906.0**. Attributed rather than
re-baselined — removing *either* new row restores 396378.0 exactly; only both
together move it. A single observation of an up box has no interior and
creates no measurable interval; two create the 30528 s between
2026-09-03T17:10:54Z and 2026-09-04T01:39:41Z. **The program can now name a
stretch it previously could not see at all**, and naming it is what raised the
number. The affected test's docstring title ("no headline number moves") is
now false about that one number, and says so.

The other moved pins (`coarse` 20 → 21, `gaps_with_a_coarse_endpoint`
23 → 24) are corpus-derived and move whenever any E round appends a row.
Both tests now separate their **invariants** (`unearned_claims == []`,
`unearned_missed_excursions == []` — a rule holds them, and a later round
breaking them is a real finding) from their **census figures** (re-derive
them; do not preserve them).

## 8. Inherited record gaps, all four discharged

1. **Round 483's leftover diff** (3 files: its knowledge file's third-pass
   section, its ledger entry moving `unscored` → `scored`, the matching
   research-state paragraphs). Round 483 died at `--max-turns 135` at
   00:32:23Z with them dirty. Verified against `logs/driver.log` and `4a5f034`
   as entirely round 483's, committed unchanged as `7b05209`.
2. **`knowledge/mission-fold-fix-v1.md` was deleted, and not by a round.**
   The Hermes gateway ran 00:04–00:44Z (`3658e02`, `88d5165`, author HIVE,
   subject "reorganize docs for production release") and left the deletion
   *unstaged*. No round's knowledge file or research-state entry claims it,
   and `CLAUDE.md` cites the file **twice** as the briefing for CRITICAL
   MISSION #476. Committing the deletion would have created two dangling
   citations in the repo's own instruction file. **Restored.**
3. **The `languages/whence/SECURITY.md` escalation entry was dead** —
   `escalationguard.py audit` returns fate `REVERTED`, HEAD and worktree both
   at the pinned base `929c52c42523`, because the gateway rewrote its own edit
   away at 00:34:38Z. Deleted per the checker. But round 475's
   `landing_violations_note` says that remedy destroys the only
   machine-readable trace that the path was ever adjudicated — so the entry's
   substance moved to a `_resolved` key, which `load_escalated_diffs` does not
   read and which therefore suppresses nothing.
4. **Round 479** has no research-state entry and no knowledge file, but its
   work IS in git (`aedad26`), so nothing is at risk of being lost. Left for
   SWE-loop(D); flagged below.

### 8b. The escalated substance did not disappear — it got committed

The same commit that reverted `SECURITY.md` **added
`languages/whence/SECURITY_AUDIT_REPORT.md`**, 120 lines, and committed it.
Round 349's mitigation — "nothing has been published while it sits in the
working tree" — no longer holds.

Round 349's four claims, re-checked against the tree at HEAD: **still four for
four false.** No `.pre-commit-config.yaml`, and the only pre-commit hook is
round 475's `escalationguard.py`, which scans no secrets; no
`.github/workflows`; **0** git tags; no `.env`/`*.key` patterns in any
`.gitignore`.

**One of the four reappears in the new file**, as a green tick: §6's
`Vulnerability scanning | ✅ | Up-to-date as of 2026-09-04` — which §7 then
contradicts by recommending "Add automated security scan to GitHub Actions".
The file also carries a **new** falsifiable claim, `Verified test count:
875/875 tests passed`, against **2802 collected** at HEAD and 2682 passed /
4 skipped at round 483's health check; 875 matches no measurement in this
repo's record. Its §3 claim "No file system access" was checked and **holds**
(no `open()`/`shutil`/`Path` IO anywhere in `languages/whence/whence/*.py`).

Round 484 did **not** rewrite it, for round 349's reason: it is
outward-facing, in a domain where the operator has authorship interest, and
the decision is the operator's. Recorded in the registry's `_resolved` key.
**This is an escalation, not a resolution.**

## 9. Tests

`nuc/tests` — **1076 passed, 0 failed, 415 s**, run alone (`nproc` is 1).
Round 478 left 1037; round 483's health check left one failing
(`test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree`, a
nested full-suite run — green here, cause at 483 not re-derived).

**Mutation-tested, because a test that has never gone red is not a
falsifier.** 23 mutations across both modules. **First pass: 21 killed, 2
survived.** Both survivors were real gaps:

* `margin >= 0` → `margin > 0` survived, because the resolution guard
  swallows the boundary and nothing could reach it. Pinned by monkeypatching
  `MARGIN_RESOLUTION_S` to 0 and asserting that an age of *exactly* 8 days is
  a deletion (`floor(8d/86400) = 8 > 7`), not a reprieve.
* `REFUSALS = ()` survived, because my fixture's refusing capture had no
  receipts and so produced no fire instant at all — the `fire_utc is None`
  clause was doing the work, not the refusal rule. Re-fixtured so the refusal
  carries an instant, which is the only shape in which it can collide with a
  verdict.

**Second pass: 23 mutations, 23 killed, 0 survived.**

## 10. Box state, and what was touched

uptime 16h02m, load 0.00/0.00/0.00; Mem **5406 / 31984 MB used (16.9%)**,
**swap 0 of 4095 MB**, `Committed_AS` 5.48 GB. `qwen36-colibri` and
`qwen36-toolproxy` (USER units) both `active (running)` since
2026-09-03T09:37:19Z, **`NRestarts=0`** — no restart in 16 hours.

**Writes to the box: exactly one** — `/work/logs/nuc-sweep-edge.md`,
md5-verified `9291e9c73a0cf230939513b1486ba504` on both ends. **No unit
restarted. Port 8001 never contacted. No engine request of any kind.**
Nothing read or written outside the allowed paths.

Capture `state/nuc-capture-r484` taken FIRST (round 478's next-step 2),
before any analysis: **12 seconds, 2.3 MB compressed**.
`capture_manifest.py audit --strict` exits **0** — `complete`, 1 non-blocking
gap (no `Failed <unit>` lines, which with `Finished`/`Stopped` present is a
fact about the box, not a filter).

## 11. Predictions — 9 HIT, 3 MISS, 2 SPLIT of 14

Banked at `bb98f0c` (`nuc/predictions-e-round484.md`) before any of these
quantities was measured; base `b7604a1`.

| # | claim | outcome |
| --- | --- | --- |
| P1 | the 00:07Z fire ran; `sar03` exists | **HIT** — mtime 2026-09-04T00:07:18 |
| P2 | all eight of round 478's forecast files are gone | **SPLIT** — 7 of 8; `sar26` survived, and that is the round |
| P3 | r478's tar is the only copy and holds all eight | **HIT** — `tar tf` lists sa23-26 + sar23-26 |
| P4 | gates 0 / 0 / 1 | **SPLIT** — `coverage` was **1**, not 0 (round 478's missing row); the other two as predicted |
| P5 | ≥1 more boot lost off the front of the boot table | **MISS** — same 5 boots. But boot −4's FIRST ENTRY moved `12:57:42` → **`18:28:02`**: journald ate **5h30m of the oldest boot's interior** without dropping the boot. The decay is real and I predicted the wrong shape of it |
| P6 | ≥1 day r478 can decide and r484 cannot | **HIT** — three (08-24/-25/-26) |
| P7 | union > the 10 r478 gives alone | **HIT** — 11 |
| P8 | 0 disagreements across captures | **HIT** — 0 over 4 captures |
| P9 | memory < 20%, swap 0 | **HIT** — 16.9%, swap 0 |
| P10 | both units active, `NRestarts=0` | **HIT** |
| P11 | `audit --strict` exits 1 again | **MISS** — exits **0**. I reasoned "P5 says decay is worse, so the audit stays red" from a premise (P5) that was itself wrong |
| P12 | ≥2 of round 349's four claims reappear in the committed report | **MISS** — exactly **one** does. All four remain false against the tree, and the new file adds a *new* false claim (875/875), but the prediction as written lost |
| P13 | the deletion is the gateway's, no round claims it | **HIT** |
| P14 | suite > 1037 tests, 0 failures | **HIT** — 1076 / 0 |

**The three misses share one root and it is worth naming.** P5, P11 and P12
are all predictions about *how bad a known-bad thing had got*, made by
extrapolating a trend from a single prior observation — round 478's three
lost boots, round 478's red audit, round 349's four false claims. Every one
of them over-predicted. Round 483 banked the same lesson from the other
direction ("the bank had been shown exactly one instance of the class and
predicted the population from it"); this round did it three times in one bank
without noticing the shape. **A trend fitted to n=1 is a guess with a slope
on it.** The two SPLITs, by contrast, are the round's two best findings —
both are cases where the world did *most* of what was predicted and the
residual was the discovery.

## 12. Skill upgraded — `prediction-banking` step 20

Ground rule 5. The three misses in §11 are a shape round 483's step 19 does
not cover: step 19 is about extrapolating a **rate** across a class, and its
remedy is to count the class in §0. These extrapolated a **direction** for
the *same* quantity, where there is no class to count. Remedy: name the
mechanism rather than the direction (P5 was not wrong that journald was
decaying — it was wrong about what the decay acts on), and declare when one
line rests on another (P11 rested on P5, unstated, so one bad premise took
two lines).

The second half is the more useful one, and it comes from the SPLITs rather
than the misses: **prefer the form that can be partly wrong.** P2 enumerated
eight files, so it had eight places to be surprised, and the single survivor
is this entire round. "The sweep deletes old files" would have been a clean
HIT and found nothing.

Landing it required a split: the SKILL body was at **exactly 500 lines**, the
`skill_lint` B001 ceiling, so any addition turned a warning into an error.
Steps 19 and 20 now live in
`skills/prediction-banking/references/n1-and-trend-extrapolation.md` with
compact pointers in the body, which is **495 lines — five shorter than at
HEAD** — with 0 errors and no R004 duplication. Corpus lint is unchanged from
round 483's baseline (102 skills, 0 errors, the same 7 B002 warnings) and
`xref_check` reports **0 NEW** dangling citations.

## 13. Next E round, in order

1. **`sar26` is dead by now.** It was age 9 days at the 2026-09-05T00:07
   sweep and no jitter reaches 86400 s. Do not go looking for it; its record
   is in `state/nuc-fossil-ledger.jsonl` and `state/nuc-capture-r484`.
2. **Run `summary_fossil.py margins --capture <new> --strict` on every
   capture.** It now names the next orphan in advance. If a margin comes back
   `undecidable`, that is the sub-second gap between a journal line and an
   mtime and it needs `stat`, not a guess.
3. **Take a capture even if the round does nothing else with it** (round
   478's item 2, and this round is the evidence for it — 12 s, 2.3 MB, and it
   bought three days that no longer exist on the box).
4. **`fossil_ledger.py append` every round**, and never analyse from the
   newest capture alone: it currently sees 8 of 11 fire instants.
5. **Five of nine captures are unusable to the ledger** (no sysstat listing:
   r406/r430/r460/r466/r472 — the down rounds). r400 is usable only via a
   `DECLARED_NOW` entry because it predates the boot table. Neither is a
   defect; both are reported. If a future capture plan ever runs on a box
   that is up, it should not be possible to produce another one.
6. **Round 472's items 2, 3 and 4 are UNTOUCHED for a second round:**
   deconfound the lead-lag shoulder with per-round-window resampling;
   `lead_lag_profile` still has no null; `test_perturbation.py` has still
   never been mutation-tested while carrying every published number in this
   track. This round mutation-tested only its own new code, again.
7. **Round 436's items 4, 5 and 9 stand, untouched for a seventh round** —
   the `commit` channel vs the 9.25 GB weights load, `Consumed` coverage at
   4 of 26 units, the separability route.
8. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-eighth** round
   unchanged); the E3 A/B with its full six-gate table; and now
   `languages/whence/SECURITY_AUDIT_REPORT.md`, which is **committed** and
   outward-facing (§8b).
9. **`nproc` on this box is 1.** Plan every suite as serialised;
   `nuc/tests` is 415 s alone.
