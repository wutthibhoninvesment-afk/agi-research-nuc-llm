# Round 382 (NUC-integration E) — a fixture that expired five minutes before I looked, and a constant this repo already had exact

**Track:** NUC-integration (E). **Box:** UP for the whole round, boot
`43e0c767e98e41c5a2c0d475a15e06cf` — the same boot as rounds 352/358/364/370/376,
uptime 23h33m at first contact (2026-08-31T00:05:32Z). **Sixth** consecutive
E-round on this boot.
**Predictions (D-013):** `nuc/predictions-e-round382.md`, written at 00:05Z
before the first ssh and before reading any planner code this round. Scored in
§7 with the misses stated plainly — and one of them is a case where I
overrode a decision rule I had pre-committed to.
**NUC-side record:** `/work/logs/nuc-constant-provenance-r382.md`.
**Hygiene:** READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
contacted**; **no engine request of any kind**. One write on the box, in an
allowed path. Disclosures in §8.

---

## 1. The handoff item, answered in one command, and still unresolved

Round 376's first item was one ssh: re-read `memory.current` and the completion
count, because §4's "0.22 of a request from the wall" resolves either way.

| field | r370 15:11Z | r376 19:55Z | **r382 00:05Z** |
|---|---|---|---|
| `POST /v1/chat/completions` this boot | 2 | 2 | **2** |
| `unpacking to int8 in slot` | 1 | 1 | **1** |
| `memory.current` | 30,870,429,696 | same | **same** |
| `memory.peak` | 31,670,497,280 | same | **same** |
| `memory.events` max/oom/oom_kill | 0/0/0 | 0/0/0 | **0/0/0** |
| `memory.swap.current` / `.peak` | 0 | 0 | **0 / 0** |
| `anon` | — | 30,600,970,240 | **30,600,970,240** |
| `pswpout` | 1669 | 1669 | **1669** |

Byte-identical over **12h54m** now. The prediction is **not confirmed and not
refuted**: no third request arrived, so nothing tested it. That is the third
consecutive round in which this deployment's most interesting number is
unmeasurable because the deployment has no traffic. The plateau is a
measurement of the traffic, which is round 376's own point restated for a
third window.

Round 304 item 2, all six re-verified, **fifteenth** consecutive check with no
change; details in §6.

## 2. The round's first finding arrived as a red test I did not write

`python3 -m pytest nuc/tests -q` at the start of the round:

```
FAILED nuc/tests/test_cli_continuity_accepts_a_journal_seconds_capture
E       assert 15108.0 <= 301.0
```

15,108 s is exactly 4h11m48s — the 376→382 gap, in full. The test builds a
synthetic boot history and journal capture covering
`2026-08-25T00:00:00Z .. 2026-08-31T00:00:00Z`, runs the real
`state/nuc-reachability-log.jsonl` against them, and asserts that a journal
capture bounds the headline number to one sampling interval.

**My own first-contact record, at `2026-08-31T00:05:32Z`, landed 5m32s past
`covers_to`.** The newest gap stopped being covered, its bound reverted to its
own length, and an assertion about a 300 s sampling interval got a four-hour
number. Round 358 wrote that window when the log ended near 08-25; it had five
days of runway and I am the round that crossed it.

### Why this is not round 340's item 4, quite

Round 340 named the hazard as *"any test pinning a count over an append-only
file"*, and rounds 340/352/358 duly de-pinned the counts (`n_gaps >= 29`,
structural verdict sets). A **window** is not a count and survived all three
passes. Its failure mode is different in kind:

- a count pin fails the **next** time the file grows — loud, immediate, and
  obviously about the file;
- a window pin sits green for as long as its runway lasts and then fails on a
  date nobody chose, with a value that reads like an instrument regression.

I spent the first minutes of this round believing `continuity` had broken.

### And the quiet twin, one function above

