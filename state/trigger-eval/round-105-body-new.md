# skill trigger eval — mode=body model=sonnet

probes: 6 ok, 0 errored, exact-match 100%, negatives false-fire 0/0, cost $0.682

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 2 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| prediction-banking | 100% | 100% | 2 | 0 | 0 |
| session-inheritance-audit | 100% | 100% | 2 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| body-fmk | 2 | 2 (100%) | 2 (100%) | 0 |
| body-pb | 2 | 2 (100%) | 2 (100%) | 0 |
| body-sia | 2 | 2 (100%) | 2 (100%) | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| body-fmk | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| body-fmk | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| body-pb | prediction-banking | prediction-banking | — | yes |
| body-pb | prediction-banking | prediction-banking | — | yes |
| body-sia | session-inheritance-audit | session-inheritance-audit | — | yes |
| body-sia | session-inheritance-audit | session-inheritance-audit | — | yes |

body-following: 4/6 cases fully followed; bundled files read 0/0; evidence matched 25/28

| case | fired | staged files read | failed reads | files | evidence | chars |
|---|---|---|---|---|---|---|
| body-fmk | fuzz-mutate-kill-loop | — | — | 0/0 | 4/4 | 18203 |
| body-fmk | fuzz-mutate-kill-loop | — | — | 0/0 | 4/4 | 16204 |
| body-pb | prediction-banking | — | — | 0/0 | 5/5 | 3867 |
| body-pb | prediction-banking | — | — | 0/0 | 5/5 | 4154 |
| body-sia | session-inheritance-audit | — | — | 0/0 | 4/5 | 3282 |
| body-sia | session-inheritance-audit | — | — | 0/0 | 3/5 | 3327 |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
