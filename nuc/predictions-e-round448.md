# Round 448 (NUC-integration E) — PREDICTIONS, banked before measuring

House rule D-013. Written 2026-09-02, BEFORE the first `ssh`, BEFORE
`capture_manifest.py retention` was run, and BEFORE `nuc/capture_manifest.py`'s
`capture_plan` function body was opened.

## Basis labelling — this round's experiment

Round 436 scored 21 HIT / 2 PARTIAL / 7 MISS / 6 unevaluable and found ONE
mechanism behind five of the seven misses: *"Everything predicted from a banked
COMMAND hit; everything predicted from a banked SENTENCE missed."* That is a
rule about prediction basis, and no round has tested it since. So every
prediction below carries an explicit basis tag, and §Scoring reports the hit
rate **per class**:

- `[CMD]` — derived from output I have already run or read verbatim this round.
- `[SENT]` — derived from a previous round's PROSE about an artefact I have
  not opened. Round 436 predicts these miss.
- `[MODEL]` — derived from reading the implementing source, but not from
  running it.
- `[NONE]` — no basis; the honest line per `skills/prediction-banking/SKILL.md`
  step 9. I will report what it holds rather than bet, and it scores
  `no-basis-reported`.

## What is already MEASURED (stated, not predicted)

- `state/nuc-capture-r424/collector-evidence.txt` `### CAPTURED_AT` is
  **2026-09-01T08:18:35Z**; `### SUMMARY_TIMER_NEXT` is **Wed 2026-09-02
  00:07:00 UTC** (i.e. "15h" away *as of the capture*, and now in the PAST);
  `### SYSSTAT_CONF` has `HISTORY=7`, `COMPRESSAFTER=10`.
- The first seven `### SYSSTAT_LS` lines read: `sa01` Sep 1 08:10, `sa23`
  Aug 23 23:50, `sa24` Aug 24 23:50, `sa25` Aug 25 23:50, `sa26` Aug 26 23:50,
  `sa27` Aug 27 23:50, `sa28` Aug 28 23:50. I have NOT read past `sa28`, so I
  do not know the `sar*` half of the listing or whether `sa29/sa30/sa31` exist.
- `### FILES_DUE_FOR_DELETION_NOW` names `sa23 mtime=2026-08-23` and
  `sar23 mtime=2026-08-24` — so at least one `sar*` file is in the listing.
- `### PROC_VMSTAT_RECLAIM_FIELDS` shows `pgsteal_kswapd 0`,
  `pgsteal_direct 0`, `pgscan_kswapd 0`, `pgscan_direct 0` — every reclaim
  counter zero at capture time.
- `nuc-health-check` reads **PASS** for rounds 442-447, six consecutive; FAIL
  for every round 410-441. Round 442's fix holds.
- `retention_forecast`'s source (read this round): `find_mtime_matches` is
  `int(age_s // 86400) > days`; `--strict` returns 1 iff
  `n_deleted_at_next_run` is non-zero; `earliest_loss_utc` is the min over
  SPARED files of `deleted_at_utc`, which is `_next_sweep_at_or_after`.

## A. Reachability

- **A1** `[NONE]` Whether the box is up. Rounds 436 and 442 both found it
  DOWN; round 430 found it up. Two down windows is not a rate and I have no
  basis for a third. I will probe twice at most (CLAUDE.md) and report.
- **A2** `[CMD]` If a probe is attempted, the LAN path fails with
  `Warning: Identity file /home/pgain/.ssh/id_ed25519_nuc not accessible: No
  such file or directory` — the key still does not exist on this host, so the
  tailnet path is the only real probe. (Round 442 measured this; I re-derive.)

## B. `retention --strict` on the banked capture (the standing item-1 action)

Run as `--capture state/nuc-capture-r424 --now 2026-09-01T08:18:35Z
--next-run 2026-09-02T00:07:00Z --history 7 --strict`.

