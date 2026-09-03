# Round 472 (NUC-integration E) — predictions, banked BEFORE measuring

Rule D-013. Written 2026-09-03T08:35Z, before any instrument in this round ran
against any data. Scored honestly at the bottom of
`knowledge/round-472-*.md`.

## §0 — what was ALREADY read before this file was written

Declared so that nothing below is passed off as a prediction when it is a
reading. Everything in this section is OBSERVED, not predicted:

1. **Reachability, both documented paths, before any code ran.**
   - tailnet `ssh -i ~/.ssh/id_ed25519 -o ConnectTimeout=15 jab@100.78.44.111`
     issued 2026-09-03T08:32:08Z -> `Connection timed out`.
   - LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` at 08:32:32Z -> same,
     and `~/.ssh/id_ed25519_nuc` **still does not exist on this host**, so that
     path proves nothing either way.
   - `tailscale status --json` 08:33:02Z: `Online false`,
     `LastSeen 2026-09-01T18:27:56.1Z` — **byte-identical to rounds 448, 454,
     460 and 466**. So 436/442/448/454/460/466/472 is ONE outage and this is
     the SEVENTH consecutive down window.
   - CLAUDE.md's two-failure rule fired. **No ssh session succeeded; nothing
     was read from or written to the box; port 8001 was never contacted.**
2. Round 460 item 1 ran first: `coverage --strict` **0**,
   `precision-audit --strict` **0**, `lastseen-drift --strict` **1** (the
   documented 436->466 recompute, `-124 s`). Exactly the state round 466 left.
3. `status` at 08:33:10Z: confirmed **37h02m31s**, upper bracket 38h05m13s.
4. Round 466's addendum in `state/nuc-missions.md` (its next-steps list is
   this round's agenda) and its `population`/`observer` code in
   `nuc/perturbation.py` (`BucketMap`, `shift_null`, `observer_trace`,
   `observer_confounding`, `session_scope_sessions`).
5. The banked journal `state/nuc-capture-r424/journal-pid1-full.txt` spans
   **2026-08-23T14:02:08Z .. 2026-09-01T08:16:20Z**.
6. `logs/round-<N>.json` transcripts EXIST for 31 E rounds
   (154,160,166,172,178,202,208,214,220,226,232,238,244,250,256,262,268,274,
   280,286,292,352,358,364,370,376,382,388,394,400,424) and carry per-event
   `timestamp` plus `tool_use`/`tool_result` blocks. Rounds 124/130/136/142
   have NO transcript.
7. Capture-dir byte sizes on this host: r400 655 123, r424 3 264 310,
   r406 47 421, r430 44 072, r460/r466 ~8 272.
8. `nuc/tests` stood at **946 green** at the end of round 466 (its own claim,
   not re-run yet).

Nothing else has been computed. No dose has been extracted, no window swap
totalled, no null drawn.

## The round's job

Round 466's next-step **item 3**: the observer effect is a measured
hypothesis and it has an experiment. *If the logins cost the memory, the cost
should scale with what the round DID, not with the login count.* Plus item
**2**: the written `session-*.scope` exclusion decision, both tables
published.

## Predictions

**P1 (dose extraction, count).** Of the 31 E-round transcripts, the number
that contain >=1 NUC-targeting shell invocation AND whose invocations fall
inside the journal span will be **25..31**.

**P2 (dose extraction, volume).** Total NUC-targeting invocations summed over
those transcripts: **300..900**. (The journal holds 1401 session scopes over
the same span, and not all of them are this program.)

**P3 (which round is heaviest).** Ranked by bytes returned through
`tool_result`, the heaviest E round in the span is **round 424** (it scp'd
3.26 MB and dumped two journals). Second heaviest is **400**.

**P4 (skew).** The per-round invocation count will be strongly right-skewed:
**max >= 5x median**.

**P5 (session-scope match rate).** Matching journal session-scope starts to
transcript-derived invocation instants at +/-120 s, **>= 50 %** of the 1401
scopes will match. (Round 466 matched the other direction: 33/35 probes.)

**P6 — THE HEADLINE. The dose-response will come back NULL.** Across E-round
windows, the association between how much work a round did on the box
(`bytes_returned`, `box_seconds`) and the swap-out recorded in its window will
be **not significant, permutation p > 0.05**. Reasoning: a 1-second login
cannot move 2.34 GiB, round 466 said so itself, and the concentration it found
is more plausibly confounding (the driver's cadence coinciding with the box's
own periodic load) than causation.

**P7 (login count no better).** `n_invocations` will not correlate more
strongly than the byte/second doses. Both near null. If ANY dose reaches
p <= 0.05 it will be `box_seconds`, not `n_invocations`.

**P8 (cost without work).** At least one E round whose dose is in the bottom
quartile will have a costly bucket inside its window — i.e. an expensive
window with a nearly-free round in it.

**P9 (the untestable set GROWS).** Round 466 had 19 costly buckets untestable
because the reachability log starts 2026-08-25. The transcript corpus starts
LATER (round 154, 2026-08-26T17:19Z), so the dose analysis's untestable set
will be **strictly larger than 19**, in the range **19..32**. Reporting them
as negatives would manufacture them.

**P10 (the exclusion decision).** I will decide **DO NOT exclude
`session-*.scope` from the fire population by default**, and ship the
exclusion as an explicit opt-in with both tables published — consistent with
round 466's own "hiding it is worse than naming it". Excluding by default
would silently move a published 94.0 % coverage number.

**P11 (both tables move a lot).** With session scopes excluded from the fire
population, costly-bucket coverage of the widened population falls from
**44/52** back to at or near the service-only **19/52**, and named bytes from
**94.0 %** to at or near **26.7 %**.

**P12 (`population --verify` still clean).** The `BucketMap` self-check
against `cost_ledger` is still `identical: true` for every population at HEAD.

**P13 (tests).** `nuc/tests` goes **946 -> 971..986**, all green. Runtime of
the full file set under 260 s on this 1-core box.

**P14 (falsifiers).** I will write >= 5 falsifiers for the new code and **at
least one will come back 0 red on its first run**, as two of round 466's seven
did — and the fix will be to make the branch reachable, not to delete it.

**P15 (no-basis, declared).** I have **no basis** to predict (a) the sign of
the correlation if one appears, or (b) whether `scp` payload bytes are
recoverable from a transcript at all (scp writes to a file, not to stdout);
these are recorded as open and will be resolved, not scored.
