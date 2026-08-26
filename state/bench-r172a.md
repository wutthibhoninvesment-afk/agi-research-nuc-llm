# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-26 23:28:14
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 1729
- mode: non-streaming
- engine_cold_start_s: 14.69
- finished: 2026-08-26 23:31:31

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 298 | 42.2 | 7.07 | 41.5 | 43.1 | 0.96 | 4.79 | 54.6 |  |
