# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-28 00:56:07
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 1
- mode: non-streaming
- engine_cold_start_s: 14.46
- finished: 2026-08-28 01:00:12

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 291 | 40.5 | 7.19 | 40.7 | 40.7 | 1.00 | 5.23 | 52.8 |  |
