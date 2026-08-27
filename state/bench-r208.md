# NUC bench — TTFT / prefill / decode

- base_url: http://127.0.0.1:8000
- model: qwen36
- started: 2026-08-27 16:28:40
- decode_tokens: 64
- cutoff_s: 300.0
- seed: 208001
- mode: non-streaming
- finished: 2026-08-27 16:35:44

| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 305 | 83.8 | 3.64 | 86.0 | 74.0 | 1.16 | 7.64 | 94.3 |  |
