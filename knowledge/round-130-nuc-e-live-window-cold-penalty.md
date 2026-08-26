# Round 130 — NUC-integration(E) — live window: ceiling confirmed, cold-penalty feature, inheritance audit

## 0. Context and inheritance audit

`state/nuc-missions.md` lists E1-E5, all `[x]` DONE. `state/research-state.md`'s
round log stops at round 127 (harness); rounds 128 and 129 both ran (128 died
at `error_max_turns`, 129 succeeded, 44 turns) but neither left a knowledge
file or a round-log entry. Round 124 (NUC/E) is the relevant gap for this
track: its log (`logs/round-124.json`) shows `error_max_turns` after 81 turns
/ $2.94 / 21.5 min, yet it left real, substantive work — `nuc-missions.md`'s
E4 and E5 checkboxes were ticked by round 124, backed by two NUC-side files
that did not exist before it ran: `/work/logs/nuc-fast-lane.md` (live cgroup
snapshot confirming the round-106/112 RAM-FAIL verdict, first NUC-side E4
write) and `/work/logs/nuc-taskscript.md` (first live Errand run through
`:8080`/`:8600`, four real requests, a `cold_penalty` backlog item flagged).
Nothing in the local git tree points at round 124 except `nuc-missions.md`'s
prose and one untracked file, `nuc/taskscript/examples/answer_live_r124.errand`
— the round's actual measurements live only on the NUC. This entry is the
first record of round 124's work in `research-state.md`'s round log (below);
rounds 128/129 are noted as open debt for tracks D/skills, not chased further
here (out of track, and re-deriving their content risks duplicating whatever
those tracks pick up next).

