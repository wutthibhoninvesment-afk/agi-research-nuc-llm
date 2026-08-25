---
name: colocated-model-lane
description: Use when a second, smaller LLM must run on the same box as a production inference engine that already fills RAM, and someone asks whether it is feasible, how to fetch and stage its weights without disturbing the big engine, or why the small model decodes slowly once it is there. Symptoms — "MemAvailable is under 1 GB and swap is in use", "the big engine sits at its cgroup MemoryMax", "is there room for a 1B/7B fast lane", "download a 7 GB container onto a server whose engine must not be evicted", "the small model is slower with a bigger expert cache", "sys time dominates its decode". Covers the cgroup footprint (resident plus swapped, not RSS), per-object bandwidth gates, expert-cache cap arithmetic from container geometry, off-box conversion, harness-mode validation, page-cache-safe resumable per-file transfer with md5 checks, and a hand-off script for an unreachable box. NOT for single-engine latency benchmarking (llm-engine-benchmarking), GPU cluster scheduling, or choosing a model by quality.
---

# Co-locating a small model lane beside a RAM-saturated engine

The question "can a second model run here?" is three arithmetic questions
(bandwidth, disk, RAM) and one regime question (does the lane decode from
RAM or from disk?). Each has a measurement that does not touch the
production engine. Reference implementation: `nuc/fast_lane.py`
(bandwidth parser + gate, cap planner, resumable transfer plan, hand-off
script), `nuc/fast_lane_sink.py` (page-cache-safe sink with `--resume`),
`nuc/lane_bench.py` (harness-mode micro-bench with sys-share), 78 offline
tests in `nuc/tests/` (`test_fast_lane.py` + `test_lane_bench.py`).

## When to use (triggers)
- A production engine (colibri, llama.cpp, vLLM-CPU) fills the machine
  and a faster/smaller model is wanted next to it for short tool turns.
- Weights must be fetched onto a box where a plain `scp`/`wget` could push
  the engine into swap or the OOM killer.
- The small lane runs but is slower than the upstream benchmark, or gets
  slower when its expert cache is made bigger.
- A prior session staged part of the plan and the box is now unreachable.

**When NOT to use:** measuring one engine's TTFT/decode curve (use
`llm-engine-benchmarking`); GPU/Kubernetes replica scheduling; picking a
model by quality; anything on a box with free RAM (just run it).

## Steps
1. **Read the cgroup, not `ps`.** For the engine's cgroup:
   `memory.current`, `memory.max`, `memory.peak`, `memory.swap.current`,
   plus `/proc/<pid>/status` `VmRSS`/`VmSwap` and `/proc/meminfo`
   `MemAvailable`. Footprint = resident + swapped (`full_footprint()`);
   RSS alone under-stated a 36.0 GB engine as 31.8 GB. Checkable: the
   plan file states footprint, `memory.max`, swap used, MemAvailable.
2. **Gate bandwidth per object, against the model's own CDN.** One
   `curl -sSL --max-time 25 -o /dev/null -w '%{speed_download} …'` per
   shard (`probe_cmd()`); shards of one repo differ 7× (66.7 vs 8.7 MB/s),
   and generic speed-test hosts read 100× slower than the model CDN from
   the same box — gate on the objects you will download. Download time =
   Σ size/rate per object (`download_time_s()`), disk margin ≥ 1.2×
   (`gate_download()`).
3. **Compute the cap plan from container geometry.** Read expert bytes,
   layers, experts from the shard headers; `RSS(cap) = RSS_full −
   (cap_full − cap)·layers·expert_bytes`; lane footprint = dense +
   cap·layers·expert + KV·ctx + workspace. `fast_lane.py plan` prints, per
   lane size, the cap the big engine must drop to and its miss cost
   (`decode +s/tok`, `prefill +s/req`). Include the row "no lane, stop
   swapping" — that number is often the real recommendation.
4. **Convert off-box.** The saturated box has no RAM for torch; convert on
   a laptop (`convert_olmoe_merged.py --flush-every 128`: 7.4 GB out,
   3.7 GB peak RSS, 4 min) and prove determinism by md5 of first and last
   shard across two conversions before trusting a partial remote copy.
5. **Validate with the engine's harness mode, locally.** Build the same
   engine version on the laptop; run its ref.json mode with a custom ref
   (`lane_bench.make_ref(prompt_ids, n_new)`) to get decode tok/s,
   expert-cache hit rate, peak RSS and `resource.getrusage` user/sys per
   case. A coherent answer ("Paris") plus these rows is the container
   check; `Matching tokens: 0/N` against dummy ids is expected.
6. **Diagnose the regime with sys share — for prefill AND decode
   separately.** sys/(user+sys) > 50 % means the lane is page-fault/read
   bound, not compute bound; on such a box a larger expert cache can be
   *slower* (bigger RSS, less page cache). Compare `cap` sizes and the
   engine's drop-pages mode (`EXPERT_DROP=1`) in the same run; report the
   rate with its regime. Measure prefill with `--n-new 1 --prompt-tokens
   200` (and 50/800): it walks one layer for all tokens, so its working set
   (≤ 64 experts, 400 MB) fits the page cache while decode's (all layers per
   token, 6.4 GB) does not — the same box read 8–9.6 prompt-tok/s (sys 42–50
   %) and 1.2 decode-tok/s (sys 85 %). Then compute the break-even prompt
   length against the big engine (`fast_lane.breakeven_prompt_tokens`);
   a lane that decodes slower than the big engine is "fast" only for long
   prompts with short replies.
