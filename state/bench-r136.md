# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-26 01:51:30
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 136
- mode: non-streaming
- finished: 2026-08-26 01:54:59

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 307 | 58.6 | 5.23 | 44.7 | 45.3 | 0.99 | 4.30 | 59.4 |  |
