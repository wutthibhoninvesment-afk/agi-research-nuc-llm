# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-26 21:00:31
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 1662
- mode: non-streaming
- finished: 2026-08-26 21:03:35

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 290 | 44.1 | 6.57 | 41.2 | 43.6 | 0.94 | 4.60 | 54.9 |  |
