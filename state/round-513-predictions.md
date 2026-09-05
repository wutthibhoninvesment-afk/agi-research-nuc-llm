# Round 513 (skills B) — prediction bank

Banked **before** any of the measurements below were taken. Written as `.md`
deliberately: `carryforward_check.find_banks` sweeps for `*prediction*` files
whose name ends in `.md`, and one of this round's own subjects is that a
`.json` bank is invisible to it (round 512's). Banking in `.json` here would
have made this file unaccountable by the very checker it is about.

Convention: STRUCTURAL = a claim about a mechanism (holds/fails);
RATE = a number with a band. Every baseline below was re-derived at HEAD
with the command printed beside it (round 433's rule).

## Baselines re-derived at HEAD (ed23dbc + 1 uncommitted registry line)

| # | Baseline | Command | Value at HEAD |
|---|---|---|---|
| B1 | case_coverage errors/warnings | `python3 skills/skill-authoring/scripts/case_coverage.py` | `1 error(s), 31 warning(s)`; 116 skills, 483 cases |
| B2 | carryforward totals | `python3 skills/skill-authoring/scripts/carryforward_check.py` | `187 bank(s) (+2 unnumbered), 185 scored, 3 unscored, 1 error(s), 33 warning(s)` |
| B3 | claim_check stale | `logs/corpus-evidence/round-512/claim_check.out` (re-run below) | `1 stale claim(s) of 391 checked` |
| B4 | the three ERROR ids | as above | P001 `red-debt-triage`; C001 `red-debt-triage/SKILL.md:144` path `/^`; K003 round 512 |
| B5 | last all-green skills-check | `logs/skills_health_round_510.log` | round 510, `0 error(s), 7 warning(s)` |

## Predictions

| id | class | claim |
|---|---|---|
| P1 | STRUCTURAL | The C001 phantom is caused by `=` being in `path_tokens`' split class `[\s=]+`. The same sed idiom written with any other character in place of `=` (`sed -n '/^Z* FAILURES/p'`) yields **zero** path tokens, because the `*` survives into the token and `TOKEN_PLACEHOLDER_RE` exempts it. The split destroys the evidence the exemption keys on. |
| P2 | RATE | Other Verification commands corpus-wide that produce a phantom path token by the same `=`-split mechanism: **0** (band 0–2). This is a one-instance defect, not a corpus-wide one. |
| P3 | STRUCTURAL | Copying round 512's bank to `predictions.md` does **not** silence K003; it changes the message to the ``bank` is X but the bank(s) on disk are Y` branch. The two branches share one cause and fixing only `find_banks`' extension set is not enough. |
| P4 | RATE | Bank-shaped files repo-wide that `find_banks` cannot see because they are not `.md`: band **2–6** (round 512's two are known). |
| P5 | RATE | Ledger entries whose `bank` field names a non-`.md` path: exactly **1** (round 512). |
| P6 | STRUCTURAL | `harness/readset.py blast` fed round 511's changed paths **does** implicate `skills/skill-authoring/scripts/test_case_coverage.py` — i.e. the instrument that would have warned the opener already existed and was not run. |
| P7 | STRUCTURAL | Same for round 512's changed paths and `test_carryforward_check.py`. |
| P8 | RATE | Wall clock of `corpus_check.py`'s nine FREE tiers (everything except `unit_tests`), serialised on this `nproc=1` box: band **40–150 s**; `unit_tests` alone was 509 s at round 512, so the free tiers are **< 25%** of the whole check. |
| P9 | STRUCTURAL | After the three fixes, `corpus_check.py` reports **0 error(s)** and the four red nodes go green. |
| P10 | RATE | New/changed test functions this round: band **14–25**. |
| P11 | RATE | case_coverage's WARNING count after `red-debt-triage` gets 3 positive cases: stays **31** (P004 for it is already counted; adding cases removes an ERROR, not a warning). |
| P12 | STRUCTURAL | The `red-debt-triage` P001 and the round-512 K003 have **different** root causes (a missing obligation vs a checker predicate), but the C001 and the K003 have the **same** one: a negative verdict computed on a filtered representation and worded about the raw one. |
