# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-27 19:16:21
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 1
- mode: non-streaming
- engine_cold_start_s: 14.83
- finished: 2026-08-27 19:19:31

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 291 | 40.8 | 7.14 | 40.6 | 41.2 | 0.99 | 5.33 | 52.4 |  |

Context (round 214): same boot as round 208 (`uptime -s` 2026-08-27 11:50:48), now ~7h24m in.
`memory.swap.current` read 975462400 bytes both immediately before and immediately after this
run (flat, not mid-transition). `memory.events`: max=1017 oom=0 oom_kill=0 (round 208 at ~4h35m:
max=1006). Both prefill (7.14) and decode (5.33) sit inside/above the 3-boot plateau band
(~6.95-7.10 / ~4.95-5.18) established by round 208 — resolves round 208's flagged swap-onset dip
(prefill 3.64 tok/s at 703 MB swap) as a transient artifact, since swap has since grown further
(703 -> 975 MB) yet prefill fully recovered rather than continuing to degrade. See
knowledge/round-214-nuc-e-swap-onset-artifact-resolved-and-ceiling-rate-decay.md.
