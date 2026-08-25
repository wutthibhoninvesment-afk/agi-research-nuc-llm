# skill trigger eval — mode=native model=haiku

probes: 48 ok, 0 errored, exact-match 42%, negatives false-fire 0/12, cost $1.616

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 67% | 92% | 12 | 1 | 6 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | n/a | 0% | 0 | 8 | 0 |
| generator-trampoline-evaluator | 61% | 92% | 11 | 1 | 7 |
| llm-engine-benchmarking | n/a | 0% | 0 | 1 | 0 |
| offline-agent-testing | n/a | 0% | 0 | 3 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | n/a | 0% | 0 | 15 | 0 |
| tiny-language-implementation | n/a | 0% | 0 | 18 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| acb-near | 6 | 6 (100%) | 5 (83%) | 0 |
| acb-mid | 6 | 6 (100%) | 2 (33%) | 0 |
| acb-far | 6 | 0 (0%) | 0 (0%) | 0 |
| gte-near | 6 | 1 (17%) | 1 (17%) | 0 |
| gte-mid | 6 | 5 (83%) | 0 (0%) | 0 |
| gte-far | 6 | 5 (83%) | 0 (0%) | 0 |
| neg-2 | 6 | 6 (100%) | 6 (100%) | 0 |
| neg-5 | 6 | 6 (100%) | 6 (100%) | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| acb-near | agent-context-budgeting | agent-context-budgeting,fuzz-mutate-kill-loop,subprocess-cli-testing,tiny-language-implementation,generator-trampoline-evaluator,llm-engine-benchmarking,offline-agent-testing | claude-api | NO |
| acb-near | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | subprocess-cli-testing,agent-context-budgeting,offline-agent-testing | claude-api,run | NO |
| acb-mid | agent-context-budgeting | subprocess-cli-testing,agent-context-budgeting,offline-agent-testing | claude-api,none,run | NO |
| acb-mid | agent-context-budgeting | agent-context-budgeting,subprocess-cli-testing | claude-api,run,init | NO |
| acb-mid | agent-context-budgeting | subprocess-cli-testing,agent-context-budgeting | claude-api | NO |
| acb-mid | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| gte-near | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-near | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-near | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-near | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-near | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-near | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-mid | generator-trampoline-evaluator | generator-trampoline-evaluator,tiny-language-implementation,subprocess-cli-testing,fuzz-mutate-kill-loop | run,init | NO |
| gte-mid | generator-trampoline-evaluator | tiny-language-implementation,generator-trampoline-evaluator,subprocess-cli-testing | run | NO |
| gte-mid | generator-trampoline-evaluator | tiny-language-implementation,generator-trampoline-evaluator,subprocess-cli-testing | — | NO |
| gte-mid | generator-trampoline-evaluator | tiny-language-implementation,generator-trampoline-evaluator,subprocess-cli-testing | run | NO |
| gte-mid | generator-trampoline-evaluator | tiny-language-implementation,subprocess-cli-testing,generator-trampoline-evaluator,fuzz-mutate-kill-loop | run | NO |
| gte-mid | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-far | generator-trampoline-evaluator | tiny-language-implementation,generator-trampoline-evaluator,subprocess-cli-testing,fuzz-mutate-kill-loop | — | NO |
| gte-far | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator,tiny-language-implementation,subprocess-cli-testing,fuzz-mutate-kill-loop,agent-context-budgeting | run,simplify,code-review | NO |
| gte-far | generator-trampoline-evaluator | tiny-language-implementation,generator-trampoline-evaluator,fuzz-mutate-kill-loop,subprocess-cli-testing | run | NO |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator,subprocess-cli-testing,fuzz-mutate-kill-loop,tiny-language-implementation | — | NO |
| gte-far | generator-trampoline-evaluator | tiny-language-implementation,fuzz-mutate-kill-loop,generator-trampoline-evaluator,subprocess-cli-testing | run | NO |
| neg-2 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-5 | — | — | — | yes |
| neg-5 | — | — | — | yes |
| neg-5 | — | — | run | yes |
| neg-5 | — | — | — | yes |
| neg-5 | — | — | — | yes |
| neg-5 | — | — | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
