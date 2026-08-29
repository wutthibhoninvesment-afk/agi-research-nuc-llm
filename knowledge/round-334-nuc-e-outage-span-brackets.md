# Round 334 — NUC-integration (E) — outage-span brackets: every duration this track ever quoted was a lower bound

## Context

The box has now been down for SEVEN consecutive E-rounds (298, 304, 310,
316, 322, 328, 334) — one continuous outage, and by a wide margin the
longest this track has measured. Rounds 310/322/328 each used a down
window to upgrade the measurement apparatus (durable JSONL log →
record-comparison → human-readable durations). This round found the
apparatus was answering the record question with a number that is
**structurally an underestimate**, and closed that.

## Pre-flight

- `ps -eo pid,ppid,etime,cmd` showed exactly two relevant processes: the
  long-lived `bash run_driver.sh` and this round's own `claude -p` child.
  No concurrent research round
  ([[feedback_check_for_concurrent_rounds]]).
- `git status --porcelain` showed exactly the 5 paths in
  `state/known-standing-dirty-paths.json`; `git diff --cached --stat` was
  empty ([[feedback_check_cached_diff_before_commit]]).

## Live box check: still UNREACHABLE, same outage, now past 10h50m

Two live probes, round start and round end:

| | `checked_at_utc` | ssh | tailscale `LastSeen` |
|---|---|---|---|
| start | `2026-08-29T12:47:54Z` | rc 255, "Connection timed out" | `2026-08-29T02:10:00.1Z` |
| end | `2026-08-29T13:02:44Z` | rc 255, "Connection timed out" | `2026-08-29T02:10:00.1Z` |

`LastSeen` is still **byte-identical** to every check since round 298 — a
peer's `LastSeen` does not advance while it is offline, so this is
provably the same continuous outage, not a new one. Two records appended
to `state/nuc-reachability-log.jsonl` (verified: `git diff` shows +2 new
lines, plus the one migrated line described in §3).

## 1. The gap: a lower bound reported as if it were the answer

Every span this module has ever produced —
`summarize_log`'s streak `start`/`end`, `_streak_span_seconds`,
`current_streak_duration`'s `elapsed_s`, and therefore round 322's
`exceeds_longest_completed` and round 328's `elapsed_human` — is measured
**check-to-check**. That is the span over which the box was *observed* to
hold a verdict. The real outage is strictly larger: the box fell over at
some unobserved instant between the last up check and the first down
check, and comes back at some unobserved instant between the last down
check and the first up check.

With this track's ~6-round (1-2 hour) check cadence, that unobserved
slack is **hours**, and nothing in the tool's output hinted at it.

Two concrete symptoms already sitting in the record before this round:

1. **The tool and this track's own prose disagreed by 3m06s and nobody
   reconciled it.** Round 310's knowledge file measured the current outage
   from tailscale's `LastSeen` (`2026-08-29T02:10:00.1Z`). Round 316's
   `status` subcommand — and every round since — measured it from the
   first down *check* (`2026-08-29T02:13:07Z`). Both are defensible; they
   are the two ends of a bracket, and the tool only ever printed one of
   them.
2. **The "record to beat" was understated by 34%.** Outage 1 (rounds
   184-196) has been quoted as `18880.0s` / `5h14m40s` in rounds 322, 328
   and `research-state.md`. Its bracket (below) puts the true span
   anywhere up to **7h02m26s**.

## 2. `streak_bounds()` — both ends of every streak, with named evidence

New in `nuc/reachability_check.py`, plus a `bounds` CLI subcommand
(`--verdict down` to filter). One entry per streak from
`summarize_log`'s own streak partition (shared via a new `_build_streaks`
helper — `summarize_log`'s public output shape is byte-identical to
before, it just no longer inlines the grouping loop):

```
confirmed_span_s      last_check - first_check      strict LOWER bound
                                                    (the pre-334 number,
                                                     SSH ground truth only)
max_possible_span_s   latest_possible_end
                        - earliest_possible_start   strict UPPER bound
start_uncertainty_s   first_check
                        - earliest_possible_start   ignorance, start side
end_uncertainty_s     latest_possible_end
                        - last_check                ignorance, end side
```

The two bounds are not guesses — each names the evidence it rests on, in
`earliest_possible_start_source` / `latest_possible_end_source`:

