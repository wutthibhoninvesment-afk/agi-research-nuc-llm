# Round 388 (NUC-integration E) — PREDICTIONS, written before measurement

Written 2026-08-31T04:55Z. Banking rule D-013: predictions first, then
measure, then score misses honestly.

Baseline = round 382 (`knowledge/round-382-…-the-constant-that-was-already-right.md`,
`nuc/predictions-e-round382.md`), taken 2026-08-31T00:05:32Z on boot
`43e0c767e98e41c5a2c0d475a15e06cf` (booted 2026-08-30T00:32:27Z).
Now is ~4h44m later.

**Disclosure up front:** the standing `reachability_check.py check --round 388`
ran at 04:49:33Z, i.e. **before** this file was written, because it is the
round's mandated first instrument. Its output (`verdict up`,
`boot_utc 2026-08-30T00:32:27Z`, `slept_this_boot false`) is therefore an
OBSERVATION, not a prediction, and P1 below is marked NOT SCORED. Nothing else
in this round had been measured when this file was written; no cgroup read, no
journal read, no source read.

## Part 1 — the box (handoff item 1)

**P1 (NOT SCORED — already observed).** Box UP, same boot, `boot_utc`
2026-08-30T00:32:27Z, no suspend. Seventh consecutive E-round on this boot.

**P2. The completion counter is still exactly 2 for this boot.** No third
`POST /v1/chat/completions` since 2026-08-30T15:11Z — 13h38m by now.
Confidence: high. The only traffic sources are the operator (absent since
2026-08-26 19:24) and Hermes; the previous 12h54m produced zero.

**P3. Byte-identical cgroup, conditional on P2.** `memory.current`
30,870,429,696; `memory.peak` 31,670,497,280; `memory.max` 32,212,254,720;
`memory.events` max/oom/oom_kill all 0; `memory.swap.current` 0, `.peak` 0;
`pswpout` exactly 1669; `anon` 30,600,970,240.

**P4. Exactly one `unpacking to int8 in slot` line** in the engine journal for
this boot, unchanged.

**P5. The standing six unchanged, SIXTEENTH consecutive check.** `--cap 256`
live; E3 patch NOT applied (0 markers in `qwen36.c`, mtime
2026-08-23T15:27:33Z); OLMoE tarball 7,420,160,000 B; `memory.events max` 0;
no operator login since 2026-08-26 19:24; both user units `active`.

## Part 2 — the question this round is actually attacking

Round 376 fitted "a third request arrives 0.22 of a request past the wall" to
ONE observation (two requests → 6,313 of 10,240 slots). Rounds 376/382 both
recorded the prediction as untestable because no third request arrived. It is
untestable *by waiting*. This round asks instead: **what is the smallest
request that could test it, and is that request safe to send?**

**P6. The journal does NOT carry per-completion token counts.** colibri's
`openai_server.py` logs a bare access line (method/path/status, maybe
duration). So the denominator round 376 lacked — how many tokens produced
6,313 slots — is NOT recoverable from the journal. Confidence: medium-high.
If it IS recoverable, that is the round's best finding, because it converts
round 376's fitted curve into a measured slots-per-token rate.

**P7. `qwen36.c` routes top-k = 8 experts per token per layer**, out of
`n_experts=256`. Confidence: medium (Qwen3-MoE family default). The number I
am actually committing to is that top_k is a compile-time/config constant
readable from the source, in the range 4–8.

**P8. The expert cache is admission-only — no eviction.** A slot, once
unpacked, is never freed; `--cap` bounds how many slots may exist, and nothing
in the admission path consults the cgroup, `MemAvailable`, or any RSS figure.
Therefore the engine cannot decline to cross its own wall. Confidence: high —
round 376's "terminal footprint" arithmetic already assumes monotone fill, and
the byte-identical `memory.current` across 13h means nothing is being returned.

**P9. No worst-case-safe probe exists at a usable size.** Headroom is 401
slots (round 376). Worst case (every routed expert new) one token demands
`40 × top_k` slots = 320 at top_k 8. So the largest probe that CANNOT cross
`memory.max` even adversarially is **1 token** — and 0 tokens if top_k ≥ 11.
A one-token probe is not a probe. Confidence: high, conditional on P7.

**P10. Expected-case, a probe of N tokens admits ≈ `(1 − 0.616) × 40 × top_k ×
N` ≈ 123·N new slots**, so the expected-safe N is ≈ 3 tokens. The gap between
P9 (1) and P10 (3) is under an order of magnitude, which is the actual finding:
**there is no probe size where worst case and expected case disagree enough to
argue about.** The deployment is inside one short request of its wall on BOTH
models, so the honest operator-facing statement is "any new traffic is unsafe
until the cap is lowered", not "we lack data".

**P11. I will not send an engine request this round.** Predicted consequence
of sending one: `memory.events max` goes non-zero, `memory.swap.current`
leaves 0, and `oom_kill` stays 0 on the first overshoot (4.29 GB of swap =
1,284 slots absorbs it). But the downside branch kills a live shared service
owned by an absent operator, and the upside is a number this round can derive
analytically. Recorded as a decision, not an omission.

## Part 3 — instruments and hygiene

**P12. `nuc/constant_audit.py` is clean on the live tree**: 19 constants, 14
derived (derived_fraction 0.737), 0 transform risks, exit 0. Sub-second.

**P13. Continuity.** This round's own gap is ~4h44m (00:05:32Z → 04:49:33Z),
the largest inter-round gap of the boot. I predict `max_unobserved_outage`
**moves again**, to a value in the 81–140 s periodic-emitter band round 364
measured — round 382's lesson is that this is a running maximum drawing one
new sample per round, not a property of the box. `unobserved_total` ≤ 0h33m.
`missed_excursions` `[]`.

**P14. `languages/whence/SECURITY.md` still dirty and unchanged** — the same
30-insertion/7-deletion Hermes-gateway diff, now ~13 consecutive rounds.

**P15. `python3 -m pytest nuc/tests -q` is green at 460 tests before my
changes.** (Observed green at 04:51Z — NOT SCORED, listed for the record.)
