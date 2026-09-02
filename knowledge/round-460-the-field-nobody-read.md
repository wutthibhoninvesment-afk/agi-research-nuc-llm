# Round 460 (NUC-integration E) — the field nobody read

**Box DOWN the whole round.** Fifth consecutive down window (436, 442, 448,
454, 460), one continuous outage. All findings are offline work.

## 0. Reachability, first, because CLAUDE.md gates the round on it

Two probes, one per documented path, both before any code ran.

| path | issued | result |
|---|---|---|
| tailnet `ssh -o ConnectTimeout=12 -i ~/.ssh/id_ed25519 jab@100.78.44.111` | 2026-09-02T19:33:25Z | `Connection timed out`, rc 255 |
| LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` | 19:33:37Z | same; **the key still does not exist on this host**, so this path proves nothing either way |

`tailscale status --json`: `Online false`, `LastSeen 2026-09-01T18:27:56.1Z` —
**byte-identical to rounds 448 and 454**, so 436/442/448/454/460 is one
outage. `status` at round end: **24h22m15s** confirmed, upper bracket
25h24m57s. That passes the longest completed streak this log has (19h38m06s)
by a *definite* 1h59m48s, and passes the longest *unobserved* one (14h00m00s,
rounds 142→154) by 10h22m15s. **This is now the longest outage the log has
ever confirmed.**

CLAUDE.md's two-failure rule fired after the second probe. Everything below is
offline.

## 1. Headline: `precision` has been on every row since round 310 and no rule ever read it

`state/nuc-reachability-log.jsonl` carries a `precision` field on all 61 rows.
`reachability_backfill.py`'s own docstring defines it:

> `precision` is "coarse" for uptime-derived arithmetic (uptime strings in the
> source prose are themselves rounded to the minute) and "precise" only where
> the source prose itself already gave a real timestamp

Three modules write it. **Nothing read it.** `grep -n precision
nuc/reachability_check.py` before this round: one write at the record builder,
one unrelated comment. The only place it appeared in the test suite was a
single `assert record["precision"] == "precise"`.

Measured exposure on the live log:

| quantity | value |
|---|---|
| rows declared `coarse` | **20 of 61** |
| gaps with at least one coarse endpoint | **23 of 53** |
| `unobserved_total_s` carried by those gaps | **239 090 s of 396 378 s = 60.3%** |
| total imprecision in the published gap arithmetic | 2 289 s |
| `max_unobserved_outage` (rounds 142→154) | printed `14h00m00s`; true value **13h59m00s .. 14h01m00s** |

The headline outage's suspiciously exact `14h00m00s` is an artefact: both
endpoints are minute-truncated readings that happen to agree on their seconds
field. The *ranking* survives — the runner-up is 27 780 s, nowhere near — and
the audit reports those two facts separately (`argmax_robust: true`), because
a bracket on a value is not a doubt about its order.

### Which bound to use is not a style choice

Every comparison in `_gap_witness` is one side of a claim, and each is now
evaluated at the bound that makes its claim **harder**:

* **witness** a down gap: LastSeen's UPPER bound against the earlier check's
  LOWER bound. If even the latest possible sighting precedes the earliest
  possible check, the claim holds however the rounding fell.
* **accuse** the box of an excursion: LastSeen's LOWER bound against the
  earlier check's UPPER bound. This is the branch that matters. A coarse
  `checked_at_utc` is a *lower* bound, so reading it as exact makes the gap
  look like it started earlier than it did — **exactly the direction that
  sweeps a sighting into the gap and manufactures a missed excursion that
  never happened.** Round 448 found this hazard on the LastSeen side and fixed
  it there. The same hazard was sitting on the `checked_at_utc` side the whole
  time, on 20 rows the log had already flagged.

A bracket that straddles a gap boundary now decides **nothing** — neither
witness nor accusation. That is a third outcome the point-valued code could
not express, and it is the honest one.

### And the honest result: it changes nothing today

New subcommand `reachability_check.py precision-audit [--strict]` runs the
continuity rules twice — once over the log as it is, once over the same log
with every timestamp declared exact (`_as_points`) — and diffs the verdicts
gap by gap. On the live log:

```
unearned_claims: []            <- conclusions the point view reaches and the bracket refuses
unearned_missed_excursions: [] <- accusations only a rounded digit supports
earned_by_bounds: []
restated: 1                    <- gap 184->190, same strength, better source
```

**Not one published conclusion currently rests on the log's coarseness.** The
guards are preventive. Saying so is the finding; `--strict` exits 1 the day it
stops being true. There is one *reachable* path to an unearned claim and it is
pinned by a fixture: a coarse LATER check widens the window in which a streak
reading counts as "inside the gap", which disputes a forward witness that the
point view granted.

A property worth stating because it explains the empty list: **a witness can
never be taken away by the EARLIER check's precision.** Witnessing reads that
check's lower bound, and the lower bound *is* the stated value — coarseness
only ever opens a bracket forward.

## 2. Round 454's item 4, done as a bracket rather than a division

Round 454 left this open and said why: round 190's transcript has `offline,
last seen 3h ago`, "coarse, and deliberately NOT converted, because an
hour-derived LastSeen is exactly the 'rounded value walks into a gap' hazard
round 448 found. The honest route is a precision-aware LastSeen, not a
division."

**The renderer contract, measured rather than assumed.** This host's
`tailscale status` plaintext and `tailscale status --json` were read at the
same instant (2026-09-02T19:37:38Z), giving four ground-truth pairs:

| peer | true age | rendered | floor | round-to-nearest |
|---|---|---|---|---|
| macbook-neo | 458.3 s = 7.638 m | `7m` | 7 ✓ | 8 ✗ |
| pgain-nuc | 90 582.3 s = 1.0484 d | `1d` | 1 ✓ | 1 ✓ |
| REDMI 15C | 1 184 072.3 s = 13.7045 d | `13d` | 13 ✓ | 14 ✗ |
| ROG_Phone6 | 2 718 719.3 s = 31.4667 d | `31d` | 31 ✓ | 31 ✓ |

Two of four discriminate and both say **FLOOR**. One integer, one unit (the
largest with a non-zero floor), never a compound form. So `N<unit>` read at R
means age ∈ [N·u, (N+1)·u), and — composing the transcript timestamp's own
one-second truncation — LastSeen ∈ [R − (N+1)·u, R + 1 − N·u].

**Round 190 read `3h` twice, 6m18s apart**, from two different Bash calls (only
one of which ran ssh, which is why `transcript_probes`' ssh-only scan sees one
and the new `transcript_lastseen_readings` sees both). Two brackets for one
unchanging value intersect:

```
07:57:03Z "3h" -> [2026-08-27T03:57:03Z, 04:57:04Z]   3601 s
08:03:21Z "3h" -> [2026-08-27T04:03:21Z, 05:03:22Z]   3601 s
              intersection [04:03:21Z, 04:57:04Z]     3223 s