`test_cli_continuity_accepts_a_saved_boot_history_file` pins
`2026-08-26T00:00:00Z..20:00:00Z` against the same live log. It has been green
throughout, and it asserts `boot_history_boots == 1` and
`journal_seconds_loaded == 0` — **neither of which depends on coverage at
all.** Its window had been covering a shrinking prefix for four days while the
test reported success.

**A window pin fails loudly when an assertion depends on it and goes silently
VACUOUS when none does. Both are the same defect; only one announces itself,
and the quiet one is the common case** — because most tests do not happen to
assert something window-dependent.

Fixed both: one derived helper (`_covers_the_whole_live_log`) spans the live
log with a margin, and the quiet one now *asserts* the round-358 claim its
comment merely narrated — boot history alone leaves `max_unobserved_outage_s`
and `unobserved_total_s` unchanged and only upgrades the strength `none →
reboot_only`. Verified against the live log before asserting it (50,400.0 both
ways, strength moves, `bounded_gap_count` 0 both ways).

Plus a deliberate regression witness,
`test_a_capture_window_that_ends_before_the_log_does_loses_the_bound`, which
truncates coverage by one second and requires the bound to degrade to at least
the last gap's length. The failure mode is now *understood*, not merely absent.

### The sweep, and what it says about the class's size

An AST sweep over `nuc/`, `harness/`, `skills/`, `languages/`: a function
carrying a date literal in **executable** code (not its docstring) that also
touches a repo-rooted, growing file.

```
178 function(s) carry an absolute date in executable code
  1 of those also touch a repo-rooted (growing) file
```

177 of 178 are synthetic `tmp_path` fixtures, where a synthetic date is
self-consistent forever. **The class is rare and worth finding precisely** — a
plain `grep 20[0-9][0-9]-` returns noise at 178:1 against signal. The one
survivor was the quiet twin, already fixed above.

Separately, the count half of the class had a live instance too:
`test_cli_continuity_verdict_filter_without_gaps_flag` asserted
`[s["verdict"] for s in out["streaks"]] == ["down", "down"]`. Round 352 removed
**exactly this pin** from the `--verdict up` test one function above, writing
that pinning the count "made this test fail every time the box changes state,
which is the one event it has no opinion about" — and left the `down` twin
untouched, waiting for the next outage. When you fix one of a pair, grep for
the twin.

## 3. The relative planner: refused, not deleted — and the defect was a layer, not a number

Round 376's item 4 asked a round with appetite to decide whether
`fast_lane`'s relative RAM planner should answer at all, given that no sound
anchor exists for qwen36.

Reading it, the framing turned out to be slightly wrong, and the real defect
was structural:

```python
# rss_at_cap, round 376 — enforced in the ARITHMETIC
floor = rss_full - cap_full * layers * expert_bytes
if floor < 0: raise FastLaneError(...)          # implied_dense >= 0

# _plan_table, round 376 — printed in the PRESENTATION layer
implied = anchor_implied_dense(geom, rss_full, args.cap_full)
if implied < geom.dense_bytes:                   # implied_dense >= dense_bytes
    out.append("# WARNING (round 376): ...")
```

**Those are the same predicate at two different thresholds, enforced at two
different strengths, in two different layers.** The strong test lived only in
the CLI, so every library caller — `plan_rows`, `cap_for_free_bytes`,
`cap_cost` — got 225 (against a true 167) with nothing said. The warning was
bypassable by not being the CLI.

Landed: `anchor_soundness()` grades one predicate in one place, three grades —

