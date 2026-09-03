# Round 472 (NUC-integration E) — the null that was the power switch

**Box DOWN the whole round.** SEVENTH consecutive down window (436, 442, 448,
454, 460, 466, 472), one continuous outage. Every finding below is offline
work on round 424's banked capture and on this repo's own driver transcripts.
**Zero ssh sessions succeeded: nothing was read from or written to the box,
port 8001 was never contacted, no engine request of any kind was made.**

Round 466's next-step item 3, verbatim:

> The observer effect is now a measured hypothesis and it has an experiment.
> If the logins cost the memory, the cost should scale with what the round
> DID, not with the login count.

This round built that experiment. It answers item 3, takes item 2's deferred
decision, and — the part worth reading — **finds three separate ways the
experiment lies, each of which reverses or erases the headline, and each
caught by the instrument rather than by review.**

---

## 0. Reachability, and round 460's item 1 first

Two probes, one per documented path, before any code ran.

| | when | result |
|---|---|---|
| tailnet `ssh -o ConnectTimeout=15 -i ~/.ssh/id_ed25519 jab@100.78.44.111` | 2026-09-03T08:32:08Z | `Connection timed out`, rc 255 |
| LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` | 08:32:32Z | same — **and the key still does not exist on this host**, so that path proves nothing either way |
| `tailscale status --json` | 08:33:02Z | `Online false`, `LastSeen 2026-09-01T18:27:56.1Z` |

That `LastSeen` is **byte-identical to rounds 448, 454, 460 AND 466**, so
436→472 is ONE outage. CLAUDE.md's two-failure rule fired after the second
probe. Plaintext: `active; relay "sin"; offline, last seen 1d ago,
tx 12168 rx 0`.

Round 460's item 1 ran FIRST, as it says to: `coverage --strict` **0**,
`precision-audit --strict` **0**, `lastseen-drift --strict` **1** — the last
for the documented reason (tailscale recomputed `LastSeen` by −124 s inside
this streak), not a new break. Re-run after this round's row was appended:
identical, 0/0/1.

`status` after the append: confirmed **37h26m00s**, upper bracket
**38h28m42s**. Round 466 mixed those two brackets in prose and scored itself a
PARTIAL for it; the confirmed figure is the one quoted here and everywhere
below. It passes the longest completed streak in this log (19h38m06s) by a
**definite 15h03m33s** and the longest unobserved one (14h00m00s) by
23h26m00s.

Round 472's row was appended with `reachability_check.py replay`, reading
`state/nuc-capture-r472/tailscale-status-r472.json`. The log is now 63 rows.

---

## 1. The dose: a second file that does not know about the first

The response variable — swap-out bytes per 10-minute sar bucket — comes off
the box, in `state/nuc-capture-r424/sar-all.txt`. For a dose-response the DOSE
has to come from somewhere the response cannot see. It does:
**`logs/round-<N>.json`**, the driver's own stream-json transcripts, which
record every shell command a round issued with millisecond timestamps. 54 E
rounds are in the driver log's population; 47 of them have a transcript on
this box.

`nuc/dose_response.py` reads them. Per round it extracts `n_calls`,
`n_logins`, `box_seconds`, `bytes_returned`, `bytes_landed`, and — as
**negative controls** — `local_calls`, `local_bytes`, `transcript_bytes`, the
same quantities for work that never touched the box. A control that cannot
cost the NUC any memory and yet predicts the response as well as the doses do
is the whole ballgame, and it is why they are in the same table.

### 1a. The heredoc that looked like a login

The first draft scored this as a contact with the box:

```
cat > nuc/predictions-e-round424.md <<'EOF'
...
`ssh jab@100.78.44.111` rc 0, `tailscale_online: true`,
EOF
```

Round 424's own prediction file quotes an ssh command line for the tailnet
address. A substring test — which is what `reachability_recover.transcript_probes`
does, correctly for its purpose — scores that as a login. `strip_heredocs`
removes heredoc BODIES and keeps opener lines, because a real invocation is
`ssh ... jab@100.78.44.111 'bash -s' <<'REMOTE'`, which opens a heredoc on the
line that makes the connection.

### 1b. The 3.26 MB that reached the transcript as 489 bytes

Worse, and in the direction that manufactures a null. Round 424's capture is

```
NUC=jab@100.78.44.111; KEY=$HOME/.ssh/id_ed25519; OUT=state/nuc-capture-r424
ssh -i $KEY $NUC 'journalctl ...' > $OUT/journal-pid1-full.txt
```

Three megabytes crossed the wire; the `tool_result` holds 489 bytes, because
the payload went to a FILE. Scored on stdout alone, **the single heaviest
round in the corpus reads as one of the lightest** — `bytes_returned` 14 077
against `bytes_landed` 2 896 862, a factor of 206. It is also not an scp
problem: round 424 used **no scp at all** (`n_scp: 0`), so a fix that special-
cased scp would have missed it entirely. `landed_paths` resolves redirect
targets and local scp/rsync destinations, expands one level of shell variable
(`$OUT`), and stats them against the tree as it stands; a path that no longer
exists is reported `unresolved`, never zero.

The corpus's dose range after the fix: `n_logins` 2..32, `box_seconds`
2.0..593.2, `bytes_landed` 0..2 896 862. Three orders of magnitude of dose.

---

## 2. THE HEADLINE: the dose-response is NULL, and the unstratified version
   is a measurement of the box's power switch

Every round is scored over the SAME window length — 3601 s anchored 300 s
before its first contact, which is round 466's own `[-300, +3300]` observer
window — because a heavy round works longer, and window length is itself a
dose.

Pooled over all 42 scorable rounds the answer is emphatic and wrong:

```
n_calls   rho +0.418   p 0.0062        <-- "the observer costs the box"
n_logins  rho +0.415   p 0.0066
```

**It is the power switch.** Ten of those 42 windows have ZERO sar buckets,
because the box was down and the record has nothing there. A down round's
response is zero by construction, and a down round also makes two probe calls
instead of fifteen. Pooled, that pairs *few calls* with *zero swap* for a
reason that has nothing to do with cost. `score_windows` now classifies every
window `full` / `partial` / `none` against the buckets the record actually
holds, and the primary table is the **28 full-record windows** only:

| term | kind | rho | p (20 000 permutations) |
|---|---|---|---|
| `n_logins` | dose | +0.257 | 0.185 |
| `n_calls` | dose | +0.241 | 0.214 |
| `box_seconds` | dose | +0.155 | 0.432 |
| `bytes_returned` | dose | +0.096 | 0.624 |
| **`bytes_landed`** | **dose** | **−0.277** | **0.155** |
| `bytes_moved` | dose | −0.002 | 0.993 |
| `local_calls` | **control** | −0.328 | 0.087 |
| **`local_bytes`** | **control** | **−0.399** | **0.037** |
| `transcript_bytes` | **control** | +0.373 | 0.051 |

**No dose reaches p ≤ 0.05. The two terms that come closest are CONTROLS** —
`local_bytes` at p 0.037 and `transcript_bytes` at p 0.051, neither of which
can touch the box. And the dose that most directly measures *what the round
did to the box*, `bytes_landed`, points the **wrong way**: rounds that pulled
more data off the machine had *less* swap in their windows.

The null is the permutation of the pairing — which dose belongs to which
window — holding both marginals exactly fixed. Nothing is assumed normal,
which matters when a single 2.34 GiB bucket dominates the response and the
response's median is **zero**.

**Verdict: NULL.** Round 466's observer coincidence is not shown to be causal
by a dose-response test. The unstratified table is kept in the report under
the key `dose_response_UNSTRATIFIED_do_not_quote`, with its warning attached,
because the size of the error is itself the finding.

### 2a. Cost without work

Round **238** made 4 calls, landed 0 bytes, and its window holds a costly
bucket worth **256.7 MB** of swap-out. Round **214**: 4 calls, 0 bytes,
47.6 MB. Round **286**: 6 calls, 0 bytes, 79.9 MB. Meanwhile round **424**,
which pulled 2.9 MB off the box, is not scorable at all — see §5.

---

## 3. Three nulls, each fixing the last, each moving the p-value the same way

The window-level question — *do E rounds happen at expensive moments?* — is
not the dose-response, and it took four attempts to ask honestly. Same 28
windows every time; only the null's SUPPORT changes.

| null | what it may draw | costly buckets: obs vs null | p |
|---|---|---|---|
| 1. random circular shift, whole span | anywhere in 08-23..09-01 | 14 vs 7.03 | 0.072 |
| 2. whole-day shifts, whole span | 9 offsets, time-of-day preserved | 14 vs 7.00 | 0.000 (0/9) |
| 3. random shift, **round days only** | 08-26..08-31 | 14 vs 6.71 | **0.0095** |
| 4. **coverage-conditional rate** | round days, scored only where the record covers | 0.393 vs 0.277 | **0.128** |

Null 1 and 2 may place the round train on **2026-08-23 and -24, where no E
round can occur** — the driver log begins with round 152 on 08-26 — and those
two days carry the record's largest bucket. Null 3 fixes that and the effect
gets *stronger*, to p 0.0095, which is where a less careful round would have
stopped.

Null 3 is wrong in the mirror direction. Inside 08-26..08-31 the box was
**down for hours** (rounds 184/190/196, and the whole 298→346 outage), and a
window shifted onto downtime has no buckets and therefore cannot hit a costly
one. A null free to land on the record's holes is being asked "are your
windows on live stretches?", to which the answer is trivially yes.

Null 4 scores a RATE over the windows each draw places on fully-recorded
ground, so observed and null are the same quantity and the holes cancel:
**11/28 = 0.393 observed against a null mean of 0.277, p 0.128. Not
significant.** Every correction to the null's support moved the answer the
same way.

**One more thing null 1 got wrong that has nothing to do with support.** Its
BYTES comparison reads `observed 2.383 GB vs null mean 4.567 GB` — the round
windows look *below* chance. The null's **median is 2.336 GB**, essentially
equal to the observation. The mean is inflated by the draws that happen to
cover the 2.34 GiB bucket. A heavy-tailed null reported by its mean alone
inverts the sign of the reader's conclusion, and `null_median_*` is now
reported alongside every mean.

---

## 4. Round 466's OWN statistic under the corrected null — and the split
   that reconciles everything

Round 466's headline was population-level, not window-level: session scopes
name 29 of 52 costly buckets against a shift null of 6.70. Does that survive?

Re-run with the same coverage-conditional rate null (`shift_null_covered`),
2000 draws:

| population | fires | distinct-bucket p (r466's null) | fires landing on covered ground | rate obs | rate null | **p** |
|---|---|---|---|---|---|---|
| published (`Starting` .service) | 647 | 0.0005 | **309 / 647 = 47.8 %** | 0.168 | 0.051 | **0.056** |
| widened, WITH session scopes | 2088 | <0.0005 | 1685 / 2088 = 80.7 % | 0.201 | 0.053 | 0.000 |
| widened, WITHOUT session scopes | 687 | 0.0005 | 311 / 687 = 45.3 % | 0.174 | 0.051 | 0.055 |
| **session scopes ONLY** | 1401 | <0.0005 | **1374 / 1401 = 98.1 %** | 0.207 | 0.053 | **0.0010** |

Two things fall out. **The scope population's association survives** the
correction at p 0.0010. **The published SERVICE population's does not** — it
drops from p 0.0005 to p 0.056. And the reason is visible in the middle
column: services spend **more than half their fires on ground the record does
not cover**, scopes almost none. The distinct-bucket null never saw that
asymmetry.

### 4a. The split: 41 % of the box's logins are ours, not "the scopes are ours"

Round 466 wrote *"the scopes are this program's own footprints"* on a
**probe-side** rate: 33 of 35 reachability-log probes had a scope within
120 s. That direction cannot bound the fraction of the box's logins that are
ours, because the log holds one row per ROUND and a round makes many logins.
The transcripts hold every call, so the scope-side rate is answerable:

- 1401 session scopes; **292 predate the transcript corpus** (it begins
  2026-08-26; the journal begins 08-23) and are reported UNTESTABLE, not
  unmatched.
- Of the 1109 testable: **454 ours (40.9 %), 655 not ours (59.1 %)**, at
  ±120 s. Chance match rate for that window set is **4.23 %**, so the
  identification is a 9.7× enrichment and is not in doubt — but **the
  majority of this box's logins are not this program's.**

Split the population and run the corrected null on each half:

| half | n | landed | rate obs | rate null | p (2000 random shifts) | p (whole-day, identity excluded) |
|---|---|---|---|---|---|---|
| **ours** | 454 | 442 | **0.2172** | 0.0468 | **0.0000** | **0.0000** (0 of 8) |
| **not ours** | 655 | 642 | 0.0421 | 0.0529 | 0.4650 | 0.1111 |

**The entire association is carried by this program's own logins. The other
655 logins on the box behave exactly like chance.** A time-of-day confound is
ruled out separately: whole-day shifts preserve time-of-day exactly and `ours`
survives them.

*(The whole-day p for `ours` is 0.1111 as printed and 0.0000 once the identity
draw is removed. `ours` spans seven days, so the offset 7 × 86400 IS the
identity mod its own span and ties the observation by construction. Round 466
added `n_identity_draws` to `shift_null` for exactly this and it had never
fired; here it decides a published number. `shift_null_covered` now reports it
too — and only because mutation testing found the field untested, see §6.)*

### 4b. The lead–lag profile: what separates a cost from a shared clock

A shift null rejects chance. It cannot distinguish a cost from a common
period, because a shared clock is an alignment and a shift destroys alignment
either way. A cause has a shape a coincidence does not: it peaks at zero and
it is not symmetric — memory pressure created by a login is in that login's
bucket and the ones AFTER it, never twenty minutes before.

Costly-bucket rate by displacement, in 600 s buckets:

```
                 -6    -5    -4    -3    -2    -1     0    +1    +2    +3    +4    +5    +6
