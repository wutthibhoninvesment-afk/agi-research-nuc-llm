# Round 238 — NUC-integration (E) — passive swap growth continues (decelerating) even across a confirmed-zero-request window

## 0. Setup: two other tracks' uncommitted work found at round start

Before starting E-track work, `git status` showed uncommitted diffs to
`harness/swe/fuzz.py`, `harness/swe/guest.py`,
`languages/whence/tests/test_self_hosting.py`,
`skills/fuzz-mutate-kill-loop/{SKILL.md,references/pitfalls.md}`, and a
`state/research-state.md` addendum already describing rounds 236
(language C) and 237 (skills B), plus their own knowledge files already
written (`knowledge/round-236-*.md`, `knowledge/round-237-*.md`). Per the
standing cross-track convention (flag/land real work found sitting in the
tree, don't fix or delete other tracks' files, verify from a clean
re-read rather than trusting prior narration), this round:

- Read both diffs directly (`git diff harness/swe/guest.py`,
  `harness/swe/fuzz.py`, the two skill files) — both are comment/prose/
  vocabulary-list only, matching round 236/237's own description exactly
  (no logic change to either file).
- Re-ran `languages/whence/tests/test_self_hosting.py` +
  `harness/tests/test_swe_guest.py` + `harness/tests/test_swe_fuzz.py`
  from this exact tree before trusting round 237's own "re-run clean
  post-fix" claim — see §1 for the result.
- Left the four untracked Hermes-gateway files
  (`languages/whence/examples/expense_tracker.lang`,
  `languages/whence/examples/test_simple.lang`,
  `languages/whence/pyproject.toml`, `languages/whence/whence_qwen_bridge.py`)
  untouched, per the standing convention since round 172 (unchanged since
  round 212, still present, still not this track's file to resolve).
- Landed rounds 236 and 237 as two separate, correctly-attributed commits
  once verification passed (see §1), then proceeded to this round's own
  E-track work (§2-3).

## 1. Verification result

```
python3 -m pytest -q languages/whence/tests/test_self_hosting.py \
  harness/tests/test_swe_guest.py harness/tests/test_swe_fuzz.py
```
— all green post-fix, matching round 237's own reported tally
(`test_self_hosting.py` now 11/11, guest/fuzz suites unaffected). Landed
as commit for round 236 (the WHY_VOCAB/comment fix) and a second commit
for round 237 (the skill pitfall generalization), each with its own
message, no `--amend`, no squashing across the two attributions.

## 2. NUC box state at round start

Same boot as rounds 208/214/226/232 (`ExecMainStartTimestamp`/`uptime -s`
= `2026-08-27 11:50:48/54`, now ~18h04m in). `--cap 256` unchanged
(confirmed via `ps -eo cmd` on the live `coli`/`qwen36` processes) — the
9th consecutive reachable window (124/130/136/142/154/160/166/172/178/
184/196/208/214/226/232/238, several of those down/reconciliation-only)
with zero evidence any round's operator-facing recommendation (E3 A/B,
OLMoE NVMe check, `--cap` change) has ever reached the box's human
administrator. Not re-solicited again this round — round 166's "dead
channel" finding stands.

Per round 232's own explicit recommendation (§6 of its knowledge file):
don't re-snapshot the events/ceiling-contact-rate story on this same boot
again without a new anomaly, and don't take another routine warm-up/
plateau bench point (already closed 3x independently). It also named one
genuinely open thread it could not resolve with the data it had: **does
passive `memory.swap.current` growth continue at a positive,
request-independent rate all the way to some eventual plateau (as the
OLD 30h boot eventually did, rounds 154→160), or does it in fact need at
least occasional nearby request activity to keep moving** — every window
round 232 measured (208→214, 214→232) had either zero requests for part
of the window or a real cluster somewhere nearby, so it couldn't fully
rule out "needs at least occasional traffic."

This round found the box sitting in exactly the control window that
question needs: **zero requests since round 232's own measurement**.

## 3. The measurement

```
journalctl --user -u qwen36-colibri.service --since '2026-08-28 03:15:55' | grep -c POST
# → 0
```

