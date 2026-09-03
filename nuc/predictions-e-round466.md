# Round 466 (NUC-integration E) — predictions, banked BEFORE any measurement

Written 2026-09-03T01:0xZ, after the two reachability probes (CLAUDE.md gates
the round on those) and after READING source, but before running any
instrument over any capture and before opening
`state/nuc-capture-r424/journal-pid1-full.txt` for anything but the four
histogram commands already recorded in §0 below.

## §0 What was already measured before this file existed, and why that is allowed

The reachability probes: CLAUDE.md's first Track-E bullet orders them first and
its two-failure rule ends the round's live work. Both failed, so the round is
offline; there is nothing to predict about a box that cannot be contacted.

Three exploratory reads over the banked capture, recorded here so no prediction
below can be secretly retro-fitted to them:

* `wc -l journal-pid1-full.txt` -> 9189
* a verb histogram -> `Deactivated 3057, Started 1697, Starting 1664,
  Finished 1580, Stopped 262, Reached target 144, Consumed 140, Stopping 95,
  Removed slice 15, Created slice 13, OOM 4, Scheduled restart 3, Failed 2`
* the OOM/restart/Failed lines themselves (8 lines, quoted in the round file)
* a `Consumed`-line unit histogram, which showed `session-NNN.scope` entries

Everything below is predicted against those and nothing else.

## The target: round 436's item 6, untouched for five E rounds

Round 436 §6 published, over the pooled 10-day swap window at
`LEDGER_MIN_BYTES = 4825665`:

> K = 52 costly buckets holding 31.53 GiB. PID-1 `Starting` names 19 (8.42 GiB);
> adding the six `Started`-only units names **the same 19**; engine events alone
> name 18 (16.78 GiB); both together at shift 0 name 33 (23.65 GiB).
> **14 buckets, 4.25 GiB, remain unnamed by anything**, largest
> `2026-08-23 21:20:02` at 2.34 GiB.

and asked two questions, both offline, both still open:

* **(a)** the fire population is `.service`-only, and `session-*.scope` records
  "were skipped by this round's `.service`-only default";
* **(b)** the largest unnamed bucket is the run-up to an OOM episode — how many
  of the *other 13* sit inside an OOM or restart window before any of them is
  called unexplained?

---

## Predictions

**P1 — the two published baselines re-derive unchanged at HEAD.**
`K = 52` costly buckets / 31.53 GiB, and `19 / 52` named by PID-1 `Starting`.
*Confidence: high.* Round 435's item 10 and round 460's own experience say
re-derive rather than quote, and this is that re-derivation; but nothing in
five rounds has touched `cost_ledger` or the swap threshold.

**P2 — `parse_unit_starts` and `parse_unit_starts_complete` both refuse every
non-`.service` unit, and the refusal is a literal `\.service` in the regex, not
a filter downstream.** Two regexes carry it: the one at `parse_unit_starts` and
`_UNIT_VERB`. *Confidence: high — I read both.* This one is banked because it is
the PREMISE of everything after it, so if it is wrong the round stops.

**P3 — `.scope` units are `Started`-only: no `.scope` in this journal ever
emits a `Starting` line.** A scope is registered by an already-running process,
so it has no startup phase for systemd to announce, which is exactly the
mechanism round 436 wrote down for `Type=simple` services. *Confidence:
medium-high.* This matters structurally: if it holds, round 436's two-pass
`Starting`-then-`Started`-only-where-never machinery admits scopes with **no
new rule at all** — only a wider unit-kind alternation. If it fails, widening
needs a genuinely new decision about double-counting and I should say so rather
than paper over it.

**P4 — widening the population to `.scope` names AT LEAST ONE of the 14
buckets, and strictly fewer than all 14.** *Confidence: medium for "at least
one"; medium-high for "not all".* Basis for the floor: round 436's own §5 table
already names `tmux-spawn-….scope` against the 21:30:03 bucket (2.94 GiB) via
`oom_cost_context`, so at least one scope demonstrably sits next to a large
bucket — though 21:30:03 is a NAMED bucket, not one of the 14, so this is
suggestive and not decisive. Basis for the ceiling: 14 buckets over 10 days is
a lot of coincidences to buy with one unit kind.

**P5 — the largest unnamed bucket, `2026-08-23 21:20:02` (2.34 GiB), is STILL
unnamed after the widening.** It is a *run-up*: the OOM fires at 21:28:09Z, and
the scope that the OOM context names was already alive. A cause that precedes
its own scope's creation cannot be named by that scope's start.
*Confidence: medium.*