ours           .011  .015  .007  .027  .029  .054  .217  .099  .061  .016  .000  .000  .002
not ours       .015  .022  .014  .008  .003  .025  .042  .014  .003  .002  .015  .029  .075
services       .020  .033  .033  .029  .020  .047  .168  .022  .025  .028  .025  .034  .020
```

- **ours**: a sharp peak at zero, ~14× the far field, with a right shoulder
  (+1 = 0.099, +2 = 0.061) about twice the left (−1 = 0.054), decaying to
  nothing by +3. That is the shape of a cost that persists ~20 minutes.
- **not ours**: no peak at zero at all (0.042 ≈ its own baseline); the profile
  maximum is elsewhere. Consistent with §4a.
- **services**: a peak at zero of the same height as ours, and **no shoulder
  whatever** (+1 = 0.022) — co-location inside a bucket, with nothing after
  it. A different phenomenon wearing the same peak.

**The honest caveat, and it is a real one.** A round makes ~12 logins spread
over 10–25 minutes, so a scope at *t* usually has siblings at *t*+600 and
*t*+1200. If one bucket in a round's window is costly, an early scope's +1
offset lands on the same bucket a later scope's 0 offset does. Some of the
right shoulder is that within-round clustering rather than persistence. The
peak at zero is not affected by this; the asymmetry is, and is reported as
suggestive, not established. Deconfounding it needs a per-round-window
resampling that this round did not build.

### 4c. So what is the finding?

Three results that have to be held together:

1. At the resolution of a **login instant** (n = 454), this program's logins
   sit in costly swap buckets at 4.6× chance, p < 0.0005, robust to whole-day
   shifts, with a peak-at-zero profile. That is strong.
2. At the resolution of a **round window** (n = 28), there is nothing:
   p 0.128.
3. At the resolution of **how much a round did** (n = 28), there is nothing,
   and the closest terms are controls that cannot touch the box.

(1) and (2) are not in conflict — 28 hour-long windows is a far coarser
instrument than 454 second-precise instants, and the effect is concentrated in
the bucket containing the login. (1) and (3) together say something specific:
**if the logins cost memory, the cost is per-login and roughly fixed, not
proportional to the work.** That is a physically plausible shape on a box at
92 % memory used — sshd fork, PAM, a logind scope — and it is exactly what the
dose-response was built to detect and did not find, at n = 28 with a
zero-median response. This round claims the coincidence is real and
fine-grained; it does not claim the cause is established.

---

## 5. The observer's largest intervention is the one the instrument cannot see

Round 424 pulled 2 896 862 bytes off the box — the heaviest dose in the
corpus by a factor of 9. Its window scores **`record_coverage: partial`,
1 bucket**, and is excluded from every primary table. The reason is the
finding: **round 424's capture IS the end of the record.** The sar file it
copied stops at the moment it copied it, so the one round whose intervention
was big enough to test is the one round the data cannot describe.

Round 430 is the same, worse: `record_coverage: none`. And the six most recent
E rounds (442, 448, 454, 460, 466, 472) are untestable because the box has
been down since 2026-09-01 and no capture has been taken since.

Twelve of 54 E rounds are untestable and are listed as such rather than scored
as zeros — six for having no NUC contact in their transcript at all
(316, 322, 328, 340, 346, 436), six for falling outside the pooled window.

---

## 6. Round 466 item 2: the `session-*.scope` exclusion decision

Round 466 refused to take this alone and said why: `sysstat-collect` is
excluded because it WRITES the bucket; a session scope would be excluded
because it IS the observer. Both tables, `perturbation.py exclusion`:

| population | fires | costly named | bytes named | share |
|---|---|---|---|---|
| published (`Starting` .service) | 647 | 19/52 | 9 039 863 808 | 26.70 % |
| widened (service,scope) **WITH** session scopes | 2088 | 44/52 | 31 839 289 344 | **94.04 %** |
| widened (service,scope) **WITHOUT** session scopes | 687 | 19/52 | 9 039 863 808 | **26.70 %** |
| session scopes ONLY | 1401 | 29/52 | 24 463 687 680 | 72.25 % |

Excluding costs **−25 costly buckets, −22.80 GB, −67.34 percentage points**.
Note the third row: dropping session scopes from the widened population
returns it *exactly* to the published population's numbers — the other 40
non-session fires the widening adds contribute nothing.

**DECISION: do NOT exclude `session-*.scope`, and the exclusion is not
implemented anywhere.** `LEDGER_EXCLUDE_UNITS` is untouched and a test
(`test_reading_the_exclusion_tables_does_not_apply_the_exclusion`) holds it at
`("sysstat-collect",)`. Three reasons, in order of weight:

1. **It would be a silent 67-point move.** A default exclusion changes a
   published figure with nothing in any round file saying so.
2. **Round 466's own argument stands, and this round strengthened it.** If
   this program's traffic costs the box four gigabytes of swap, that is a fact
   about the deployment. §4a makes it *more* worth naming, not less: it is
   specifically OUR logins that carry the association, and specifically the
   other 655 that do not.
3. **The reason for excluding got weaker.** `sysstat-collect` is excluded
   because its fire and the bucket's cost are the same event. A login is not
   that: §4b's profile has a right shoulder, i.e. the cost outlives the fire.
   Excluding it would be hiding a candidate cause, not removing a tautology.

What the exclusion IS, is a reported table. Anyone quoting 94.0 % should quote
26.7 % beside it.

---

## 7. Tests, and what mutation testing found

`nuc/tests`: **946 → 995, all green**, 229.5 s on this 1-core box (the fast
check's nested pytest run is most of that). The round-472 file is 49 tests in
15 s.

**One test went red on its first run and the TEST was what was wrong.**
`test_the_stratifier_is_what_separates_the_two_answers` built its
"no association" stratum as `n_calls = 10 + (i % 2)` against
`swap = (i % 2) * 10` — a *perfect* rank correlation dressed up as a null. It
is fixed and the docstring records the mistake.

Then every falsifier was **mutation-tested**, because a green test that cannot
go red is not a falsifier. Ten mutations; the first pass killed seven and
**three survived**:

| mutation | first pass | why it survived | fix |
|---|---|---|---|
| drop the `via_variable` disjunct from `addressed` | **passed** | the disjunct is DEAD: a variable can only resolve to a NUC target via an assignment in the same command text, which puts the literal address in that text anyway | removed the disjunct; `via_variable` kept as a reported field because `landed_paths` needs the expansion, with the environment-variable blind spot documented |
| drop the wrapped tail in `BucketMap.span_buckets` | **passed** | the test's wrap was 2000 s, and the pooled window opens at 14:02 on day 0, so the wrapped-in tail was EMPTY | wrap extended to 60 000 s, with an assertion that the tail is non-empty |
| stop counting `n_identity_draws` in `shift_null_covered` | **passed** | no test reached the field — and it decides §4a's published `ours` p-value | a test with explicit offsets including the identity |

All three are round 466's F1/F7 lesson recurring: *a falsifier that goes 0 red
because its branch is unreachable is a design problem, not a testing one.*
After the fixes, **10 of 10 mutations go red**, including a one-sided
permutation test, a position-based tie-break in `spearman`, an identity
`expand_vars`, and always-`full` record coverage.

The `BucketMap` self-check against `cost_ledger` (`verify`) is still
`identical: true` after this round added `_map_any`, `all_bucket_bytes` and a
bisect run index to the same constructor, and the new run index is pinned
against the per-second scan by `verify_runs`.

---

## 8. What this round did NOT do

- **Nothing on the box.** No ssh session succeeded.
- The lead–lag asymmetry is **not** deconfounded from within-round login
  clustering (§4b). The peak at zero is; the shoulder is not.
- `bytes_landed` resolves against the tree as it stands today. Files deleted
  since are `unresolved` and reported, but a round that pulled data and threw
  it away is under-dosed and there is no way to recover that from a transcript.
- The **`commit` channel** and the **`steal` channel** were not touched; every
  number here is the `swap` channel at `min_bytes` 4 825 665.
- Round 436's items 4, 5 and 9 are untouched for a fifth round.
- `--cap 196` and the E3 A/B are still blocked on the operator — **twenty-
  sixth** round unchanged.

## 9. Artefacts

- `nuc/dose_response.py` — the experiment (`dose`, `run --strict`).
- `nuc/perturbation.py` — `shift_null_covered`, `lead_lag_profile`,
  `session_exclusion_tables`, `is_session_scope`, and `BucketMap`'s
  `all_bucket_bytes` / `span_buckets` / `span_bytes` / run index /
  `verify_runs`.
- `nuc/tests/test_dose_response.py` — 49 tests.
- `state/nuc-capture-r472/` — `tailscale-status-r472.json`,
  `dose-response-r472.json`, `exclusion-tables-r472.json`,
  `leadlag-nulls-r472.json`.
- `nuc/predictions-e-round472.md` — banked before measuring; scored in §10.

---

## 10. Predictions, scored (D-013)

`nuc/predictions-e-round472.md`, banked 08:35Z before any instrument in this
round ran, with a §0 declaring the three reachability reads and the two file
inspections that preceded it. **8 HIT, 1 PARTIAL, 5 MISS of 14, plus the
no-basis item resolved both ways.**

| | prediction | outcome | |
|---|---|---|---|
| P1 | 25..31 of the 31 transcripts have a contact inside the span | 31 | **HIT**, on a wrong denominator — see below |
| P2 | 300..900 NUC invocations in total | 380 logins / 329 calls over the 42 scored | **HIT** |
| P3 | heaviest round by bytes returned is 424, then 400 | by `bytes_returned` it is **394**, then 208, 388, 376; 424 is mid-pack at 14 077 | **MISS** |
| P4 | per-round invocation count skewed, max ≥ 5× median | max 27 vs median 8 = **3.4×** (logins 32/9 = 3.6×) | **MISS** |
| P5 | ≥ 50 % of the 1401 scopes match a transcript call at ±120 s | **40.9 %** of testable (454/1109); 32.4 % of all 1401 | **MISS** |
| P6 | **the dose-response comes back NULL, p > 0.05** | no dose reaches p ≤ 0.05; strongest is `bytes_landed` at p 0.155 | **HIT** |
| P7 | `n_invocations` no stronger than the byte/second doses; if any dose hits p ≤ 0.05 it will be `box_seconds` | `n_logins` (+0.257) **is** stronger than `box_seconds` (+0.155) and `bytes_returned` (+0.096), weaker than `bytes_landed` (−0.277); second clause never triggered | **PARTIAL** |
| P8 | a bottom-quartile-dose round has a costly bucket in its window | rounds 214, 238, 286 — 238 at 4 calls, 0 bytes landed, **256.7 MB** | **HIT** |
| P9 | untestable costly buckets strictly > 19, in 19..32 | **22** before 2026-08-26 (and exactly 19 before 08-25, reproducing round 466) | **HIT** |
| P10 | I will decide DO NOT exclude, shipping both tables | decided, §6 | **HIT** |
| P11 | excluding returns coverage to 19/52 and 26.7 % | **19/52, 26.70 %**, byte-exact | **HIT** |
| P12 | `BucketMap.verify` still `identical` | green after three structural additions | **HIT** |
| P13 | tests 946 → 971..986 | **995** | **MISS** (overshot by 9) |
| P14 | ≥ 5 falsifiers, ≥ 1 comes back 0 red on its first run | 49 tests; **three could never go red at all**, found by mutation, not by first-run silence | **HIT**, and worse than predicted |
| P15 | declared no-basis: the sign of any correlation; whether scp payload is recoverable from a transcript | sign is **negative**; scp payload is not in stdout but IS recoverable by resolving redirect and scp destinations — and the real defect was `ssh > file`, not scp at all | resolved, not scored |

**P1's denominator was wrong and the honest number is better.** §0 recorded
"transcripts EXIST for 31 E rounds" from a hand-picked list. **All 54 E rounds
in the driver-log population have a transcript on this box.** 42 of the 54
scored; the other 12 are untestable for stated reasons (§5). The prediction is
a HIT against the set it named and a misreading of the corpus, and the
misreading is the more useful half.

**P3 and P4 are the same miss.** Both assumed round 424 would dominate the
dose because it captured 3.26 MB. It does dominate — on `bytes_landed`, the
dose this round had to *invent* after finding that stdout undercounts a capture
round by 206× (§1b). On the dose I predicted with, `bytes_returned`, round 424
is unremarkable, because what makes a round heavy never passes through
`tool_result` at all. Both misses are the same discovery arriving as a
prediction failure.

**P6 is a HIT for the wrong reason and that matters.** The reasoning banked
with it was "a 1-second login cannot move 2.34 GiB". That is not what produced
the null: the unstratified table says rho +0.418 at p 0.0062, and only the
record-coverage stratification turns it null (§2). Had this round not built the
stratifier it would have published the opposite result with the same prediction
scored a MISS. A correct prediction from a wrong mechanism is not a
confirmation of the mechanism.

**P14 was optimistic in the wrong direction.** It predicted one falsifier would
come back 0 red on its first run, as two of round 466's seven did. Three came
back permanently green — they could not have gone red for ANY code change,
which first-run silence does not reveal. Mutation testing does. That is the
practice this round would keep.