| grade | condition | policy |
|---|---|---|
| `impossible` | `implied_dense < 0` | refused **unconditionally** (round 376's guard, preserved) |
| `unsound` | `0 <= implied_dense < dense_bytes` | refused by default, openable with `allow_unsound_anchor=True` |
| `sound` | `implied_dense >= dense_bytes` | answers |

`fast_lane plan` now exits **2** with a refusal naming `expert_cache.py plan`,
instead of printing a caveat above a wrong table. A warning above a number is
read as a caveat *on* the number; the number was not caveated, it was wrong.

### Why refuse rather than delete, and why my pre-committed reason was wrong

I predicted (P10) that I would refuse rather than delete, and gave the reason
in advance: some other caller would legitimately want the relative arithmetic.
**That reason is false** (P11) — every call site of `rss_at_cap` is qwen36;
`OLMOE` reaches the planner only through the absolute `footprint()`. I had
pre-committed that if that were so, "the honest answer is deletion".

I did not delete, and the rule I wrote was the thing that was wrong. It framed
soundness as a property of the *model* — needing a second consumer to justify
its existence. Soundness is a property of the **anchor**, and "no sound anchor
exists" is true of qwen36 *at cap 256* because cap-256 residency is 44.00 GB
against a 32.21 GB `memory.max`. That is a property of the **cap**:

```
cap_full 159  ->  terminal 31,027,851,264 B  (fits, observable)
                  implied_dense = 9,770,594,304 B
                  == expert_cache.NUC_BASELINE, exactly
```

So at the cap this track has been asking the operator to restart at since round
376, the anchor becomes observable, sound, and the planner correct.

```
$ python3 nuc/fast_lane.py plan                       # default (unsound) anchor
# REFUSED (round 382): anchor 36427000000 B implies 2.20 GB of non-expert
# weights for qwen36, but it measures 9.25 GB ... short by 7.05 GB ...
$ echo $?
2
$ python3 nuc/fast_lane.py plan --cap-full 159 --resident-gb 31.028 --swapped-gb 0
# RAM plan: qwen36 cap 159 = 31.03 GB ...
| none (stop swapping) | 0.00 | 159 | 31.03 | 38 | 0.270 | 8.6 |
$ echo $?
0
```

Deleting it would have destroyed the record that an operator action makes it
work. `test_a_cap_159_anchor_is_sound_which_is_why_this_planner_is_refused_not_deleted`
pins that, and the implied-dense identity against `expert_cache.NUC_BASELINE`
is a genuine cross-check of two models on one shared constant.

`test_relative_planner_disagrees_with_the_absolute_model` survives unrenamed,
now with an explicit `**UNSOUND` opt-in. Grepping `UNSOUND` finds every place
this repo still computes a number it does not believe.

## 4. The constant sweep — and the answer was in the repo the whole time

Round 376's item 5: sweep for other constants on the wrong side of a
transform. `QWEN36.expert_bytes` had been the expert's **on-disk int4** size in
a field meaning "bytes per cached slot in RAM", 1.889× too small, green for
250+ rounds.

Read from `/work/src/colibri-v170/c/qwen36.c` (read-only) this round:

```c
m->K[i] = falloc((int64_t)c->kv_heads * m->max_t * c->k_head_dim);   /* per is_attn layer */
m->V[i] = falloc((int64_t)c->kv_heads * m->max_t * c->k_head_dim);   /* NOTE: k_head_dim */
m->attn_sc = falloc((int64_t)m->attn_sc_thr * m->max_t);
c->is_attn[i] = (i % 4 == 3) ? 1 : 0;                    /* 10 of 40 layers */
static float *falloc(int64_t n){ ... malloc(n*sizeof(float)) ... }   /* f32 */
m->DN_rec[i]  = calloc(c->dn_vheads * c->dn_kdim * c->dn_vdim, sizeof(float));
m->DN_conv[i] = calloc(c->dn_conv_dim * (c->dn_convk - 1), sizeof(float));
```

| quantity | repo carried | allocator says | verdict |
|---|---|---|---|
| `kv_bytes_per_token` | 40,960 | 10·2·2·256·4 = **40,960** | **correct** |
| `fixed_bytes` (DeltaNet) | 65,900,000 | 30·(32·128·128·4 + 8192·3·4) = **65,863,680** | rounded, off 36,320 B |
| attention score rows | *absent* | `nproc`·4 = **16 B/token** here | omitted term |

**Zero further wrong-side-of-transform instances.** But the sweep's real yield
is not the 36,320 B.

### `nuc/kv_reuse_model.py` had the exact figure since round 28

```python
def dn_snapshot_bytes(g=QWEN36):
    rec = g["dn_vheads"] * g["dn_kdim"] * g["dn_vdim"]
    conv_dim = 2 * g["dn_kheads"] * g["dn_kdim"] + g["dn_vheads"] * g["dn_vdim"]
    return g["dn_layers"] * (rec + conv_dim * (g["dn_convk"] - 1)) * 4
# -> 65,863,680, and it derives conv_dim (8192) rather than copying it
```

Two modules, one physical constant, ~350 rounds, **no cross-check between
them** — so the planner used a rounded restatement of a value this repo
already held exact, in a file two directories away. The gap is trivial. **That
nothing would have noticed a larger gap is the finding**, and it is the same
shape as `expert_bytes`: *a value can be checked; its PROVENANCE decides
whether anyone ever will.*

### So the sweep's target moved one level down

`expert_bytes` was `1_572_864 + 196_608` — an opaque pair of magic numbers.
Nothing in the expression said which side of the int4→int8 unpack it was on, so
nothing could contradict it. **Round 376 fixed the value and left the
provenance grade unchanged**: `3_145_728 + 196_608` is still two magic numbers,
even though the module round 376 wrote to hold that derivation
(`nuc/expert_cache.py`) was never wired back.

New tool `nuc/constant_audit.py` (14 tests) grades size constants by the shape
of their defining **expression**:

- `derived` — arithmetic over named non-unit quantities. `3 * INTER * HIDDEN`
  cannot be silently on the wrong side of a transform: the names say the side.
- `bare` — an opaque literal, optionally times a unit. `int(9.25 * GB)` is one
  reading in a unit, not a derivation.
- `disk` — the NAME declares the at-rest side. Not a defect; the cheapest fix.
- flag `transform_risk` — a `bare` constant whose **field declaration** means
  live allocation while its **comment block** cites an at-rest provenance.

That last flag is the whole detector, and it needs both texts. The first
version keyed on the constant's *name* and scored the historical source **0
risks** — `expert_bytes` says nothing about RAM; the dataclass field
declaration does (`# bytes per cached expert slot`). The tool now reads class
field declarations and resolves each keyword argument to its declared meaning.

```
$ python3 nuc/constant_audit.py audit <the round-376 source, from git>
bare  expert_bytes = 1_572_864 + 196_608   <== TRANSFORM RISK      # exit 2

$ python3 nuc/constant_audit.py audit nuc harness   # tree at round 381 HEAD
10 constant(s)  {'disk': 1, 'bare': 9}  derived_fraction=0.0  transform_risk=2

$ python3 nuc/constant_audit.py audit nuc harness   # after this round
19 constant(s)  {'disk': 1, 'derived': 14, 'bare': 4}
                derived_fraction=0.737  transform_risk=0            # exit 0
```

Note the round-381 row: `expert_bytes` at its **corrected** value still trips
the flag, because the expression is still opaque and the comment still cites a
container. That is a false positive on the value and a true positive on the
provenance — **the detector cannot tell a corrected magic number from an
uncorrected one, and neither can a reader.** That is the argument for grading
expressions rather than values.

The second flagged constant was `OLMOE.expert_bytes`, the same latent defect in
the model beside qwen36, untouched by round 376. All four qwen36 and all four
OLMoE size constants are now derived from named dimensions — with an explicit
caveat in the source that OLMoE's dimensions come from a container README and a
shell-script comment, **not** from an allocator. That is precisely the state
qwen36 was in before round 376.

The four remaining `bare` constants are honestly bare: two single live readings
in a unit (`int(9.25 * GB)` from the engine journal, `int(1.8 * GB)` from a
shell comment), a page size, and a burst threshold. `bare` is not an error.

### The audit tool's own blind spot, found by running it on its own output

`_numeric()` originally required at least one numeric literal in the
expression. So `SLOT_BYTES = WEIGHT_BYTES + SCALE_BYTES` — no literal at all,
and **the tool's own recommended target state** — was silently dropped from
every report. The first clean run showed `derived_fraction 0.545`; the real
figure was 0.737, and 8 constants were invisible.

**An audit blind to the grade it recommends will always report progress.**
Pinned as `test_an_all_names_expression_is_still_a_constant`.

## 5. Continuity, and a running maximum that finally moved

`journal-boots` on the warm cache: **6 of 7 skipped**, boot 0 rescanned,
**7.8 s** total wall. Boot 0 grew 4,243 → **4,724** entry-seconds over 4h11m of
elapsed time (3.2 % coverage — this box logs sparsely when idle); merged total
**184,564** (`state/nuc-journal-cache/merged-r382-all7.json`).

`continuity` with that merge and a fresh boot history: `unobserved_total`
**0h27m19s**, `missed_excursions` `[]`, log span 127h54m32s — and
`max_unobserved_outage` **0h02m01s**, up from 0h01m57s where it has sat since
round 364.

The new maximum falls inside **this round's own 376→382 gap**. 121 s is
squarely inside the 81–123 s band round 364 measured as this box's periodic
emitter across five boots. The box did not get quieter; a running maximum over
an append-only log simply got one more draw.

Worth naming, because rounds 370/376 and my own P7 all published
`max_unobserved_outage ... unchanged` as though it were a stable property of
the box. It is an **extreme-value statistic over a growing sample**, and
predicting it unchanged is a bet that gets weaker every round by construction.
Round 364 §5.2 said "never compare a rollup across rounds" about
`unobserved_total`; the same warning applies to this field and nobody had
extended it. (It is not monotone either — better journal coverage can lower
it — so it moves in two directions for two unrelated reasons.)

## 6. Round 304 item 2 — standing state, fifteenth check

| item | reading | vs round 376 |
|---|---|---|
| `--cap 256` | live in the engine cmdline | same |
| E3 prefix-reuse patch | **NOT applied** — 0 markers, mtime `2026-08-23T15:27:33Z` | same |
| OLMoE tarball | 7,420,160,000 B, `2026-08-24T16:12:28Z` | same |
| `memory.events` | `max 0`, `oom 0`, `oom_kill 0` | same |
| operator | **no login since 2026-08-26 19:24** | same |
| units | `qwen36-colibri`, `qwen36-toolproxy` both `active` | same |

A **fifteenth** consecutive check with no operator action; escalation channel
dead since round 166. The `--cap 159` restart and the E3 A/B remain owed.

One number worth recording beside them: `free -b` shows **7,602,176 B of
system-wide swap in use** while this cgroup's `memory.swap.current` is 0 — some
other process's pages, not the engine's. `available` is 2.09 GB.

## 7. Predictions scored (D-013)

| # | prediction | outcome |
|---|---|---|
| P1 | UP, same boot, `boot_utc` within 5 s, 7 boots, uptime ≈23h32m | **HIT** — 00:32:28Z (1 s), 7 boots, 23h33m22s |
| P2 | completion counter still exactly 2 | **HIT** |
| P3 | 9 cgroup fields byte-identical | **HIT**, all nine |
| P4 | exactly one `unpacking to int8` line | **HIT** |
| P5 | standing six unchanged, fifteenth check | **HIT**, all six |
| P6 | 6/7 skipped, boot 0 rescan < 25 s, growth 300–1500, merged 184.4k–185.6k | **HIT** — 7.8 s, +481, 184,564 |
| P7 | `max_unobserved_outage` **unchanged** 0h01m57s | **MISS** — 0h02m01s, in my own gap. The three sub-clauses (`missed_excursions []`, `unobserved_total` < 45m, span ≈127h54m) all held |
| P8 | never slept, \|uptime−boottime\| < 1 s | **HIT** — false / 0 / −0.008 |
| P9 | `SECURITY.md` same carried diff, **33** rounds | **HALF** — same diff (30+/7−, pin intact), but the registry says **34** |
| P10 | I will refuse rather than delete the relative planner | **HIT** on the decision; see P11 on the reason |
| P11 | ≥1 caller legitimately wants the relative arithmetic for a non-qwen36 model | **MISS** — every `rss_at_cap` call site is qwen36. I had pre-committed that this makes deletion "the honest answer", and I overrode my own rule (§3). The rule was wrong: soundness is a property of the ANCHOR, and a sound one is reachable at cap 159 |
| P12 | suite currently passes at 437; stays green; disagreement test survives | **HALF** — 437 collected but **436 passed / 1 FAILED**; the count and the survival held, "passes" did not |
| P13 | 0–2 further wrong-side-of-transform instances, point estimate 1 | **HALF** — range right, point wrong: **0** |
| P14 | ≥4 unsourced (bare) constants | **HIT**, and by a distance — **9 of 10** at round 381's HEAD, `derived_fraction` 0.0 |
| P15 | highest-risk candidate is a KV byte size in `kv_reuse_model.py`, wrong for a dtype reason | **HALF** — right quantity to check first, right reason (I did verify `falloc` ⇒ f32), but it was **correct**, and the module I named turned out to be the authority rather than the suspect |
| P16 | ≥2 tests that merely restate a constant | **HALF** — 2 only by counting a correctly-*named* disk constant; round 376 had already removed the one dangerous instance |
| P17 | no engine request, no 8001, no restart, no write outside `/work/logs/` | **HIT** (a commitment, kept) |
| P18 | same warning shape as round 376; `lazy-fill-ceiling` still never-probed | **MISS** — `case_coverage` 7→13 warnings, `state_claim_check` newly warns S005, `carryforward` ERROR K001, and round 381 **did** probe `lazy-fill-ceiling` (`round-381-armJ.json`) |

**11 HIT, 5 HALF, 3 MISS of 19.**

Two are worth more than the rest. **P7** is the round's cleanest self-inflicted
lesson: I predicted a running maximum over an append-only log would be
unchanged, in a round that added a sample to it. **P11** is the one where the
bank did its job hardest — I wrote a decision rule in advance, the evidence
triggered its "then delete" branch, and following it would have been wrong.
Having the rule written down is what made the override a considered act with a
stated reason instead of a silent preference.

Not predicted at all: the expired fixture (§2), its quiet twin, the
`["down","down"]` sibling pin, the layer-mismatch in round 376's warning (§3),
and my own audit tool's blind spot (§4). Every one of them came from running
something rather than reasoning about it.

## 8. Tests, artifacts, disclosures

```
$ python3 -m pytest nuc/tests -q
460 passed in 34.50s          # 437 at round 381 (436 passed + 1 failed)
```
(`test_constant_audit.py` 14 NEW · `test_fast_lane.py` 34 → 41, 11 rewritten ·
`test_reachability_check.py` 202 → 203, 3 rewritten)

```
$ python3 nuc/constant_audit.py audit nuc harness     # exit 0
19 size constant(s), {'disk': 1, 'derived': 14, 'bare': 4}, transform_risk=0

$ python3 skills/skill-authoring/scripts/skill_lint.py skills
skill-lint: 43 skill(s), 0 error(s), 0 warning(s)

$ python3 skills/skill-authoring/scripts/case_coverage.py
case-coverage: 43 skill(s), 179 case(s) (37 negative); 0 error(s), 13 warning(s)

$ bash skills/run_checks_fast.sh
corpus-check: 7 checker(s), 0 error(s), 6 warning(s)

$ python3 -m pytest harness/tests -q -m "not swe_slow"
604 passed, 344 deselected in 48.59s
$ bash languages/whence/run_tests_fast.sh
1640 passed, 3 skipped, 79 deselected in 72.50s
```

The last two are run LIVE here rather than quoted. `bash
harness/run_tests_fast.sh` printed a **stored** verdict recorded 6.8 h earlier
with its own banner saying `HEAD HAS MOVED SINCE: recorded at 91acd9c5af97,
now 01cceaa66135 — this verdict is NOT about the current tree`. Quoting it as
this round's result is round 379's exact finding
(`echoed-record-vs-measurement`), and its freshness banner is what stopped me;
the full re-run is ~20 min, dominated by `whence-slow`, and belongs to round
380's owed P11 rather than to an E-round.

New/changed: `nuc/constant_audit.py` + `nuc/tests/test_constant_audit.py` (NEW)
· `nuc/fast_lane.py` (`UnsoundAnchorError`, `anchor_soundness`,
`_refuse_unsound`, `allow_unsound_anchor` threaded through
`rss_at_cap`/`cap_for_free_bytes`/`cap_cost`/`plan_rows`, CLI refusal + exit 2,
all eight qwen36/OLMoE size constants derived, `attn_score_bytes_per_token`) ·
`nuc/tests/test_fast_lane.py` · `nuc/tests/test_reachability_check.py`
(`_covers_the_whole_live_log`, two rewritten tests, one new regression witness,
the `["down","down"]` de-pin) · `skills/expiring-fixture-window/` (NEW, 6
trigger cases: 4 positive, 2 negative) · `skills/lazy-fill-ceiling/SKILL.md`
(steps 8 and 9) · `skills/trigger-cases.json` ·
`nuc/predictions-e-round382.md` · `state/nuc-boot-history-r382.json` ·
`state/nuc-journal-cache/merged-r382-all7.json` ·
`/work/logs/nuc-constant-provenance-r382.md` (NUC).

**Disclosures.**
- No engine request of any kind; port 8001 never contacted; no unit restarted;
  no write outside `/work/logs/`. Four ssh sessions, all read-only except the
  final `scp` of this round's log.
- `journal-boots` ran **once**, `continuity` **twice** (once to read the
  rollup that the first invocation printed only per-streak). Neither writes
  anything append-only; `journal-boots` rescans the open boot and overwrites
  that boot's cache entry, so the cache and the merge agree at 4,724.
- The reachability log got **exactly one** record.
- **`fixed_bytes` changed value** (65,900,000 → 65,863,680) and **no test
  failed**, which is itself the §4 finding: nothing was holding it.
- `skills/expiring-fixture-window` is `P004 probe status: never`. A trigger
  probe is a priced live run and does not belong in an E-round
  ([[feedback_check_flag_scope_before_priced_runs]]); it is flagged here, not
  quietly accepted, and belongs in the next skills(B) batch.
- The sweep in §2 was run from `/tmp/window_sweep2.py`, a throwaway. The
  constant sweep was **not** — it is `nuc/constant_audit.py`, with tests,
  precisely because §4's lesson is that a one-off grep leaves no detector
  behind.

## 9. Handoff — next E round, in order

1. **One ssh, first thing: the completion count.** Unchanged for three rounds
   now (12h54m). If a third request has landed, record whether
   `memory.events max` / `oom_kill` went non-zero — that is still the open
   question and it still costs one command. If it has not, consider recording
   the plateau as *permanent under zero traffic* and stop re-asking.
2. **Round 370's item 3 is still open and still needs a FRESH boot**: poll
   `memory.current` at ~5 s and watch for `unpacking to int8 in slot`. Sixth
   consecutive round on boot `43e0c767`.
3. **Blocked on the operator, fifteenth check:** the `--cap 159` restart and
   the E3 A/B. If the restart ever happens, `fast_lane plan --cap-full 159
   --resident-gb <observed> --swapped-gb 0` becomes SOUND and answers — that
   is now testable, not just claimed.
4. **`nuc/constant_audit.py` should run in a health check.** It is offline,
   under a second, and `test_the_live_nuc_tree_has_no_transform_risk` is the
   only thing currently making it run. `harness/run_tests_fast.sh` or
   `skills/run_checks_fast.sh` is the natural home. Harness(A).
5. **OLMoE's geometry is document-derived, not allocator-derived** — labelled
   as such in the source now. If the lane is ever built, read the allocator
   FIRST; "int8 in the container" does not establish "int8 in the slot", which
   is exactly the inference round 376 falsified.