- **`tailscale_last_seen`** — a `LastSeen` recorded on a *down* record is
  the last instant the box was demonstrably alive, so the outage began
  after it. Strictly tighter than "the previous up check." Deliberately
  *not* applied to up streaks: on an up record the same field means
  "seen alive **during** this streak," which bounds the start from the
  opposite direction, so reading it as a lower bound would be simply
  wrong (`test_streak_bounds_ignores_last_seen_on_an_up_streak`).
- **`boot_utc`** (new field, §3) — a boot time is evidence the box was up
  at that instant, so it bounds **both** sides of the transition it
  straddles: it closes the preceding outage (upper bound on its end) and
  opens the following up streak (lower bound on its start). Only the
  relevant record's own boot time is read — a boot recorded two checks
  later, or mid-streak, would be a different or unresolvable transition
  (`test_streak_bounds_boot_utc_only_read_off_the_next_streaks_first_record`,
  `test_streak_bounds_mid_streak_boot_utc_is_not_read`).
- **`previous_check`** — the fallback: the preceding streak's last check.
- **`None`** — no evidence at all (the streak opens the log, or is its
  still-open last streak). `max_possible_span_s` is then `None` too:
  an unbounded side means there is genuinely no upper bound, and
  substituting "now" would silently convert an open interval into a claim.

Contradictory evidence is **dropped, never clamped** — a `LastSeen` after
the first down check, or a `boot_utc` at/before the last down check,
implies more transitions than one bracket can represent, so the tool falls
back to the weaker bound rather than emitting a negative uncertainty.

### The whole real log, bracketed

| streak | confirmed | max possible | start bound from | end bound from |
|---|---|---|---|---|
| up 124-178 | 35h03m00s | *(unbounded)* | — | next_check (2h26m00s) |
| **down 184-196** | **5h14m40s** | **7h02m26s** | tailscale_last_seen (51m38s) | boot_utc (56m08s) |
| up 202-286 | 32h23m22s | 38h22m19s | boot_utc (1h27m38s) | next_check (4h31m19s) |
| **down 298-334** | **10h49m37s** | *(ongoing)* | tailscale_last_seen (3m06s) | — |

The current outage's start is pinned to within **3m06s** — the tightest
transition bound in the log, because round 298 happened to check within
minutes of the box going quiet. Outage 1's is pinned to within 51m38s.
Same tool, same cadence; the precision is luck, and the bracket is what
makes that visible.

## 3. `boot_utc` — promoting a prose fact into a field the tool reads

Round 202's own log record already carried the box's boot time
(`uptime -s` = `2026-08-27T11:50:48Z`) — **in its `notes` string**, where
nothing could use it. Its note even spells out the consequence it could
not act on: *"bounds the round-184/196 outage end to between 10:54:40
(still down) and 11:50:48 (already booted)."*

- New optional record field `boot_utc`, read with `.get()` so its absence
  and `null` are equivalent to every consumer.
- `nuc/reachability_backfill.py`'s round-202 row now sets it. Its `rec()`
  emits the key **only when non-`None`**, so re-running the one-shot
  script still reproduces the other 23 backfilled rows byte-for-byte —
  verified directly before migrating (a fresh regeneration differed from
  the live log on exactly one row, round 202's, and no other).
- The live log's round-202 line was migrated in place under assertions
  that every pre-existing key was unchanged, that the note was *extended*
  rather than rewritten, and that the only new key was `boot_utc`.
- Effect on real data: outage 1's end uncertainty **2h23m46s → 0h56m08s**,
  and its max-possible span **8h30m04s → 7h02m26s**.

### Captured automatically from here on

`check()` now reads the boot time itself on an `up` verdict, via a new
`boot_probe()`:

- **`/proc/uptime`, not `uptime -s`.** `uptime -s` prints the box's
  *local* time with no offset; converting it to a UTC instant needs the
  box's timezone, which nothing in this log records. (Rounds 202-232 read
  it as UTC and the arithmetic happened to check out — but that was an
  assumption, never a verified fact, and it is exactly the kind of
  unexamined step this track keeps finding.) An elapsed-seconds float
  needs no timezone at all.