**P6 — of the other 13, FEWER THAN HALF (≤6) sit inside an OOM or restart
window,** taking "window" as the same half-hour `oom_cost_context` already
uses. *Confidence: LOW — this is the prediction I most expect to lose.* Basis:
there are only 3 OOM episodes, 2 scheduled-restart instants and 1 `Failed` in
ten days, so at most 6 windows exist and they cannot cover 13 buckets unless
they cluster hard. But I have not looked at where the 14 buckets fall, so the
clustering could go either way.

**P7 — the `sysstat-collect` exclusion argument applies to `session-*.scope`
and the tree contains no writing that notices.** `LEDGER_EXCLUDE_UNITS`
excludes the instrument because it "is present in every costly bucket by
construction". An ssh login is also an instrument on this box — this program
ssh'd in to take every capture — and a session scope is the systemd record of
one. *Confidence: high for "the tree says nothing"; the interesting part is
whether it is TRUE here, which P8 asks.*

**P8 — at least one `session-*.scope` start in this journal coincides with a
row in `state/nuc-reachability-log.jsonl`,** i.e. with one of THIS PROGRAM's
own probes, within 120 s. *Confidence: medium-high.* Every reachability probe
that succeeded is an ssh login and every ssh login opens a session scope; the
log covers the capture window. If this holds, then a costly bucket "named" by a
session scope may be named by the observer, and the honest report separates
program-caused sessions from the box's own.

**P9 — the count of session scopes attributable to this program is a MINORITY
of all session scopes in the journal.** *Confidence: LOW.* The reachability log
records one row per E round (every sixth round, so ~1/day at the observed pace)
against ten days of a box a human operator also uses. But E rounds run several
ssh calls each and the log records one row per round, not one per login, so
this could invert.

**P10 — NO DECLARED BASIS: how many distinct `session-*.scope` units appear in
`journal-pid1-full.txt`, and how many of them fall in a costly bucket.** I have
seen a `Consumed`-line histogram that shows session scopes exist and that some
appear twice, and nothing else. I will not guess a number. Round 436's item 7
rule: a file nobody has opened for this purpose is not a prediction target — I
will report what it holds.

