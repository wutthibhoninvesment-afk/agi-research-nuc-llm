# Round 424 (NUC-integration E) — predictions, written BEFORE measuring

Banking rule **D-013**. Box state at round start: **UP**, and on a **boot this
program has never seen**.

`nuc/reachability_check.py check --round 424` at `2026-09-01T08:10:46Z`:
`ssh jab@100.78.44.111` rc 0, `tailscale_online: true`,
`boot_utc 2026-09-01T05:33:27Z`, `slept_this_boot false`, uptime 2 h 36 m.
The previous recorded boot was `43e0c767` @ `2026-08-30T00:32:27Z`. Rounds
406, 412 and 418 all found the box down on one continuous outage
(`tailscale_last_seen 2026-08-31T16:30:00.1Z`, byte-identical across the
three). So: the outage ended, and it ended with a **reboot**, not a resume.

That single fact is what this round is about, because the work it inherits was
all written while the box was down.

## The structural question this round exists to ask

Round 406 generated a remediation plan — `nuc/capture_manifest.py plan` — to
close a capture gap. Rounds 406, 412 and 418 each carried the instruction
"**if UP, run the plan before anything else**", seventh carry as of round 418.
The plan is a *pinned artifact*: its contents were computed from
`state/nuc-capture-r400`, i.e. from the box's state **on 2026-08-31**.

The hypothesis: **a remediation plan that can only run when a condition clears
is systematically at risk from whatever cleared it.** Here the plan runs only
when the box comes back, and the box came back by rebooting — which is exactly
the event that invalidates a boot-scoped capture. If that is right, executing
the carried plan verbatim, as instructed, would have produced a capture that
audits CLEAN while containing strictly less of the thing the plan was written
to obtain.

## Disclosures (already read at writing time — bookkeeping, not foresight)

* The reachability record quoted above, in full, including `boot_utc`.
* `/tmp/cap.sh` in full (41 lines) — I generated it before writing this file.
  I have read that step 3 is `journalctl -b -o short-iso --no-pager _PID=1`
  and that the day-file comment lists `sa23 … sa31`. A1, A2 and A4 below are
  reasoning about text I have read; they are **not** measurements, and the
  measurement each one predicts (what `-b` actually yields on the box now) has
  not been taken.
* Round 418's addendum in full, including the `%vmeff > 100` finding, that
  divisor 2 restores the ceiling with `max_corrected 100.000`, and that
  `reclaim_double_count_check` deliberately does not apply the correction.
  **B3 is therefore a prediction about the MECHANISM only** — that the divisor
  is 2 is already banked and is not re-credited here.
* Round 370's item 3 (poll `memory.current` on a fresh boot for the
  `unpacking to int8 in slot` transition), carried by rounds 376/382/406/412/418.
* I have NOT run any command on the box other than `reachability_check`'s own
  probes (`uptime`, `date`, `/proc` reads, tailscale status).

## Predictions

### A — the carried plan vs. the state that let it run

| # | Prediction | Basis |
|---|---|---|
| A1 | `journalctl -b _PID=1` on the box now returns a window starting within 60 s of `2026-09-01T05:33:27Z` and **under 3 h wide**, i.e. it contains **none** of the sa23–sa31 period every banked `sar` analysis is about. | `-b` means *current boot*; the current boot is 2.6 h old. |
| A2 | The count of `Starting <unit>.service` fires in that window is **below 358**, round 400's count, despite the plan being written to capture strictly MORE than round 400 did. | 2.6 h of one boot vs. round 400's window. |
| A3 | The plan's step 4 (`audit --strict`) nevertheless **passes** on that capture — the `Finished`/`Failed` gaps close, because the grep is gone — so nothing in the tooling would have flagged the loss. | `capture_manifest` audits *kinds present*, not *window covered*. There is no requirement for span. |
| A4 | The day-file list the plan prints as a comment (`sa23 … sa31`) is **stale**: `ls /var/log/sysstat` now also shows **`sa01`** (today, 2026-09-01). The plan's step-1 glob `sa[0-9][0-9]` picks it up anyway, so the *tar* is correct and only the human-readable comment is wrong. | Date rolled over; `sadc` writes `sa<DD>`. |
| A5 | The journal on this box is **persistent** (`/var/log/journal` exists), so ≥ 2 boots are listed by `journalctl --list-boots` and a wider-than-one-boot capture is **available**, not merely desirable. | Round 412's item 5 asked for it; nothing has said it is impossible. |
| A6 | With persistence confirmed, a `--since`-bounded `_PID=1` capture over the sa23–sa31 window yields **more than 358** `Starting` fires. | Round 400's 358 came from one boot and a grep. |