- **B1** `[MODEL]` `sa23` is doomed: age at 2026-09-02T00:07Z from
  2026-08-23T23:50Z is 9.01 d, `int(9.01) = 9 > 7`. Likewise `sa24` (8.01 d →
  8 > 7). `sa25` is 7.01 d → `int(7.01) = 7`, NOT `> 7`, so `sa25` is SPARED.
- **B2** `[MODEL]` Exit code **1** (`--strict` with a non-empty doomed set).
- **B3** `[SENT]` The doomed set is exactly `{sa23, sa24, sar23, sar24}`, four
  files — round 430's prediction A2 recorded as HIT. Prose-derived: I have not
  seen `sar24` in the listing.
- **B4** `[MODEL]` `earliest_loss_utc` = **2026-09-03T00:07:00Z** and
  `next_files_lost` includes `sa25`. (`sa25` becomes sweepable at
  2026-08-25T23:50 + 8 d = 2026-09-02T23:50Z, and the next fire at or after
  that is 2026-09-03T00:07Z.)
- **B5** `[SENT]` Round 434's carried pair — deadline `2026-09-10T00:07:00Z`,
  next loss `2026-09-03T00:07:00Z` — re-derives EXACTLY, both halves. The
  10th is prose I have not re-derived; if the run disagrees I will say the run
  is right.
- **B6** `[MODEL]` **The forecast is now retrospective and the tool cannot
  say so.** `--next-run 2026-09-02T00:07:00Z` is in the past as of this round.
  Nothing in `retention_forecast` compares `next_run_utc` against a "now", so
  it will report four files as *going to be* deleted by a sweep that either
  already ran (and deleted them) or did not run (box down). I predict the JSON
  contains no field naming this, and no warning is printed.

## C. `capture_plan` step 3b — round 436's item 2, four claimed defects

All four are `[SENT]`: round 436's prose about a function I have not opened.
Round 436's own rule says these should MISS. Banked anyway, precisely to test
that rule.

- **C1** The step-3b comment says "the USER manager" while the command it
  introduces is `journalctl _SYSTEMD_USER_UNIT=qwen36-colibri.service`.
- **C2** The plan emits **no `###` header** for the journal-user file, which
  is how `journal-user-full.txt` ended up holding an unlabelled lead section
  plus a `### USER_MANAGER`-labelled copy of a subset of it.
- **C3** The plan writes BOTH the wide user-manager journal and the narrow
  engine-unit journal into ONE file.
- **C4** The plan does not capture `_SYSTEMD_USER_UNIT=qwen36-toolproxy.service`
  at all.

## D. Suites, after whatever this round changes

- **D1** `[CMD]` `python3 -m pytest nuc/tests -q` at HEAD, before any edit, is
  **802 passed** (round 442's final number; nothing since round 442 has been
  an E round, and 443-447 are A/B/C/D tracks).
- **D2** `[MODEL]` After this round's edits the count is 802 + N with 0
  failures, where N is the number of tests I add; I will state N before
  running.
- **D3** `[CMD]` `bash nuc/run_checks_fast.sh` exits 0 and prints
  `nuc-checks PASS`, on an `nproc`=1 box, in 120-260 s. Round 442 measured
  150.5 s at 794 tests; 802 tests plus contention widens the band upward, and
  I am deliberately NOT betting a point estimate on a wall time this box
  varies 3x on under load (round 434's finding).
- **D4** `[NONE]` Whether the corpus/skills checks stay green. I have not run
  them and this round is not a skills round; I will report the number.

## E. The `%vmeff` residual (carried since round 430)

- **E1** `[CMD]` It is STILL vacuous and will stay vacuous on this capture:
  the capture's own `pgsteal_kswapd` is 0, and round 436's item 3 says to
  check that first. I predict I close it as a WRITTEN DECISION this round
  rather than leaving it as a fourth vacuous carry, and that closing it
  requires no new measurement — only the sentence.
