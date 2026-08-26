# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-26 20:54:42
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 166
- mode: non-streaming
- engine_cold_start_s: 105.71
- finished: 2026-08-26 20:59:51

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 289 | 57.8 | 5.00 | 40.5 | 45.8 | 0.88 | 3.35 | 59.3 |  |
