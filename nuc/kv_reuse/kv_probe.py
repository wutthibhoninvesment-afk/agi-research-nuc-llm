#!/usr/bin/env python3
"""Round-28 P8 probe: three identical raw-prompt requests to :8000 /v1/completions
(streaming, one SSE chunk per token), timing TTFT + total per request. The
first request after a long idle carries the idle-cold penalty; the ratio for
P8 is therefore request 3 / request 2. Also captures the raw model output for
the retokenization-stability experiment. Writes /tmp/r28_probe.json."""
import json, time, urllib.request, sys

P = json.load(open(sys.argv[1]))["p1"]
OUT = "/tmp/r28_probe.json"
N = 3
results = []
for i in range(N):
    body = json.dumps({"model": "qwen36", "prompt": P, "max_tokens": 40,
                       "temperature": 0, "stream": True}).encode()
    req = urllib.request.Request("http://127.0.0.1:8000/v1/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic(); t_first = None; text = []; chunks = 0; usage = None
    with urllib.request.urlopen(req, timeout=1800) as r:
        for line in r:
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            d = json.loads(payload)
            if d.get("usage"):
                usage = d["usage"]
            ch = d.get("choices") or []
            if ch and ch[0].get("text"):
                if t_first is None:
                    t_first = time.monotonic() - t0
                text.append(ch[0]["text"]); chunks += 1
    total = time.monotonic() - t0
    rec = {"i": i, "ttft_s": t_first, "total_s": total, "chunks": chunks,
           "text": "".join(text), "usage": usage, "started_at": time.time() - total}
    results.append(rec)
    print(json.dumps(rec), flush=True)
    json.dump(results, open(OUT, "w"), indent=1)
print("DONE", flush=True)