7. **Transfer per file, without page cache, resumably.** Stream each
   file into `fast_lane_sink.py` (fdatasync + `posix_fadvise(DONTNEED)`
   every 256 MB; `.part` + rename); on a retry ask `--part-size`, send
   `tail -c +<have+1>` with `--resume`, verify with `md5sum` on the box
   against local digests (`transfer_plan()`, `md5_of_files()`). Never a
   tar stream: its headers carry mtimes, a re-run is not byte-identical.
8. **Quote remote paths for the remote shell.** `~/x` inside single
   quotes never expands on the box — `remote_quote()` emits `"$HOME"/x`
   inside the single-quoted ssh argument.
9. **Generate the hand-off before you need it.** `fast_lane.py handoff
   <dir> <target> <remote_dir> --remote-sizes sizes.json --md5` prints an
   idempotent script: host guard first (`exit 2` when down), sink staged,
   skip/resume/send per file, md5 verify (`exit 3`), log line appended.
   The script refuses to contain the forbidden port; keep that check in
   code, not in a comment.
10. **Predictions first, scored after** (`prediction-banking`): bandwidth
    per shard, container size, conversion time, decode per cap, hit rate,
    sys share. Bank box-side predictions the box cannot answer today for
    the window when it can.

## Pitfalls
- **RSS as the footprint.** At `memory.current == memory.max` the
  engine has already pushed 13 % of itself to swap; every cap computed
  from RSS is too optimistic (predicted cap 130, planner said 75).
- **Speed-test hosts as the bandwidth reference.** 0.1–0.24 MB/s from
  three well-known mirrors vs 9–67 MB/s from the model CDN on the same
  Wi-Fi; a 403 from a CDN speed page is a user-agent block, not the link.
- **A tar stream for a multi-GB copy.** Died at 1.09 GB of 7.42 GB with
  no way to resume; per-file streams resume with `tail -c`.
- **Single-quoted `~`.** The sink would have written to a directory
  named `~` in the login cwd; the md5 step would then "verify" nothing.
- **Predicting one regime from a number taken in another.** Round 106's
  decode bands (3.5–5.5 tok/s) came from CHAT-mode runs made right after
  conversion, container hot in the page cache; the cold measurement was
  1.20 — every miss in that ledger (5 of 11 parts) had this shape. Label
  every rate with its regime and re-measure cold before banking.
- **Reading a laptop rate as the box's rate.** An 8 GB laptop cannot hold
  a 7.4 GB container in page cache, so its decode is the *disk-bound*
  regime; a box with more free RAM decodes faster, a box with none
  decodes like the laptop — say which regime a number came from.
- **Measuring while your own searches run.** Two forgotten `find /`
  jobs pushed load to 2.3 during the first case; label warm-up cases and
  repeat the clean one (`ps -axo pid,ppid,etime,command | grep find`).
- **Numbers that live only in a dead session's transcript.** Round 100
  measured everything and wrote nothing; the next round rebuilt the
  record from the JSONL transcript (`session-inheritance-audit` step 5b).

## Commands
```bash
python3 nuc/fast_lane.py parse probe.log                 # per-object MB/s, spread
python3 nuc/fast_lane.py gate --min-rate 8.7 --disk-free-gb 677 --disk-needed-gb 7.42
python3 nuc/fast_lane.py plan --resident-gb 31.81 --swapped-gb 4.20 --cap-full 256 --ram-gib 31.23
python3 nuc/lane_bench.py --engine ./olmoe --snap ./olmoe_merged \
  --case cap=16 --case cap=64 --case drop:cap=16,EXPERT_DROP=1 --n-new 200 --json bench.jsonl
python3 nuc/lane_bench.py --engine ./olmoe --snap ./olmoe_merged --case p200:cap=16 --n-new 1 --prompt-tokens 200   # prefill rate
python3 -c 'import sys; sys.path.insert(0, "nuc"); import fast_lane as f; print(f.breakeven_prompt_tokens(60))'   # lane vs big-engine break-even
python3 nuc/fast_lane.py handoff ./olmoe_merged jab@box '~/models/olmoe' --key ~/.ssh/k --md5 > handoff.sh
```

## Verification
```bash
perl -e 'alarm 300; exec @ARGV' python3 -m pytest -q nuc/tests           # 155 passed (incl. taskscript)
python3 nuc/fast_lane.py handoff ./olmoe_merged jab@box '~/m' | grep -c "'~"   # expected: 0
python3 nuc/fast_lane.py handoff ./olmoe_merged jab@box '~/m' | grep -c 8001   # expected: 0
```
- [ ] Plan file states footprint = resident + swapped, and the no-lane cap
- [ ] Every shard has its own measured rate; gate passed on the slowest
- [ ] Two conversions, identical md5 on first and last shard
- [ ] Harness-mode table has tok/s, hit %, peak RSS, sys share per case
- [ ] Hand-off script: host guard first, resume offsets = have + 1, md5 exit 3