**P11 — NO DECLARED BASIS: whether widening to `.socket`/`.timer`/`.target`/
`.mount` names any of the 14.** I have no reading at all on non-scope kinds.
Reported, not guessed. (Stated separately from P4 on purpose: P4 is a scope
claim and must not be scored on a socket's behalf.)

**P12 — the tests: `nuc/tests` collects 915 at HEAD and the pristine-worktree
baseline (transcripts symlinked in) is NOT all-green.** Round 460 measured
`866 passed / 2 failed / 1 skipped` with two environmental failures it named
(a `.venv` the worktree lacks; a coverage pin seeing a driver log ahead of the
checked-out rows). *Confidence: high on 915; medium on the failure count,
because the driver log has advanced by a round since.* Banked this way
deliberately: round 460's P12 was its only non-HIT precisely because it
predicted "all green" without measuring, so this round measured the baseline
FIRST, in a worktree, before editing anything — and this prediction is being
scored against a run that was already launched when this file was written.
The number is not yet known to me; the run's output file is empty.

**P13 — `coverage --strict` exits 0 and `precision-audit --strict` exits 0;
`lastseen-drift --strict` exits 1.** Round 460's item 1 orders these first.
*Confidence: high* — 460 measured all three and nothing since has touched the
log except this round's own row, which is not yet written.

**P14 — the round-466 reachability row extends one continuous outage; the
confirmed streak passes 30 h and sets a new record.** `LastSeen` read
`2026-09-01T18:27:56.1Z` at 01:00:10Z today, byte-identical to rounds 448, 454
and 460. *Confidence: high — this is arithmetic on two values already read.*

**P15 — `unobserved_total_s` does not move,** because a down-to-down gap
contributes nothing to it (round 460's P14 measured 0.0 across all four down
streaks). *Confidence: high.*

---

# SCORING (written after all measurements, round 466)

**11 HIT, 2 PARTIAL, 1 MISS of 14, plus two declared no-basis items resolved.**

| # | prediction | result | measured |
|---|---|---|---|
| P1 | K=52 / 31.53 GiB and 19/52 named re-derive unchanged | **HIT** | byte-exact on both, and on 8.42 GiB / 26.7 % too |
| P2 | both parsers refuse non-`.service` via a literal in the regex | **HIT** | `parse_unit_starts` and `_UNIT_VERB`, both pinned to `\.service` |
| P3 | no `.scope` in this journal emits `Starting` | **HIT** | **0** `Starting`, **1401** `Started`, 696 distinct units — and the same holds for `.timer` (0/84) and `.path` (0/6) |
| P4 | widening names ≥1 of the 14 and <14 | **HIT** | **7 of 14** |
| P5 | `2026-08-23 21:20:02` (2.34 GiB) stays unnamed | **MISS** | it is scope-named. The record's single largest unexplained bucket is explained by an ssh login |
| P6 | ≤6 of the other 13 sit in an OOM/restart window (banked at LOW) | **HIT** | **0 of 13**, at ±30 min and ±60 min both |
| P7 | the tree contains no writing noticing the exclusion argument applies to scopes | **HIT** | `git grep 'session-\|session_scope' HEAD -- 'nuc/*.py' 'nuc/tests/*.py'` returns **nothing** at the pre-round commit. (A bare `session` grep is NOT the check and I nearly reported it as one: it returns 10 hits, all of them vendored colibri/`kv_reuse` code about chat sessions. Same shape as round 460's P6 — the phrase matches things that are not the subject.) `LEDGER_EXCLUDE_UNITS` names only `sysstat-collect`, and its comment argues from *writes the bucket*, never from *is the observer* |
| P8 | ≥1 session scope coincides with a reachability row within 120 s | **HIT** | **33 of 35** successful probes, 18 of them within ±1 s |
| P9 | this program's sessions are a MINORITY of all sessions (banked at LOW) | **PARTIAL** | 719/1401 = **51.3 %** within ±45 min of a probe row — a bare majority, so the claim as worded is wrong. But the window is one row per ROUND against dozens of logins per round, so 51.3 % is a floor and the direction of the error is knowable. Scored PARTIAL, not HIT: I picked the side and the side was wrong |
| P10 | *no basis:* how many distinct session scopes, how many in a costly bucket | **RESOLVED** | **696 distinct units, 1401 starts** (numbers reused across reboots); they land in **29 of the 52** costly buckets |
| P11 | *no basis:* whether `.socket`/`.timer`/`.path`/`.target`/`.mount` name any of the 14 | **RESOLVED** | **none.** `service,scope` names 44/52; adding all five other kinds still names 44/52 and the same 29.65 GiB. 102 extra fires, zero extra buckets |
| P12 | 915 collected; pristine worktree NOT all green; ~2 environmental failures | **HIT** | **912 passed, 2 failed, 1 skipped of 915**, measured in a worktree BEFORE the tree was touched. Both failures are the two round 460 named, and both are the worktree lacking gitignored files (`logs/driver.log`, `.venv`) |
| P13 | `coverage`=0, `precision-audit`=0, `lastseen-drift`=1 | **HIT** | exactly |
| P14 | one continuous outage; confirmed streak passes 30 h and sets a record | **PARTIAL** | one outage ✓ (`LastSeen` byte-identical for the 4th round); record ✓ by a **definite 10h12m30s**. But confirmed elapsed is **29h50m36s** — **9m24s short of 30 h**. The 30 h figure is only reachable on the upper bracket (30h53m18s), and I wrote "confirmed" |
| P15 | `unobserved_total_s` does not move | **HIT** | 396 378 s, unchanged |

## What the bank got right about itself, and what it did not

**The two LOW-confidence flags were the two that carried real information, and
they split.** P6 was flagged "the prediction I most expect to lose" and came in
far *stronger* than predicted (0, not ≤6) — the OOM hypothesis for the residual
is dead rather than merely weak. P9 was flagged LOW and **lost**, and lost in
the way a flagged prediction should: I said minority, measured 51.3 %, and the
flag is why the round went and measured the burst structure and the session
lifetimes instead of asserting it. Flagging weak evidence did not make either
prediction right; it made the round willing to look.

**P5 is the honest MISS and it is the good kind.** I reasoned that a *run-up*
bucket cannot be named by the scope of a process that was already alive, and
that reasoning is sound — it is just not what the data does. `21:20:02` is
named because *another* login happened inside it, in the 60-session burst
running 21:02:37→22:33:27. The prediction failed because I modelled one session
where the record holds sixty. **A rate-shaped population cannot be predicted
against as though it were a single event.**

**P14 is a PARTIAL for a word, and the word matters.** "The confirmed streak
passes 30 h" was written from arithmetic on two timestamps I had already read
(01:00:10Z minus 18:27:56.1Z ≈ 30 h 32 m) — but that difference is the *upper*
bracket, computed from `LastSeen`, and the *confirmed* streak runs from round
436's own check at 19:30:39Z, which is later. I mixed the two bounds inside one
sentence, which is precisely the failure mode round 460 built
`precision-audit` to catch. The instrument was green; the prose was not. **A
round that ships a bracket-discipline instrument should read its own bracket
before quoting a number from it.**

**The no-basis clause earned its place twice.** P10 and P11 were both declared
rather than guessed, and P11 is the one worth noting: guessing there would
almost certainly have produced "the other kinds add a little", and the true
answer is that 102 timer/socket/path fires add **exactly zero** buckets and
zero bytes. A wrong small number would have looked like a result. "I have no
basis and will report what it holds" reported a clean zero.