### B — the factor of two in `pgsteal` (round 418 item 2)

| # | Prediction | Basis |
|---|---|---|
| B1 | `/proc/vmstat` on this kernel (6.8) contains **two disjoint partitions of the same reclaim events**: an actor split (`pgsteal_kswapd`, `pgsteal_direct`, and on 6.8 also `pgsteal_khugepaged`) and a memory-type split (`pgsteal_anon`, `pgsteal_file`). | Kernel ≥ 5.19 exports both. |
| B2 | Those two partitions **sum to each other**: `pgsteal_kswapd + pgsteal_direct + pgsteal_khugepaged == pgsteal_anon + pgsteal_file`, exactly, at any instant. | They count the same pages, sliced two ways. |
| B3 | **The mechanism of the factor of two is an asymmetry in how `sysstat` reads those fields.** `pgsteal` is accumulated by *prefix* `pgsteal_`, which matches **both** partitions and therefore doubles; `pgscank`/`pgscand` are read from the *specific* fields `pgscan_kswapd` / `pgscan_direct`, which are one partition only and do **not** double. `%vmeff = pgsteal/(pgscank+pgscand)` therefore reports ≈ **2×** the true reclaim efficiency. | The only asymmetry that yields exactly 2 on the numerator and 1 on the denominator. |
| B4 | Consequently `pgscan_anon + pgscan_file == pgscan_kswapd + pgscan_direct + pgscan_khugepaged` **also** holds, and sar's `pgscank + pgscand` is the *undoubled* total — so the error is entirely in the numerator and **every stolen-byte figure in this program's record is exactly 2× too large**, not the "upper bound with a factor-of-two question over it" round 418 had to publish. | Follows from B2+B3. |
| B5 | I predict I will **not** be able to close this empirically from a live `sar -B 1 1` on an idle box, because reclaim will be 0 in that sample and 0/0 measures nothing. The confirmation available is structural (B2) plus the installed `sysstat` version. Stated in advance so a null here is not retro-fitted. | An idle 31 GB box does not reclaim on demand, and forcing it would be a perturbation. |

### C — this boot, and what a fresh boot makes visible (round 370 item 3)

| # | Prediction | Basis |
|---|---|---|
| C1 | The engine (`qwen36-colibri`, a **user** unit) started during this boot, and **this boot's journal still holds the load** — so the `unpacking to int8 in slot` transition round 370 wanted to catch live is recoverable **retrospectively**, from the journal, without polling and without sending a request. | Journal retains the current boot in full. |
| C2 | That makes round 370's item 3 answerable in a **weaker but honest** form: the transition's *timeline* (per-slot timestamps) is recoverable; the `memory.current` *trajectory* through it is **not**, because nobody sampled it, and no artifact records it after the fact. I predict item 3 is therefore **half-closable and half-permanently-lost for this boot**. | `memory.current` is a level, not a counter; unsampled levels do not survive. |
| C3 | `sa01` (today) shows a memory step during 05:33–06:30 of the same order as the model's resident footprint (~9.77 GB), and it is the **largest** step in sa01. | Round 364/370 measured `memory.current` 9,770,594,304 B at rest. |
| C4 | `sa01`'s reclaim during the engine load is **smaller** than sa30's 13:30–15:10 load, because a fresh boot's page cache starts empty and there is less to steal. | Reclaim needs something reclaimable. |

### D — `sadf` and the 1200 s stitch (round 418 item 4)

| # | Prediction | Basis |
|---|---|---|
| D1 | `sadf` **does** emit a day-file's first record, which `sar` consumes as a reference and never prints — so `sadf`-based extraction removes the 1200 s stitched bucket instead of working around it. | `sadf` is a raw formatter; `sar` computes rates and needs a previous sample. |
| D2 | If D1 holds, the first `sadf` record of a day file carries a **timestamp near 00:00** and the `sar` table's first printed row is the **second** record — a directly checkable pair. | Same file, two renderers. |

### E — hygiene (not a forecast; a commitment)

| # | Commitment |
|---|---|
| E1 | Port **8001 is never contacted**. No engine request of any kind is sent to :8000 or :8080. |
| E2 | No unit is started, stopped or restarted. |
| E3 | Writes on the box are confined to `~/nuc-research/**` and `/tmp/**`; nothing under `/work/**` is modified. |