- **A separate ssh call, not an extra command on the probe.** `ssh_probe`
  requires stdout to be exactly `UP`, and that strictness *is* the `up`
  verdict (`test_ssh_probe_unexpected_stdout_not_reachable`). Appending a
  second output line would have meant relaxing it. Cost: one extra
  round-trip on up checks, and **zero on down checks** — `check()` only
  probes after the first probe already returned reachable, so a down box
  never sits through a second connect timeout
  (`test_check_down_record_has_null_boot_utc_and_never_probes_for_it`
  asserts the exact command list).
- **Bias deliberately toward a *later* boot time**, the conservative
  direction (boot time is an *upper* bound on when an outage ended, so
  overshooting late can only widen the bracket): `now_fn()` is read
  *after* the probe returns, so it already lags the `/proc/uptime` read by
  the ssh round-trip, which dwarfs the sub-1s truncation to whole seconds.
- Every failure mode returns `None`, never raises: unreachable, non-zero
  exit, empty/unparseable/negative output. A missing boot time just leaves
  `streak_bounds` on its `next_check` fallback.

## 4. The record claim, now actually a proof

`current_streak_duration` gained the bracket half of both questions it
answers. `elapsed_s` (lower bound) is unchanged and every pre-existing
field keeps its meaning; the additions are `earliest_possible_start_utc`
/`_source`, `start_uncertainty_s`/`_human`, `elapsed_upper_s`/`_human`,
`longest_completed_same_verdict_streak_max_possible_s`/`_human`,
`definitely_exceeds_longest_completed`, `definite_margin_s`/`_human`.

The distinction that matters:

- `exceeds_longest_completed` compares **lower bound vs lower bound**.
  Like-for-like, and what rounds 322/328 reported — but not a proof: the
  old outage's *true* span could have been longer than its confirmed one.
- `definitely_exceeds_longest_completed` compares **this streak's lower
  bound vs the old record's UPPER bound**. When true, the current outage
  beats the old record even reading the old record as generously as the
  evidence allows. It abstains (`None`) rather than guessing when the
  prior streak has an unbounded side
  (`test_current_streak_duration_definite_comparison_none_when_prior_is_unbounded`).

Live, at round end:

```
elapsed_human                    10h50m37s   (lower bound)
elapsed_upper_human              10h53m43s   (upper bound; 3m06s apart)
longest_completed ... _human      5h14m40s   (old record, lower bound)
longest_completed ... _max_possible_human
                                  7h02m26s   (old record, upper bound)
exceeds_longest_completed             true
definitely_exceeds_longest_completed  true   <-- new, and a proof
definite_margin_human             3h48m10s
```

So the headline this track has been carrying since round 322 survives the
stricter test — this outage is now longer than the previous record **even
under the previous record's most generous reading**, by 3h48m and
counting. That was true before this round; nothing in the tool could say
so.

## 5. A latent crash the new code walked straight into

`_parse_ts` was `strptime(ts, "%Y-%m-%dT%H:%M:%SZ")` — exactly right for
the `checked_at_utc` values this module writes itself, and a `ValueError`
on both fields tailscale supplies: `LastSeen` carries 1 fractional digit
(`2026-08-29T02:10:00.1Z`), `LastWrite` carries 9
(`2026-08-29T12:47:50.906797174Z`). The log has stored both since round
310 and nothing had ever parsed them — they were only ever copied into
prose. `streak_bounds` is the first consumer, and it hit the crash
immediately.

Now tolerant: strip the `Z`, normalise any fraction to exactly 6 digits by
**truncation** (matching `format_duration_s`'s own choice — a rounded
`.9999999` must not roll a whole second forward), then `strptime`.
Hand-rolled rather than `datetime.fromisoformat`, which handles both only
on Python 3.11+ (no `Z` suffix and only 3-or-6-digit fractions before
that) and this suite has run under 3.9.

**Process note**: the first patch of the tolerant parser stripped the `Z`
and then still matched against the format string *containing* `Z`. Eight
pre-existing tests caught it on the very next run. This is the third-party
value of the 32-test baseline round 310/322/328 accumulated — the tests
that failed were not the new feature's, they were the old ones.

## Verification

