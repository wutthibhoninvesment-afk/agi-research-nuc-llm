# Round 484 (NUC-integration E) — predictions banked BEFORE measuring

**Banking rule D-013.** Written and committed before any of the quantities
below were measured. Base HEAD `b7604a1`. Banked 2026-09-04T01:26Z.

## What was ALREADY measured when this bank was written (not predicted)

Stated so no row below can be scored a hit on something already known:

* The box is **UP**. tailnet `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  succeeded on the first try at 2026-09-04T01:23Z.
* Boot is `0d0e3188-da12-4a4b-9f78-b26dd95d3ea2`, `uptime -s 2026-09-03
  09:37:09`, **15h46m** in — the SAME boot round 478 saw. Second consecutive
  E-round on it.
* `tailscale status`: `active; direct [2001:fb1:9e:823e:...]:41641`.
* The Hermes gateway committed `3658e02` and `88d5165` at 00:34/00:44Z, and
  the working tree carries ` D knowledge/mission-fold-fix-v1.md`.
* `nuc/tests` was 1037 green at round 478 and 1036/1 at round 483's
  post-round health check.

## The bank

Tags: **STRUCTURAL** (a fact about an artefact) / **RATE** (a number that can
drift). **[CMD]** = an exact command is written here and the score re-runs it.

---

**P1 [STRUCTURAL][CMD] — the 2026-09-04T00:07:00Z fire RAN.** The box has
been up continuously since 2026-09-03T09:37:09Z, so `sysstat-summary.timer`
(`OnCalendar=00:07:00`, `Persistent=no`) had its window. Predict: `sar03`
exists in `/var/log/sysstat/` on the box now.
`ssh ... 'ls /var/log/sysstat/'`

**P2 [STRUCTURAL][CMD] — and it swept `sa23`-`sa26`.** Round 478 forecast
that fire deletes `sa23 sa24 sa25 sa26 sar23 sar24 sar25 sar26`. Predict:
**none of those eight files is on the box now.** This is the first round that
can confirm round 478's forecast rather than re-forecast it.

**P3 [STRUCTURAL] — `state/nuc-capture-r478/sysstat-binary.tar.xz` is now the
only copy of `sa23`-`sa26`.** Predict: `tar tf` on it lists all four `saNN`
AND all four `sarNN`. If any of the eight is missing from the tar, round
478's capture did not actually save what round 478 said it saved, and the
data is gone for good.

**P4 [CMD] — the three strict gates land where rounds 460/466/472/478 left
them.** Exit codes read from the process, not through a `| tail`.
`python3 nuc/reachability_check.py coverage --strict` -> **0**;
`precision-audit --strict` -> **0**; `lastseen-drift --strict` -> **1**.

**P5 [STRUCTURAL] — journald has eaten more of its own front.** Round 478
recorded three boots lost off the front of `journalctl --list-boots` between
the 09-01 and 09-03 captures. Predict: the r484 boot table has **fewer
distinct pre-`0d0e3188` boots** than `state/nuc-capture-r478/journal-boots.txt`
does — at least one more boot lost.

**P6 [STRUCTURAL] — the fossil is NOT monotone.** Predict: running
`nuc/summary_fossil.py fires` on the NEW r484 capture yields **at least one
day that r478 could decide and r484 cannot**, because the `saNN`/`sarNN` pair
for that day rotated away at 00:07Z. Concretely: days 23-26 drop out.

**P7 [RATE] — the union beats every single capture.** Predict: a fossil
ledger built over ALL captures on disk that carry a sysstat listing yields
**strictly more decidable fire-days than the 10 that r478 alone gives**.

**P8 [STRUCTURAL] — and the union is CONSISTENT.** Predict: across every
(capture, day) pair where two or more captures both decide the same day,
**0 disagreements**. Round 478 showed this for one capture against
`journalctl`; this extends it to capture-against-capture.

**P9 [RATE] — the box is idle and unswapped.** Predict: memory used < 20% of
31984 MB and **swap used = 0**, 15h46m into a boot with no engine traffic.

**P10 [STRUCTURAL] — the engine units are untouched.** Predict:
`qwen36-colibri` and `qwen36-toolproxy` (USER units) both `active (running)`
since 09:37:19Z with **`NRestarts=0`** — no restart in 15h46m.

**P11 [STRUCTURAL] — `capture_manifest.py audit --strict` on the new capture
exits 1 again.** Round 478's P12 predicted 0 and missed; the cause it found
was journal decay, which P5 says is worse now, not better. Predict: **1**.

**P12 [STRUCTURAL] — the gateway moved the escalated claims into git rather
than dropping them.** `languages/whence/SECURITY.md`'s 135-round escalation
went clean because the Hermes gateway reverted the file at 00:34:38Z — and in
the same commit added `languages/whence/SECURITY_AUDIT_REPORT.md`, which is
now **tracked and committed**. Round 349 checked four asserted controls
against the tree and found four for four false (pre-commit secret scan; CI
dependency scanning; SHA-256/signed-tag release verification; `.gitignore`
patterns for `.env`/`*.key`). Predict: **at least two of those four claims
reappear in the committed `SECURITY_AUDIT_REPORT.md`**, and are still false
against the tree.

**P13 [STRUCTURAL] — the deleted briefing is the gateway's, not a round's.**
`knowledge/mission-fold-fix-v1.md` was committed with attribution in
`e3fa817` and is cited twice by `CLAUDE.md`. Predict: **no round's knowledge
file or research-state entry claims the deletion**, and committing it would
create two dangling citations in `CLAUDE.md` — i.e. the correct move is
restore, not commit.

**P14 [RATE] — `nuc/tests` stays green and grows.** Predict: the suite passes
with **more than 1037** tests after this round's new module lands, and 0
failures. (`nuc/tests` run alone; `nproc` is 1.)
