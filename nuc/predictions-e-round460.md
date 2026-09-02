# Round 460 (NUC-integration E) — predictions banked BEFORE measuring

Banked 2026-09-02T19:35Z, before running any instrument this round and before
opening any transcript. Rules: round 436's item 7 (an honest bank says "I have
no basis here" rather than guessing) and D-013 (predict, then score misses).

## 0. Already observed before this file existed — NOT predictions

Reachability was probed first, because CLAUDE.md's two-failure rule gates the
whole round on it. Recorded here so the bank cannot be read as having called it:

- tailnet `ssh -o ConnectTimeout=12 -i ~/.ssh/id_ed25519 jab@100.78.44.111` at
  2026-09-02T19:33:25Z -> `Connection timed out`.
- LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` at 19:33:37Z -> same, and
  the key still does not exist on this host.
- `tailscale status --json`: `Online false`, `LastSeen 2026-09-01T18:27:56.1Z`
  — byte-identical to rounds 448 and 454. Box DOWN; fifth consecutive down
  window (436/442/448/454/460), one continuous outage.

## 1. `reachability_check.py coverage --strict` (round 454's item 1, run first)

**P1.** Exit 0, no holes. **P2.** `n_owed` is 51 and `n_covered` is 51 — round
454 measured 50/50 and then appended its own row, and round 460 is the highest
E round so it is exempt in flight. Confidence: high on P1, medium on P2 (I am
guessing at how `coverage` counts the in-flight round into `n_owed`).

## 2. The `precision` field

`reachability_recover.record_from_probes` writes `"precision": "precise"` as a
constant on every recovered row.

**P3.** Nothing reads it. `grep -n 'precision' nuc/reachability_check.py`
returns no consumer in the witness or summarize paths — it is a write-only
field, put there by round 454 in anticipation of exactly the coarse-LastSeen
work this round is picking up. Confidence: medium-high (I have read
`reachability_recover.py` in full and `_gap_witness` in full, and neither uses
it; I have NOT read the other ~2000 lines of `reachability_check.py`).

## 3. Recovered rows

**P4.** The live log holds exactly 7 rows whose `source` matches
`transcript-r*` — round 454 recovered 190/220/226/250/280/292/442, and 148 has
no transcript. **P5.** All 7 carry `tailscale_last_seen_utc: null`.

## 4. The coarse LastSeen in round 190's transcript

**P6.** `logs/round-190.json` contains a `tailscale status` plaintext line for
`pgain-nuc` reading `offline, last seen 3h ago` (round 454's prose quotes it).

**No basis, and I will not guess:** whether ANY of the other six recovered
rounds (220/226/250/280/292/442) carries a coarse `last seen` rendering. I have
not opened those transcripts and round 454's prose names only 190. I will
report what the six hold. This is the shape round 436's item 7 asked for.

## 5. The tailscale plaintext renderer (to be calibrated live, offline)

The conversion "3h ago" -> a bounded interval needs the renderer's contract.
This host's own `tailscale status` + `--json` give ground-truth pairs.

**P7.** The renderer emits ONE integer and ONE unit from {s, m, h, d} — the
largest unit that yields a non-zero integer — and never a compound
("1d 1h ago"). Basis: the four offline peers on this host render `3m`, `1d`,
`13d`, `31d`. Confidence: medium-high.

**P8.** It TRUNCATES (floor), not rounds. Basis is weak and I am saying so:
`pgain-nuc` at `LastSeen 2026-09-01T18:27:56.1Z` read at ~19:33Z is 25.1 h old
and renders `1d`, which floor and round-to-nearest both produce. The `3m` peer
is the one that can discriminate. Confidence: LOW — this is the prediction I
most expect to lose.

**P9.** At least one of the four offline peers on this host will discriminate
floor from round-to-nearest (i.e. its true age falls in a range where the two
rules disagree). Confidence: low.

## 6. The up-side witness regression (round 454's item 3, latent)

Round 454 fixed the DOWN side of the split-gap bug and said the UP side is
"latent and unexhibited". Reading `_up_gap_witness`, the mechanism is that a
missing `boot_utc` on either endpoint returns WITNESS_NONE unconditionally.

**P10.** The regression reproduces on a synthetic 3-record up streak
A(boot_utc)-M(no boot_utc)-B(boot_utc, same boot): with M absent the A->B gap
scores `reboot_only` via `boot_utc_unchanged`; with M inserted, BOTH halves
score `none`, so inserting an observation increases `unobserved_total_s`.
Confidence: high — this is a code reading, not a guess.

**P11.** `bounded_gap_count` on the live log is 0, so the BOUNDED form of the
same regression has no live instance (round 454 says so; I am re-deriving it).

## 7. Suite state at HEAD, before this round's edits

**P12.** `nuc/tests` is 869 tests, all green. **P13.** `nuc-checks` passes
(ninth consecutive, 442-460).

## 8. After this round's edits

**P14.** The down-side `unobserved_total_s` stays 0.0 after appending round
460's row: the new row carries a real LastSeen, so the 454->460 gap is
witnessed by the direct rule and needs no forward lookup.

**P15.** Converting round 190's coarse reading into a bounded interval will NOT
change `unobserved_total_s` by itself, because round 190's row is an endpoint
of gaps that round 454's forward rule already witnesses. The value of the work
is that the interval is available and sound, not that it moves a number today.
Confidence: medium-low — I have not looked at which gaps 190 bounds.

---

# SCORING (written after all measurements, round 460)

**13 HIT, 1 PARTIAL, 0 MISS of 14. One declared no-basis item resolved.**

| # | prediction | result | measured |
|---|---|---|---|
| P1 | `coverage --strict` exit 0 | **HIT** | rc=0 |
| P2 | `n_owed` 51, `n_covered` 51 | **HIT** | exactly that |
| P3 | `precision` is a write-only field | **HIT** | 3 producers, 0 consumers; one `assert record["precision"] == "precise"` in the whole suite |
| P4 | 7 `transcript-r*` rows | **HIT** | 190, 220, 226, 250, 280, 292, 442 |
| P5 | all 7 carry `tailscale_last_seen_utc: null` | **HIT** | `{None}` |
| P6 | round 190's transcript says `offline, last seen 3h ago` | **HIT** | twice — 07:57:03Z and 08:03:21Z, tx 10296 and tx 5304 |
| — | *no basis:* do the other six carry a rendering? | **RESOLVED** | **none of them.** The `~40-46m` strings in five of the six are round 184's prose quoted forward, not a status line |
| P7 | one integer, one unit, no compound form | **HIT** | 4/4 peers |
| P8 | the renderer FLOORs (banked at LOW confidence) | **HIT** | macbook 7.638m→`7m`, REDMI 13.7045d→`13d` |
| P9 | at least one peer discriminates floor from round | **HIT** | two do |
| P10 | the up-side split-gap regression reproduces | **HIT** | `[reboot_only]` → `[none, none]` on insertion |
| P11 | `bounded_gap_count` is 0 on the live log | **HIT** | 0 |
| P12 | 869 tests, all green at HEAD | **PARTIAL** | 869 collected is right. "All green" is **not verifiable**: a pristine `git worktree` gives 11 failed / 857 passed because `.gitignore:20` excludes `logs/round-*.json`, which seven of the log's rows are pinned against. With the transcripts symlinked in: 866 passed, 2 failed (both environmental), 1 skipped |
| P13 | `nuc-checks` passes, ninth consecutive | **HIT** | PASS |
| P14 | down-side `unobserved_total_s` stays 0.0 | **HIT** | 0.0 across all four down streaks, including 436→460 |
| P15 | round 190's bracket moves no published number (banked at medium-LOW confidence) | **HIT** | `continuity` scalars byte-identical; only `witness_source` changed, 184→190 `tailscale_last_seen_forward` → `tailscale_last_seen` |

## What the bank got right about itself, and what it did not

**The low-confidence flags were calibrated.** P8 was banked at LOW ("the
prediction I most expect to lose") and P15 at medium-low; both hit. Flagging
weak evidence did not make the prediction wrong, it made the round willing to
go and measure — the calibration read `tailscale status --json` against the
plaintext on four peers rather than assuming, and that measurement is what
makes §2's bracket defensible rather than plausible.

**P6 was nearly scored a MISS by a bad instrument.** The first grep over round
190's transcript returned four `~40-46m` hits and, further down, two `3h ago`
hits; on the strength of the first line I wrote "round 454's prose is WRONG"
before reading the rest. The `~40-46m` strings are round 184's prose being
quoted forward by later rounds. **A phrase grep over a transcript finds
quotations of observations as readily as observations.** The extraction that
decides anchors on the `pgain-nuc` status line
(`transcript_lastseen_readings`), not on the phrase.

**P12 is the honest failure, and it is a process failure, not a forecast
failure.** I predicted a baseline I had not measured and then could not measure
cleanly, because the round had already started editing. The rule that would
have caught it is one this program already has: measure the baseline in a
pristine worktree BEFORE touching the tree. Doing it afterwards is what
surfaced §5 — so the process failure paid for itself once, which is not a
reason to repeat it.

**The no-basis clause earned its place.** Round 436's item 7 asked for a bank
that writes "I have no basis here and will report what it holds" instead of
guessing. Used once, on the six recovered rounds' transcripts. The answer —
none carries a rendering, and the strings that look like renderings are
quotations — was not derivable from anything the state file records. Five
guesses there would have failed as one.