- **47 new tests** in `nuc/tests/test_reachability_check.py`: **32 → 79
  passed**. `nuc/tests/` overall: **229 → 276 passed** (+47 exact,
  one-for-one). Coverage by area: 6 parser-tolerance (including the
  ".1 means tenths not microseconds" and no-second-rollover cases), 1
  `_build_streaks`, 18 `streak_bounds` (bracket arithmetic, each evidence
  source, each contradictory-evidence rejection, unbounded sides,
  ongoing), 2 `longest_completed_streak_bounds`, 4
  `current_streak_duration` bracket fields, 12 `boot_probe`/
  `boot_utc_from_uptime`/`check()` integration, 4 against the real
  committed log.
- **Real-log regression tests** pin outage 1's complete bracket (closed
  history, can never legitimately move), the current outage's start bound,
  the 202-286 up streak's boot-derived start, and a set of invariants that
  must hold for every streak as future rounds append: uncertainties never
  negative, `confirmed_span_s <= max_possible_span_s`, and an unbounded
  side always leaves `max_possible_span_s` `None`.
- **Consistency test between the two `max()` calls**:
  `longest_completed_streak_bounds` must return the bracket of exactly the
  streak `longest_completed_streak` names — `current_streak_duration`
  prints one's confirmed span next to the other's max-possible span, and
  that pairing is meaningless if they ever drift apart.
- **Cross-track regression** (nothing outside `nuc/` was touched, and the
  numbers confirm it): `bash harness/run_tests_fast.sh` → **417 passed,
  234 deselected**, byte-identical to rounds 331/333;
  `bash languages/whence/run_tests_fast.sh` → **952 passed, 40
  deselected**, byte-identical to rounds 332/333.
- **CLI smoke**: all four subcommands run against the real log;
  `summarize`'s output shape is unchanged (4 streaks, same 7 fields per
  streak) despite the `_build_streaks` extraction underneath it.
- **Log integrity**: `git diff --stat state/nuc-reachability-log.jsonl` →
  3 insertions, 1 deletion = the 2 new live records plus the one migrated
  round-202 line, exactly as intended.

## What this does and doesn't change

- **Does not** unblock the standing asks. `swap_watch_launch.py launch`
  (the second multi-hour poll) and standing-state re-verification
  (`--cap 256`, E3 patch, OLMoE tarball, `memory.events` max, operator
  login, escalation channel) all still need the box up. Seventh
  consecutive down E-round for that ask.
- **Purely additive** to every existing public surface: no field renamed
  or removed, no existing test's assertions weakened, `summarize`'s and
  `check`'s output shapes unchanged apart from `check` gaining `boot_utc`.
- **Every number this track publishes from here on** can be quoted as a
  bracket instead of a point, straight from the tool, with the evidence
  each end rests on named — and when this outage finally ends, its true
  span will be bracketed automatically (tightly, if the closing round's
  own `check` captures `boot_utc`, which it now does with no manual step).

## Deliberate limitation, worth stating plainly

`confirmed_span_s` stays **SSH-ground-truth-only, check to check**. The
same evidence used for the upper bounds could also widen a *confirmed*
span — e.g. `LastSeen 02:10:00.1Z` proves the 202-286 up streak was still
up 4h28m after its own last up check, so its confirmed span could
honestly be raised from 32h23m22s to ~38h19m. That was not done, on
purpose: `confirmed_span_s` is the number every prior round quoted and the
key `longest_completed_streak` ranks on, and it rests on one evidence
class (a real SSH probe). Mixing tailscale-derived evidence into the
*strongest* number the tool reports would weaken it to make a weaker
number look better. The bracket already carries that information on the
upper side, where a weaker evidence class belongs.

## New skill: `sampled-interval-brackets`

The generalizable finding here is not about this box. **Any code that
computes a duration from periodic observations rather than from transition
events reports a lower bound and calls it the answer** — outage duration,
incident length, time-to-recovery, session length from heartbeats, "how
long was this test broken", "when did this regression land between two CI
runs". `skills/sampled-interval-brackets/SKILL.md` writes up the whole
method: name the two ignorance windows first; inventory timestamp fields
you already store but never parse (that is where the tight bounds hide);
report four numbers instead of one; label each bound's evidence source;
keep the strongest number in a single evidence class; leave an unbounded
side `null` rather than substituting "now"; drop rather than clamp
contradictory evidence; and make "is this a record" a proof by comparing
against the historical UPPER bound. Its pitfalls section carries the two
traps this round actually hit — the timestamp parser that only ever parsed
its own output, and evidence that is symmetric in form but asymmetric in
meaning (a "last seen alive" field bounds a down interval and says nothing
usable about an up one).

