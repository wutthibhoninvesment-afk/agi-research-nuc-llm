# skill trigger eval — mode=native model=sonnet

probes: 30 ok, 0 errored, exact-match 100%, negatives false-fire 0/4, cost $1.038

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 100% | 6 | 0 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 2 | 0 | 0 |
| generator-trampoline-evaluator | 100% | 100% | 4 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 4 | 0 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 2 | 0 | 0 |
| skill-authoring | 100% | 100% | 6 | 0 | 0 |
| subprocess-cli-testing | 100% | 100% | 4 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-near | skill-authoring | skill-authoring | — | yes |
| sa-near | skill-authoring | skill-authoring | — | yes |
| sa-mid | skill-authoring | skill-authoring | — | yes |
| sa-mid | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| oat-mid | offline-agent-testing | offline-agent-testing | — | yes |
| oat-mid | offline-agent-testing | offline-agent-testing | claude-api | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | — | yes |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |
| neg-3 | — | — | — | yes |
| neg-3 | — | — | — | yes |
| neg-6 | — | — | — | yes |
| neg-6 | — | — | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# skill trigger eval — mode=native model=haiku

probes: 30 ok, 0 errored, exact-match 67%, negatives false-fire 0/4, cost $1.149

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 83% | 50% | 5 | 5 | 1 |
| fuzz-mutate-kill-loop | 100% | 67% | 2 | 1 | 0 |
| generator-trampoline-evaluator | 25% | 50% | 1 | 1 | 3 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | 100% | 67% | 4 | 2 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 2 | 0 | 0 |
| skill-authoring | 100% | 75% | 6 | 2 | 0 |
| subprocess-cli-testing | 100% | 50% | 4 | 4 | 0 |
| tiny-language-implementation | n/a | 0% | 0 | 2 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-near | skill-authoring | skill-authoring | — | yes |
| sa-near | skill-authoring | skill-authoring | — | yes |
| sa-mid | skill-authoring | skill-authoring | — | yes |
| sa-mid | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring,agent-context-budgeting | — | NO |
| sa-far | skill-authoring | skill-authoring,agent-context-budgeting | — | NO |
| oat-near | offline-agent-testing | offline-agent-testing,agent-context-budgeting | — | NO |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| oat-mid | offline-agent-testing | offline-agent-testing,subprocess-cli-testing | claude-api | NO |
| oat-mid | offline-agent-testing | offline-agent-testing | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| acb-far | agent-context-budgeting | agent-context-budgeting | — | yes |
| gte-far | generator-trampoline-evaluator | skill-authoring,subprocess-cli-testing,offline-agent-testing,fuzz-mutate-kill-loop,generator-trampoline-evaluator | run | NO |
| gte-far | generator-trampoline-evaluator | skill-authoring,subprocess-cli-testing,agent-context-budgeting | run | NO |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | run | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists,tiny-language-implementation,offline-agent-testing,generator-trampoline-evaluator | run | NO |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | init | yes |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | init | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | run | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | fuzz-mutate-kill-loop,agent-context-budgeting,subprocess-cli-testing,tiny-language-implementation | run | NO |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | fuzz-mutate-kill-loop | — | NO |
| neg-3 | — | — | — | yes |
| neg-3 | — | — | run | yes |
| neg-6 | — | — | run | yes |
| neg-6 | — | — | run | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# per-model comparison

| skill | sonnet recall | haiku recall |
|---|---|---|
| agent-context-budgeting | 100% | 83% |
| fuzz-mutate-kill-loop | 100% | 100% |
| generator-trampoline-evaluator | 100% | 25% |
| llm-engine-benchmarking | n/a | n/a |
| offline-agent-testing | 100% | 100% |
| shared-tip-immutable-lists | 100% | 100% |
| skill-authoring | 100% | 100% |
| subprocess-cli-testing | 100% | 100% |
| tiny-language-implementation | n/a | n/a |

| metric | sonnet | haiku |
|---|---|---|
| exact-match | 100% | 67% |
| neg false-fire | 0/4 | 0/4 |
| errored | 0 | 0 |
| displaced | 0 | 0 |
| cost | $1.038 | $1.149 |
