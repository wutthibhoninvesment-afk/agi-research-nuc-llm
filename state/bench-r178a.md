# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-27 03:15:05
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 1729
- mode: non-streaming
- engine_cold_start_s: 14.7
- finished: 2026-08-27 03:18:27

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 298 | 43.6 | 6.83 | 43.2 | 44.6 | 0.97 | 4.80 | 56.3 |  |
