# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-26 03:19:41
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 142
- mode: non-streaming
- finished: 2026-08-26 03:22:49

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 296 | 44.9 | 6.60 | 43.6 | 43.4 | 1.00 | 5.07 | 56.0 |  |
