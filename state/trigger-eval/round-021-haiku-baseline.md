# skill trigger eval — mode=native model=haiku

probes: 30 ok, 0 errored, exact-match 30%, negatives false-fire 4/4, cost $1.095

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 50% | 19% | 3 | 13 | 3 |
| fuzz-mutate-kill-loop | 100% | 50% | 2 | 2 | 0 |
| generator-trampoline-evaluator | 50% | 100% | 2 | 0 | 2 |
| llm-engine-benchmarking | n/a | 0% | 0 | 1 | 0 |
| offline-agent-testing | 75% | 60% | 3 | 2 | 1 |
| shared-tip-immutable-lists | 100% | 67% | 2 | 1 | 0 |
| skill-authoring | 50% | 100% | 3 | 0 | 3 |
| subprocess-cli-testing | 100% | 29% | 4 | 10 | 0 |
| tiny-language-implementation | n/a | 0% | 0 | 4 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-near | skill-authoring | skill-authoring | — | yes |
| sa-near | skill-authoring | skill-authoring | — | yes |
| sa-mid | skill-authoring | — | — | NO |
| sa-mid | skill-authoring | skill-authoring,agent-context-budgeting | — | NO |
| sa-far | skill-authoring | agent-context-budgeting,fuzz-mutate-kill-loop,tiny-language-implementation,offline-agent-testing | dataviz | NO |
| sa-far | skill-authoring | subprocess-cli-testing | Glob | NO |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| oat-near | offline-agent-testing | offline-agent-testing,agent-context-budgeting,subprocess-cli-testing | run | NO |
| oat-mid | offline-agent-testing | — | claude-api | NO |
| oat-mid | offline-agent-testing | offline-agent-testing | claude-api | yes |
| acb-near | agent-context-budgeting | — | claude-api | NO |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting,subprocess-cli-testing | claude-api,run | NO |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| gte-far | generator-trampoline-evaluator | tiny-language-implementation,subprocess-cli-testing,fuzz-mutate-kill-loop,generator-trampoline-evaluator,offline-agent-testing,llm-engine-benchmarking,shared-tip-immutable-lists | — | NO |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator,agent-context-budgeting | run | NO |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists,agent-context-budgeting | — | NO |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists,agent-context-budgeting | — | NO |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing,agent-context-budgeting | run | NO |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | fuzz-mutate-kill-loop,agent-context-budgeting,subprocess-cli-testing,tiny-language-implementation | — | NO |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | fuzz-mutate-kill-loop,agent-context-budgeting,subprocess-cli-testing,tiny-language-implementation | — | NO |
| neg-3 | — | agent-context-budgeting,subprocess-cli-testing | run | NO |
| neg-3 | — | agent-context-budgeting,subprocess-cli-testing | run | NO |
| neg-6 | — | agent-context-budgeting,subprocess-cli-testing | — | NO |
| neg-6 | — | agent-context-budgeting,subprocess-cli-testing | — | NO |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