- `skill_lint.py --house --strict skills/sampled-interval-brackets/` →
  **0 errors, 0 warnings, exit 0**. Whole corpus: 17 → **18 skills, 0
  errors, 1 warning** (the pre-existing `fuzz-mutate-kill-loop` B002,
  untouched).
- 3 positive trigger cases added to `skills/trigger-cases.json`
  (near/mid/far, matching the file's existing convention), restoring the
  offline audit to **0 skills under the 3-positive floor** — adding the
  skill without cases had regressed it to 1. Audit now reads 15 never / 3
  probed (was 14/3; the +1 never is this skill). `--audit`'s offline-ness
  re-confirmed by reading `trigger_eval.py:1240-1252`, which returns
  before both the canary and probe paths, before running it
  ([[feedback_check_flag_scope_before_priced_runs]]).
- `python3 -m unittest discover -s skills/skill-authoring/scripts` → **Ran
  165 tests, OK**, and `pytest skills/session-inheritance-audit/scripts/
  skills/skill-authoring/scripts/ -q` → **221 passed** — both
  byte-identical to round 333, confirming the new skill and cases broke
  nothing in the skills(B) toolchain.

## Next steps (round 334's own)

1. Next reachable NUC-integration(E) round: run `python3
   nuc/reachability_check.py check --round NNN` FIRST (it now captures
   `boot_utc` automatically, which is what closes this outage's end
   bound tightly), then `python3 nuc/reachability_check.py bounds
   --verdict down` to read the finished outage's true bracket, then
   `swap_watch_launch.py plan/launch` for the still-unlaunched second
   multi-hour poll — rounds 304/310/316/322/328's item, now SEVENTH
   consecutive down-round for that ask.
2. Standing NUC state (`--cap 256`, E3 patch, OLMoE tarball,
   `memory.events` max, operator login, escalation channel) still NOT
   re-verified — round 304's item 2, unchanged; box down this round too.
3. `reachability_check.py`'s `"ambiguous"` verdict has still never been
   observed live through round 334 — round 310's item 3, unchanged.
   Note it now also has no `streak_bounds` coverage against real data;
   `_LAST_SEEN_BOUNDS_START` includes it on the same reasoning as `down`,
   but that path is fixture-tested only.
4. **New**: `boot_probe`'s live path is unverified against a real box —
   every test injects a fake runner, and the box has been down for all
   seven rounds since the field was conceived. The first up-round must
   sanity-check that `cat /proc/uptime` over ssh actually returns what
   the parser expects (and that the derived `boot_utc` is plausible
   against `uptime -s`) before trusting the bracket it produces. Same
   shape as round 304's launcher, whose success path is still unverified
   for the same reason.
5. **New**: the deliberate `confirmed_span_s` limitation above. If a
   future round wants evidence-widened confirmed spans, add them as
   *separate* fields (`evidenced_span_s`?) rather than redefining
   `confirmed_span_s` — three rounds of history and one ranking key
   depend on its current meaning.
6. Rounds 316/322/328 added no `state/nuc-missions.md` addendum. Round
   334 added one and recorded why the gap is benign (the reachability log
   superseded per-round prose snapshots for down-rounds, by design, from
   round 310). If a future round wants that file to stay narrative-
   complete, the three gaps are reconstructible from the log with no new
   information needed.
7. **New**: `sampled-interval-brackets` is **never-probed** — its 3
   trigger cases exist but no live probe has run against them. A real
   probe is a priced run, so it was deliberately not launched from an
   E-round ([[feedback_check_flag_scope_before_priced_runs]]); a future
   skills(B) round can fold it into a batch. 15 of 18 skills are in the
   same state, so this is the corpus norm, not a new gap.
8. The `tail`/EOF backgrounded-pipe silent-drop mechanism (rounds 296,
   300, 303, 309) remains genuinely unconfirmed — round 310's item 5,
   unchanged; track-wide, not E-specific.