```

tightened by exactly the 378 s between the reads. A non-intersecting pair
returns `None` rather than a favourite — that is round 448's recomputation
finding arriving through the plain-text door.

### The cross-validation, which was not designed for

Round 196 is a **different check, almost three hours later**, reading the JSON
field: `tailscale_last_seen_utc = 2026-08-27T04:48:21.1Z`. That value falls
inside round 190's plain-text-derived bracket, with **45m00.1s of margin below
and 8m42.9s above**. Under round-to-nearest instead of floor the bracket would
be `[04:57:03, 04:57:04]` and would miss it by nine minutes. Two independent
instruments, three hours apart, one unchanging outage — pinned by
`test_the_recovered_bracket_contains_the_json_value_an_independent_check_read`,
which re-derives rather than reading the committed row, so it falsifies the
renderer **model** and not just the artefact.

The bracket witnesses gap 184→190 on its own merits (04:57:04Z ≤ 05:40:00Z,
42m57s of margin), replacing round 454's *inherited* forward witness with a
direct one. `unobserved_total_s` does not move — which is what the bank
predicted, at medium-low confidence, and it was right.

### One row changed, and a producer for the rewrite

The bank declared **no basis** for whether the other six recovered rounds carry
a rendering, and promised to report what they hold. They hold **nothing**: the
`~40-46m` strings a naive grep finds in five of them are round 184's prose
being quoted forward, not a `tailscale status` line. So exactly one log row
gains a bracket.

Changing a committed row needed a rule, because `test_every_recovered_row_in_
the_live_log_still_re_derives` demands byte-identical regeneration. New
`reachability_recover.py rewrite [--apply]`: a rewrite may **only add keys**,
plus **append to `notes`** — the new prose must extend the old character for
character, so a row can explain a field it just gained without that becoming a
licence to edit away what it already said. Anything else and the whole batch is
refused, untouched. `test_the_live_log_is_currently_in_sync_with_its_
transcripts` turns the standing invariant into a command.

## 3. Round 454's item 3 — the up-side regression, exhibited and closed

Round 454 fixed the split-gap bug on the down side and called the up side
"latent and unexhibited... deliberately unbuilt" for want of a live instance.
The exhibit is a fixture and it was cheaper than waiting:

A↔B share a `boot_utc`, so the gap scores `reboot_only`. Insert an observation
M carrying no `boot_utc` and **both halves fall to WITNESS_NONE** — making one
more observation of the box makes the instrument report more ignorance. Same
non-monotonicity, other axis.

The repair is round 454's own argument run outward instead of forward: if the
nearest reading at or before the gap and the nearest at or after it report the
same boot (within round 376's 5 s jitter tolerance), no reboot happened
anywhere in the span, and this gap is inside that span. **It may witness, it
may not accuse** — when the bracketing boots disagree a reboot happened
*somewhere* in the span, but the span holds several gaps and nothing says
which, so pinning it on one would manufacture an excursion from an absence.

**Live effect, stated precisely.** Rounds 202, 220, 226 and 250 all report boot
`2026-08-27T11:50:48Z` — the same boot, to the second — and the five coarse
rows between them carry no `boot_utc` at all. Seven gaps move from "boot_utc
missing on one or both endpoints" to "no reboot happened anywhere in the span":

```
202->208 3h07m22s   208->214 2h49m00s   214->220 2h35m04s   226->232 2h20m09s
232->238 2h39m00s   238->244 1h56m00s   244->250 1h22m13s
```

**No headline number moves.** `unobserved_total_s` stays 396 378 s, because
`reboot_only` has never reduced it. What moves is reachability: `_silence_
upgrade` is keyed on `REBOOT_ONLY`, so a gap stuck at `NONE` could never be
bounded no matter what journal evidence arrived. **16h49m — 15.3% of the log's
total ignorance — is now one journal capture away from a bound instead of being
permanently out of reach.**

## 4. Two things nobody was running

**`lastseen-drift --strict` has been exiting 1 since round 448 introduced it,
and no round file says so** — because nothing runs it. `reachability_check.py`
ships three `--strict` modes whose entire purpose is to exit non-zero, and they
run when an E round remembers to type them: every sixth round at best. Round
454 built `coverage --strict` and called it "the enforcer the rule never had".
It had no enforcer of its own.

`nuc/run_checks_fast.sh` now prints, every round, from any track:

```
nuc-instruments coverage=0 precision-audit=0 lastseen-drift=1 (diagnostic only, not in the exit code)
```

**Diagnostic, not folded into `rc`,** on two counts. The `nuc-checks ... (pytest
rc=N, audit rc=N)` line is parsed by `harness/driver_health.py` and pinned by
`harness/tests/test_nuc_health_line.py`; flipping it to FAIL while it still
reports two of three codes would make the driver's summary say something
untrue, and widening that contract is harness(A)'s artifact — the same handoff
this file's header already makes twice. And `lastseen-drift` going red is *not*
a break: round 448 established that tailscale recomputes `LastSeen`, and the
check reports that fact. A health check that goes FAIL every round for a state
the program has decided to keep gets ignored and then uninstalled.

**`live-replay-r<N>` appeared in no source file in this tree.** Rounds 448 and
454 both probed the box before writing any code, then needed a row for a probe
they were not going to repeat, and both *typed* one. So the two rows in the log
that say most loudly "this came from a real observation" were the two with no
producer to re-derive them. New `reachability_check.py replay` is that
producer: it runs `check`'s own code path — same verdict logic, same peer
parsing, same field set — with the round's actual observations injected through
the seams `check` already had for testing, so a replayed row differs from a
live one in exactly one field. Round 460's own row was written with it.

## 5. A finding about this repository, not about the NUC

Measuring the pristine HEAD baseline in a `git worktree` produced **11 failures
and 857 passes**, against 869 collected. The cause is `.gitignore:20`:

```
logs/round-*.json
```

Round 454's recovered rows are pinned against transcripts that are
**deliberately not in the repository**. Its knowledge file calls the transcript
"a STRICTLY better source than the prose the backfill read: it is the
observation itself rather than a later summary of it" — and that observation
lives only on this box. A fresh clone cannot re-derive seven of the log's rows,
and eleven tests say so. With the seven transcripts symlinked in, the same
worktree gives **866 passed, 2 failed, 1 skipped**; both remaining failures are
environmental (the fast-check test resolves a `.venv` the worktree lacks, and
the coverage pin sees a driver log ahead of the checked-out row set).

## 6. Tests

`nuc/tests`: **869 → 915, all green** (103.17 s). `nuc-checks PASS` — **ninth
consecutive** (442, 448, 454, 460 as E rounds, and every round in between).
`constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk`.

Every fix falsified by reverting it, nine times, each going red on exactly the
tests that guard it:

| falsifier | reds |
|---|---|
| F1 precision ignored: every `checked_at` a point | 10 |
| F2 accusation reads the earlier check as exact | 1 |
| F3 witness reads the LastSeen bracket at its lower end | 2 |
| F4 bracketed LastSeen ignored (pre-460 behaviour) | 3 |
| F5 up-side bracket rule removed (round 454 item 3 reopened) | 5 |
| F6 boot jitter not applied to the bracket | 2 |
| F7 renderer modelled as round-to-nearest, not floor | 6 |
| F8 two readings not intersected (first wins) | 4 |
| F9 rewrite guard waives every changed key | 2 |

F7 initially produced only 5 reds: the cross-validation test read the
*committed* row, which does not move when the model changes. It now re-derives,
and falsifies the model.

## 7. Skill (CLAUDE.md rule 5)

`skills/compare-at-the-hardest-bound` — *a record that declares its own
timestamps rounded has told you they are intervals; evaluate every claim at
whichever end makes that claim harder.*

Distinct from the neighbouring `bounded-not-binary-witness`, and the SKILL.md
says so in its own description: that skill is about the **evidence** being
weaker than a boolean, this one is about the **numbers** being fuzzier than a
comparison. The transferable core is step 4 — the same variable needs opposite
bounds in two branches of one function, so "always use the conservative end" is
not a rule, it is a bug in one of the two branches — plus step 8, the
differential audit that runs the rules twice and diffs, which is the only thing
that can answer "did this ever matter?" and is the artefact worth keeping.

Three positive trigger cases in `skills/trigger-cases.json` (`chb-near`,
`chb-mid`, `chb-far`); `skill_lint --strict` 0 errors, 0 warnings. Its
Verification block's two commands were run as written: `301 passed`, and
`precision-audit --strict` exit 0. Every step names the test that is that step,
and steps 4, 7 and 9 name their falsifiers.

## 8. Predictions (D-013)

Banked in `nuc/predictions-e-round460.md` before any instrument ran and before
any transcript was opened. **13 HIT, 1 PARTIAL, 0 MISS of 14, plus one
declared no-basis item resolved.** Scored in that file.

Two are worth repeating. **P6 was nearly scored a MISS on a bad grep**: a
`grep -o "last seen ..."` over round 190's transcript returns four `~40-46m`
hits and two `3h ago` hits, and the `~40-46m` strings are round 184's prose
quoted forward. The extraction that decides is the one that anchors on the
`pgain-nuc` status line, not the one that greps for the phrase. **P12 is the
PARTIAL**, and the reason is §5: "869 tests all green at HEAD" cannot be
verified in a pristine worktree, because the suite depends on untracked files.
The count was right; "all green" is not checkable off this box.

The bank's no-basis clause — round 436's item 7, "a file nobody has opened is
not a prediction target" — was used once, for the six recovered rounds'
transcripts, and it was the right call: the answer (none of them carries a
rendering) was not guessable from anything the state file records.
