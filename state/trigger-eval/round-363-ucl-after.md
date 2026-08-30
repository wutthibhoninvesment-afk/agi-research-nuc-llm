| case | runs | fired | exact | err |
|---|---|---|---|---|
| ucl-near | 3 | 3 (100%) | 3 (100%) | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| ucl-near | unrun-checker-latency | unrun-checker-latency | — | yes |
| ucl-near | unrun-checker-latency | unrun-checker-latency | — | yes |
| ucl-near | unrun-checker-latency | unrun-checker-latency | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# comparison vs baseline state/trigger-eval/round-363-unrun-checker-latency.json — model=sonnet
exact-match 75% -> 100%; negatives false-fire 0/1 -> 0/0; verdicts: 3 dropped, 1 low-n
descriptions edited since the baseline: unrun-checker-latency

| case | expect | base fired | new fired | Δ | base exact | new exact | verdict |
|---|---|---|---|---|---|---|---|
| ucl-near | unrun-checker-latency | 1/1 | 3/3 | +0% | 0/1 | 3/3 | low-n |
| ucl-mid | unrun-checker-latency | 1/1 | — | — | 1/1 | — | dropped |
| ucl-far | unrun-checker-latency | 1/1 | — | — | 1/1 | — | dropped |
| ucl-neg-ci-already-red | — | 1/1 | — | — | 1/1 | — | dropped |

[exited with code 0]
