# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-26 21:03:56
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 1663
- mode: non-streaming
- finished: 2026-08-26 21:06:57

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 291 | 42.2 | 6.90 | 40.8 | 43.2 | 0.95 | 4.55 | 54.7 |  |
