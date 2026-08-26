# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-26 18:43:38
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 160
- mode: non-streaming
- finished: 2026-08-26 18:46:43

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 304 | 43.7 | 6.95 | 42.5 | 43.2 | 0.98 | 5.06 | 54.9 |  |