Also observed, left alone (not this track): `languages/whence/` has 6
uncommitted files (`SPEC.md`, `ast_nodes.py`, `interp.py`, `lexer.py`,
`parser.py`, `values.py`) plus an untracked `tests/test_v13.py`, sitting on
top of a committed "Time-Travel Debugger v0.7" (`8637795`) — this is
round 126/127/128's v0.13 return-type-checking WIP (round 127 wrote the
missing `_check_ret` to un-break it). Whence suite is 777/777 green with it
in place; not touched this round (language track's business).

## 1. The box was UP — a rare live window, used for real measurement

`ping`/`ssh` both worked at 18:08 UTC (round 124 had it at 16:11 UTC on the
SAME boot — `qwen36-colibri` PID 1047, uptime 5h10m here vs round-124's
3h13m, `--cap 256` unchanged). Two read-only cgroup snapshots ~8 minutes
apart, plus a controlled live request sweep. No restart, no config change —
every write was to `/work/logs` or `/tmp` on the NUC and to this repo.

### 1a. The RAM ceiling was reached live, but swap was NOT triggered — new nuance

| time (UTC) | uptime | `memory.current` | `memory.max` | `memory.swap.current` | system `MemAvailable` |
|---|---|---|---|---|---|
| r124, 16:11 | 3h13m | 15.6 GiB | 30.0 GiB | 0 B | 21.6 GB |
| r130, 18:08 | 5h10m | **30.0 GiB (= max)** | 30.0 GiB | 0 B | 1.12 GB |
| r130, 18:16 | 5h18m | **30.0 GiB (= max)** | 30.0 GiB | 0 B | 0.73 GB |

Round 106/124 established that `qwen36 --cap 256`'s footprint grows with
expert-cache *diversity*, not uptime alone, and that the onset is
traffic-dependent rather than immediate. This round adds the missing middle
of that curve on the SAME session: within ~2 more hours of the same boot,
the cgroup went from 52% of its ceiling to pinned exactly at `memory.max` —
but **`memory.swap.current` stayed at literal 0 B at both checkpoints**,
even as system-wide `MemAvailable` collapsed from 21.6 GB to 0.73 GB. Reading
cgroup v2 semantics: hitting `memory.max` first forces reclaim of anything
reclaimable (page cache) before the kernel pushes anonymous pages to swap —
so "at the cgroup ceiling" and "swapping" are sequential, not simultaneous,
events. Round 106's original "4.2 GB swapped" reading needed either more
elapsed time past this point or a different load mix than this window
produced. Net: the RAM-FAIL verdict is not just correct in the abstract for
this deployment — the actual box, right now, sits at meaningful memory risk
without a restart (system `MemAvailable` under 1 GB), independent of whether
swap has started yet. Not fixed (needs the operator-approved restart at
`--cap 204` the plan already recommends); logged to `/work/logs/nuc-fast-lane.md`
verbatim (see NUC log) so the operator sees it without re-deriving it.

### 1b. Warm-up decay measured directly: flat across 0-180 s, contra a smooth-curve assumption

Round 124 flagged an unbuilt backlog item: "log inter-request gaps against
TTFT ratio on live traffic ... to fit the actual decay shape," reading its
own data (a >29-hour-idle request at 2.08x the E1-curve projection, then
immediate-follow-up requests back on the curve, then a `mini_turn` ~1-2 min
later reading ~1.5x high) as "graded, not binary."

This round ran a controlled 4-point sweep to test that directly: an
identical 67-prompt-token, `max_tokens=1`, **no-`tools`-field** request to
`:8080`, at gaps of 0 s / 30 s / 90 s / 180 s since the previous one
(`/tmp/nuc-decay-r130.jsonl` on the Mac; NUC side sees only ordinary
completions, no state changed).

| gap (s) | curl wall time (s) |
|---|---|
| 0   | 9.76 |
| 30  | 9.74 |
| 90  | 10.00 |
| 180 | 10.02 |

Flat within ~3% across the whole range — no measurable warm-up penalty at
any gap up to 180 s, in direct tension with round-124's "graded" reading of
its own `mini_turn` data point. The likely reconciliation: round-124's
elevated `mini_turn` sample carried `tools yes` (tool-schema rendering has
its own real cost — round 22's colibri-tokenizer finding), while this sweep
deliberately omitted `tools` to isolate pure idle-time effects. So some or
all of the "graded decay" round 124 inferred from one data point may be
tool-schema cost, not idle time — and the true decay curve (if a smooth one
exists at all) lives entirely in the unmeasured gap between 180 s and >1 day.
No round has bridged that gap; flagged as still open, not claimed solved.

## 2. Built: `cold_penalty`/`cold_after` in Errand (SPEC v0.2, round 124's flagged backlog item)

Given §1b's finding — real data at two extremes (flat at ≤180 s, 2.08x at
>29 h) with nothing in between and a plausible confound (tool schemas) in
the one "graded" reading — fitting a continuous decay function would be
overfitting a single ambiguous point. Built the narrower, honestly-scoped
thing the data supports: a lane may declare `cold_penalty DURATION` (added
to TTFT) and `cold_after DURATION` (the idle threshold, or "never called
this lane yet this run") — a single declared **step**, not a curve, and
both keys are required together (a `ParseError` otherwise — a lone
`cold_penalty` with no `cold_after` would silently never fire, and a lone
`cold_after` with `cold_penalty` unset would silently do nothing; both are
static-discipline bugs the parser now catches, matching SPEC decision 6's
existing philosophy).

Implementation (`nuc/taskscript/`):
- `parser.py`: `Lane` gains `cold_penalty: float = 0.0` / `cold_after:
  Optional[float] = None`; two new `LANE_KEYS`; link-time check requires
  both-or-neither.
- `interp.py`: `project()` takes an optional `idle_s`; `Projection` gains a
  `cold: bool` field; `Interp` tracks `self._lane_last_call: dict[str,
  float]` keyed by lane name, read via the **same injected `clock()`**
  budgets already use (so this is exactly as offline-testable as
  retries/budgets — no wall-clock read anywhere). `idle_s` is `None` on a
  lane's first-ever call in a run (treated as cold — the safer default,
  matching "we don't know, assume worst") or `now - last_call` afterward;
  the lane is marked "warm from here" only when a task is NOT refused at
  preflight (a refusal never touches the transport, so it must not touch
  the warm-state either). `preflight` trace events now carry `idle_s` and
  `cold` for `why`/telemetry visibility.
- `SPEC.md` +decision 8, grammar line updated.
- Tests: 2 new parser-error parametrize cases (`cold_penalty` without
  `cold_after` and vice versa), `test_lane_cold_penalty_parses_and_requires_both_keys`,
  `test_project_applies_cold_penalty_only_when_idle_at_or_above_threshold`
  (never-called / just-under-threshold / at-threshold, exact ttft_s
  arithmetic), `test_interp_tracks_idle_per_lane_and_prices_the_first_call_as_cold`
  (fake-clock two-flow run: first call ever = cold, immediate second call =
  warm, third call after a 30 s clock jump = cold again) — 5 new tests, all
  green first run.

Not built (deliberately): an automatic real-time-based decay function, or
any live "probe call before pricing" mechanism — both would need more data
than exists between 180 s and >1 day, and the DSL's standing discipline
(SPEC decision 1-3: everything time-dependent is either injected or a
declared static fact, never inferred at runtime from real elapsed wall time)
argues against guessing a shape now. `cold_penalty`/`cold_after` are OFF by
default (`None`/`0.0`) on every existing lane in every existing example —
zero behavior change for anyone not opting in.

## 3. Tests and standing suites

- `nuc/tests/ nuc/taskscript/`: 157 passed (was 152; +5 this round), run
  under `nuc/.venv` (Python 3.9.6) and bare `python3` — both agree.
- Pre-existing, NOT caused by this round: `nuc/fast_lane/colibri-c/`,
  `nuc/kv_reuse/{upstream,patched}/` vendored server-code mirrors fail to
  **collect** under Python 3.9 (`dataclass(..., slots=True)` needs 3.10+) —
  these are compile-verification copies from round 28's KV-reuse patch work,
  meant to be checked against the NUC's own Python, not this venv; confirmed
  pre-existing via `git status` (untouched by this round's diff) before
  writing this off. The "nuc suite" figure quoted in `research-state.md`
  (152, now 157) has always meant `nuc/tests/` + `nuc/taskscript/`, not the
  vendored mirrors — this round is the first to notice the mirrors don't
  collect locally at all; flagged for whichever E round next touches
  `kv_reuse`/`fast_lane`, not fixed here (out of scope: fixing a vendored
  upstream-mirror's Python-version target is not this round's job).
- `harness/tests`: 448 passed (7m8s; unrelated to this round's changes,
  run as standing practice).
- `languages/whence`: 777 passed (71.99 s; includes the uncommitted v0.13
  WIP noted in §0).
- `skill_lint.py --house --strict skills/`: 15 skills, 0 errors, 0 warnings.

## 4. What was NOT done, and why

- **The E3 A/B (patched KV-reuse binary, restart at `--cap ≤ 204`)** was
  available this round — the box was up and PLAN-E4.md names this as the
  next step once an operator restart happens — but was **not attempted**.
  Restarting a shared inference service the operator/others may depend on
  is a hard-to-reverse, shared-state action; every prior E round (100, 106,
  112, 124) has treated it as requiring explicit operator sign-off, and nso
  did this one. Flagged prominently to the user in this round's summary
  rather than acted on unilaterally.
- **The NVMe on-box decode check** (5 minutes, would confirm whether the
  OLMoE lane's page-fault-bound 1.2 tok/s improves to a projected 2.5-4
  tok/s on real NVMe) needs the OLMoE lane deployed on the box, which it
  is not (round 124's taskscript run explicitly noted "no olmoe lane — not
  deployed on the box this round"); deploying it is a disk/bandwidth-cost
  action similar in kind to the restart question — not attempted without
  the same sign-off.
- Given system `MemAvailable` was already down to 0.73 GB by the end of
  this round's (very light — 4 small requests) live traffic, no further
  live requests were sent after §1b's sweep; padding the round with more
  live calls against a box already this close to its ceiling was judged not
  worth the marginal data.

## 5. Predictions

None banked — this round's live-window work was opportunistic (the box's
uptime status is not something a round can predict in advance) and the
`cold_penalty` feature's shape was fixed by the measurement in §1b itself,
not a prior guess. Standing D-013 practice resumes next round with a
plannable task.
