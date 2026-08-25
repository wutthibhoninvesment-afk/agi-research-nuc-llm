# skill trigger eval — mode=native model=sonnet

probes: 27 ok, 0 errored, exact-match 89%, negatives false-fire 0/9, cost $0.611
declared-not-invoked: 3 probe(s) wrote SKILLS=<expected> without a Skill tool_use (protocol artifact — re-probe before treating the miss as a selection failure)

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | n/a | n/a | 0 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| prediction-banking | 67% | 100% | 6 | 0 | 3 |
| session-inheritance-audit | 100% | 100% | 9 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| pb-near | 3 | 3 (100%) | 3 (100%) | 0 |
| pb-mid | 3 | 0 (0%) | 0 (0%) | 0 |
| pb-far | 3 | 3 (100%) | 3 (100%) | 0 |
| sia-near | 3 | 3 (100%) | 3 (100%) | 0 |
| sia-mid | 3 | 3 (100%) | 3 (100%) | 0 |
| sia-far | 3 | 3 (100%) | 3 (100%) | 0 |
| pb-neg | 3 | 3 (100%) | 3 (100%) | 0 |
| sia-neg | 3 | 3 (100%) | 3 (100%) | 0 |
| pm-neg | 3 | 3 (100%) | 3 (100%) | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| pb-near | prediction-banking | prediction-banking | — | yes |
| pb-near | prediction-banking | prediction-banking | — | yes |
| pb-near | prediction-banking | prediction-banking | — | yes |
| pb-mid | prediction-banking | — | — | NO |
| pb-mid | prediction-banking | — | — | NO |
| pb-mid | prediction-banking | — | — | NO |
| pb-far | prediction-banking | prediction-banking | — | yes |
| pb-far | prediction-banking | prediction-banking | — | yes |
| pb-far | prediction-banking | prediction-banking | — | yes |
| sia-near | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-near | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-near | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-mid | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-mid | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-mid | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-far | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-far | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-far | session-inheritance-audit | session-inheritance-audit | — | yes |
| pb-neg | — | — | — | yes |
| pb-neg | — | — | — | yes |
| pb-neg | — | — | — | yes |
| sia-neg | — | — | — | yes |
| sia-neg | — | — | — | yes |
| sia-neg | — | — | — | yes |
| pm-neg | — | — | — | yes |
| pm-neg | — | — | — | yes |
| pm-neg | — | — | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
