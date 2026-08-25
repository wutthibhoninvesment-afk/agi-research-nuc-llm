# skill trigger eval — mode=body model=sonnet

probes: 4 ok, 0 errored, exact-match 100%, negatives false-fire 0/0, cost $0.433

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | n/a | n/a | 0 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | 100% | 100% | 4 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| body-sa | 2 | 2 (100%) | 2 (100%) | 0 |
| body-saref | 2 | 2 (100%) | 2 (100%) | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| body-sa | skill-authoring | skill-authoring | — | yes |
| body-sa | skill-authoring | skill-authoring | — | yes |
| body-saref | skill-authoring | skill-authoring | — | yes |
| body-saref | skill-authoring | skill-authoring | — | yes |

body-following: 2/4 cases fully followed; bundled files read 2/4; evidence matched 16/16

| case | fired | staged files read | failed reads | files | evidence | chars |
|---|---|---|---|---|---|---|
| body-sa | skill-authoring | — | — | 0/1 | 4/4 | 5162 |
| body-sa | skill-authoring | — | — | 0/1 | 4/4 | 6717 |
| body-saref | skill-authoring | skill-authoring/references/trigger-evaluation.md | — | 1/1 | 4/4 | 2170 |
| body-saref | skill-authoring | skill-authoring/references/trigger-evaluation.md | — | 1/1 | 4/4 | 1627 |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
