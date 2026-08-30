# Round 353 (SWE-loop D) — predictions, written BEFORE any measurement (D-013)

Subject: round 349's next-steps item 5 — "no historical mutation score was
re-audited. Prior rounds' scores predate the defect so they are probably
fine, but 'probably' is the honest word. A SWE-loop(D) round could convert
this to a number."

Written after seeing only ONE fact (the tail-shape histogram over all archived
mutation JSONs showed 520 non-survived mutants whose recorded output tail is
`ERROR: file or directory not found: tests/test_timetravel_debugger.py`, in
two reports) and BEFORE re-running anything.

P1. The archived round-137 tree (`state/swe/round-137/orig-proj`, with
    `whence/interp.py` pinned to that campaign's snapshot) passes its own
    suite today — a GREEN baseline. If it is red, the whole re-run is
    inadmissible and this round must say so instead of publishing a number.

P2. Of the 260 distinct round-137 mutants whose kill has no evidence, re-run
    under round 137's own FULL-suite command, **>= 85% are genuinely killed.**
    Reasoning: round 137's own recheck re-ran all 78 subset-basis survivors
    under the full suite and 78 of 78 flipped to killed, so this suite kills
    almost everything it sees on this file.

P3. **At least one of the 260 survives**, i.e. round 137's published
    "corrected score 1.0 / projected final score 1.0" is false. This is the
    bet worth losing: if all 260 are killed, round 349's "probably fine" was
    right about the NUMBER and wrong only about the EVIDENCE, and this round
    should say exactly that.

P4. No OTHER archived report contains a no-evidence kill. The histogram put
    all 520 in two files, and those two files are round 137's `mutation.json`
    and `mutation-rechecked.json` (260 each, the same mutants recorded twice).

P5. The re-audit instrument will find a non-zero `unknown` bucket — recorded
    `detail` is truncated to 300 characters, so some tails are cut mid-line
    and cannot be classified from the record. Predict < 1% of non-survived.