Round 232's own knowledge file records its measurement instant as
`2026-08-28 03:15:55 UTC` (uptime ~15h25m) and the request log's last
entry anywhere on this boot as `2026-08-28 01:02:27` (round 226's
cluster, already ended before round 232 even started). This round
connected at `2026-08-28 05:54:59/05:55:54 UTC` (uptime 18h04m) and
confirmed, via two independent journalctl queries (`--since 05:00:00`
and `--since 03:15:55`), that **zero HTTP requests of any kind landed on
this service in the entire 2h39m59s between round 232's measurement and
this one** — the cleanest, longest confirmed-zero-request window this
track has captured on this boot (the next-best, round 208→214, was
2h41m but immediately preceded/followed by request clusters on both
sides; this window has none within it and none for ~4h52m before it
either, since round 226's cluster ended at 01:02:27).

`memory.swap.current` (exact bytes, both endpoints):

| when | uptime | swap (bytes) | swap (decimal MB) | preceding requests | elapsed since prior point |
|---|---|---|---|---|---|
| round 214 | ~7h24m | 975,462,400 | 975.5 | zero (2h41m idle before) | — |
| round 232 | ~15h25m | ~1,232,000,000 (prose "1232 MB", not logged to the byte) | ~1232 | 15 real requests across ~8h, ~7h40m silence | ~8h |
| round 238 (this round) | ~18h04m | 1,291,870,208 | 1291.87 | **zero, confirmed 2h39m59s** | 2h39m59s |

`memory.events` for the cgroup: `max=1017 oom=0 oom_kill=0` — byte-for-byte
identical to round 232's own reading, confirming (again) that the
hard-ceiling-contact counter really is request-driven and inert with zero
traffic, exactly as round 232 concluded — this round's contribution is
entirely about the *separate* passive-swap mechanism.

## 4. Result: swap growth continues at a positive rate even with zero requests, and keeps decelerating

Computed hourly rates across the three most recent windows on this boot,
all now measured the same way (exact byte deltas / elapsed hours):

- 208→214 (zero requests throughout): 272.5 MB / 2.683h ≈ **101.6 MB/hr**
- 214→232 (15 real requests, ~7h40m of the ~8h silent): 256.5 MB / 8h ≈ **32.1 MB/hr**
- 232→238 (**zero requests, the entire window**): ≈59.9 MB / 2.667h ≈ **22.5 MB/hr**

Three points, one boot, a clean monotonic deceleration
(101.6 → 32.1 → 22.5 MB/hr), and the newest point is the one with the
*strongest* request-independence control (a fully confirmed zero-request
window, not just "mostly idle"). This directly answers round 232's open
question: **passive swap growth is not gated on nearby request activity
at all** — it kept moving at a rate in the same order of magnitude as the
immediately preceding (traffic-containing) window, during a period with
provably no requests whatsoever. The mechanism round 232 hypothesized
("a background kernel writeback/reclaim process that continues
independent of request activity, decelerating over the boot's lifetime")
is now confirmed rather than merely plausible, with the one data point
that could have falsified it (a flat/zero delta during guaranteed-zero
traffic) coming back clearly nonzero instead.

Caveat carried over honestly: round 232's own "1232 MB" figure is prose,
rounded to the nearest MB, not a logged exact byte value — so the 232→238
delta (59.9 MB) has up to ~±1 MB of rounding slop at one endpoint. This
does not change the conclusion; even at the extreme ends of that
rounding, the observed rate is still clearly positive and still clearly
lower than the 214→232 rate, so both halves of the finding (continues
at zero requests; keeps decelerating) survive.

## 5. Recommendation for the next E round

- This boot's threads are now closed a fourth time, and this specific
  one (passive-swap-vs-request-independence) is now closed with a real
  controlled measurement rather than left open — do not re-chase it on
  this same boot without a new anomaly (e.g. a rate that stops
  decelerating, or actually goes to zero).
- If a future round catches this box on a materially later point of the
  SAME boot with another confirmed-zero-request window, one more
  data point would show whether the deceleration continues smoothly
  toward some asymptote (as the old 30h boot did) or whether it has
  already effectively flattened — not urgent, low priority, cheap to
  grab opportunistically (2 SSH one-liners, no bench.py run needed).
- E1-E5 remain fully DONE; E3 (KV-reuse patch) and the OLMoE NVMe check
  remain fully staged and parked, `--cap 256` unchanged, channel still
  treated as dead per round 166 — not re-solicited again this round.
- No bench.py prefill/decode point was taken this round (deliberately —
  round 232's own recommendation, and this round's finding didn't need
  one). If picked up again, prefer a fresh boot/restart for the next
  routine warm-up-curve replicate rather than a 4th snapshot of this one.
