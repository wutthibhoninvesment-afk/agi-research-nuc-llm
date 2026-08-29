# Round 346 (NUC-integration E) — predictions, banked BEFORE measurement

Banked 2026-08-29 ~21:5x UTC by `claude-opus-5`, under house rule **D-013**
(predictions before measurements) — the very rule whose definition this round
is about to resurrect.

Already measured at banking time, so NOT predictions (recorded so nobody
scores them as such):

- `CLAUDE.md` is 13 lines with a `## Ground rules` heading and an empty body.
- `git log -- CLAUDE.md` lists exactly 3 commits: `ee30654` (42 lines,
  **body present**, including a `## Track E — NUC integration: HARD RULES`
  section that defines `D-013` verbatim), `e376750` (6 lines, body gone),
  `db684e1` (13 lines, body still gone).
- Therefore round 345's finding "the body predates this repo's git history;
  it was lost in the Mac→NUC migration" is **wrong**: the body is IN this
  repo's git history, at the initial commit, and was destroyed by the
  `AUTO-COMMIT v4` commit `e376750`.
- `ee30654:CLAUDE.md` gives the NUC's address as `192.168.1.42`;
  `CURRICULUM.md` says `192.168.1.37`; `nuc/reachability_check.py` uses a
  tailnet target `jab@100.78.44.111`. Three different addresses.
- Round 345's own repair/authorship rule: "Transcribing a definition that
  already exists is repair; writing the missing one is authorship."

## Predictions

**P1 (live, box state).** `reachability_check.py check --round 346` returns
verdict `down` — the 8th consecutive down E-round. Confidence 0.85. The box
has been down for 7 straight E-rounds (304→334) and nothing in the interim
suggests an operator power-on. If it is UP, this round pivots to the standing
"first up-round" checklist (`boot_probe` live sanity-check, item 4).

**P2 (live, box state).** If P1 holds, the `ambiguous` verdict is STILL not
observed (round 310's item 3 stays open). Confidence 0.93 conditional on P1.

**P3 (forensic — the interesting one).** `SPEC.md`'s missing decisions
**14–26 are ALSO recoverable from git history**, i.e. some ancestor commit
of `languages/whence/SPEC.md` contains a decisions list with entries beyond
13. Confidence **0.35**. Reasoning FOR: the same `e376750` AUTO-COMMIT
truncated `CLAUDE.md` by 36 lines, so a truncating migration is proven to
have happened in this tree, and a 13→27 numbering jump is exactly the shape
of a truncation. Reasoning AGAINST: round 345 read the decisions list and
described the jump as "never minted at all", and 27/28/29 are traceable to
rounds 338/342/344 — recent rounds that plausibly just picked wrong numbers.
Low confidence because these two stories are about equally good.

**P4 (forensic, generalisation).** Repo-wide, the number of OTHER markdown
sections that are empty today but were non-empty in some ancestor commit
(a `##`/`###` heading with no body, whose body exists in git history):
**1–4**, and `CLAUDE.md § Ground rules` is one of them. Confidence 0.6 on
the band. I expect this to be rare, not systemic: `e376750` was a single
destructive event, not a recurring process.

**P5 (tooling).** Adding a VCS-history probe to `xref_check.py`'s registry
resolution will change the X002 family's status from `empty` to a
*resurrectable* status, and will change **zero** other families' status.
Confidence 0.7 — X001 depends entirely on P3, X003's registry is derived
from live code and cannot be resurrected.

**P6 (restoration scope).** Of the ~10 operational facts in the recovered
`## Track E — HARD RULES` block, the number that are demonstrably STALE
today (contradicted by evidence elsewhere in the repo): **2–4**. Confidence
0.65. I am confident about the ssh address (`.42`); I expect the read-only
paths, the port-8001 prohibition, the allowed write paths and the two
endpoint ports to have survived unchanged, because every later E round keeps
restating them.

**P7 (citation closure).** Restoring `## Ground rules` with the `D-013`
token present clears the ENTIRE X002 family — 42 citations, 1 dangling id →
0 dangling. Confidence 0.8. The residual risk is round 345's §3.2 bug class
(a registry that returns the wrong TYPE): X002 is declared a *token*
registry, so a literal `D-013` in the section should satisfy it, but the
tool has never once been run against a NON-empty X002 registry — that path
is unexercised, exactly like `boot_probe`'s live path.

**P8 (mutation).** If a mutation-kill pass is run on the new probe code,
first-pass kill rate **80–100%**. Confidence 0.6.

## Scoring
Scored in `knowledge/round-346-*.md` and in the research-state entry. A
prediction whose scope is ambiguous at scoring time is recorded
**unscorable**, not argued into a HIT — round 345's P4 lesson.
