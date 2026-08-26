# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-26 17:15:26
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 154
- mode: non-streaming
- finished: 2026-08-26 17:18:31

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 310 | 44.4 | 6.98 | 43.2 | 42.2 | 1.02 | 5.04 | 55.7 |  |
