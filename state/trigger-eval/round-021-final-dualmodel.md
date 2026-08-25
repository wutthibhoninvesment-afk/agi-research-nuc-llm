# skill trigger eval — mode=native model=sonnet

probes: 39 ok, 0 errored, exact-match 97%, negatives false-fire 0/7, cost $1.581

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 100% | 3 | 0 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 7 | 0 | 0 |
| generator-trampoline-evaluator | 100% | 100% | 4 | 0 | 0 |
| llm-engine-benchmarking | 100% | 100% | 3 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 3 | 0 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 3 | 0 | 0 |
| skill-authoring | 100% | 100% | 3 | 0 | 0 |
| subprocess-cli-testing | 100% | 100% | 4 | 0 | 0 |
| tiny-language-implementation | 75% | 100% | 3 | 0 | 1 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-near | skill-authoring | skill-authoring | — | yes |
| sa-mid | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| oat-mid | offline-agent-testing | offline-agent-testing | claude-api | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| gte-near | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-mid | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-mid | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-far | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-far | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| tli-near | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-mid | tiny-language-implementation | — | — | NO |
| tli-far | tiny-language-implementation | tiny-language-implementation | — | yes |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation,subprocess-cli-testing | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |
| neg-1 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-3 | — | — | — | yes |
| neg-4 | — | — | — | yes |
| neg-5 | — | — | — | yes |
| neg-6 | — | — | — | yes |
| leb-near | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-mid | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-far | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-neg | — | — | — | yes |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-modelreview | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# skill trigger eval — mode=native model=haiku

probes: 39 ok, 0 errored, exact-match 51%, negatives false-fire 2/7, cost $1.544

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 38% | 3 | 5 | 0 |
| fuzz-mutate-kill-loop | 29% | 50% | 2 | 2 | 5 |
| generator-trampoline-evaluator | 75% | 75% | 3 | 1 | 1 |
| llm-engine-benchmarking | 33% | 100% | 1 | 0 | 2 |
| offline-agent-testing | 100% | 75% | 3 | 1 | 0 |
| shared-tip-immutable-lists | 67% | 100% | 2 | 0 | 1 |
| skill-authoring | 67% | 33% | 2 | 4 | 1 |
| subprocess-cli-testing | 100% | 31% | 4 | 9 | 0 |
| tiny-language-implementation | 100% | 40% | 4 | 6 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-near | skill-authoring | — | — | NO |
| sa-mid | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| oat-mid | offline-agent-testing | offline-agent-testing | — | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | — | yes |
| gte-near | generator-trampoline-evaluator | tiny-language-implementation,generator-trampoline-evaluator | — | NO |
| gte-mid | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-far | generator-trampoline-evaluator | skill-authoring,subprocess-cli-testing,agent-context-budgeting,generator-trampoline-evaluator,fuzz-mutate-kill-loop,offline-agent-testing,tiny-language-implementation | run | NO |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists,tiny-language-implementation,agent-context-budgeting,subprocess-cli-testing,fuzz-mutate-kill-loop | run | NO |
| stil-mid | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-far | shared-tip-immutable-lists | — | — | NO |
| fmk-near | fuzz-mutate-kill-loop | subprocess-cli-testing,tiny-language-implementation,agent-context-budgeting,fuzz-mutate-kill-loop | run | NO |
| fmk-mid | fuzz-mutate-kill-loop | subprocess-cli-testing | code-review,glob | NO |
| fmk-far | fuzz-mutate-kill-loop | — | security-review | NO |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | run | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | run | yes |
| sct-far | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| tli-near | tiny-language-implementation | tiny-language-implementation,subprocess-cli-testing,skill-authoring,agent-context-budgeting | — | NO |
| tli-mid | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-far | tiny-language-implementation | tiny-language-implementation,subprocess-cli-testing,skill-authoring | run,init,cli-dev-env | NO |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation,subprocess-cli-testing | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | fuzz-mutate-kill-loop,tiny-language-implementation,subprocess-cli-testing,agent-context-budgeting,skill-authoring,generator-trampoline-evaluator | run,init,code-review | NO |
| neg-1 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-3 | — | subprocess-cli-testing | run | NO |
| neg-4 | — | — | — | yes |
| neg-5 | — | — | — | yes |
| neg-6 | — | — | run | yes |
| leb-near | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-mid | llm-engine-benchmarking | — | — | NO |
| leb-far | llm-engine-benchmarking | — | claude-api | NO |
| leb-neg | — | subprocess-cli-testing | run | NO |
| fmk-oracle | fuzz-mutate-kill-loop | generator-trampoline-evaluator | — | NO |
| fmk-modelreview | fuzz-mutate-kill-loop | — | — | NO |
| fmk-timeouts | fuzz-mutate-kill-loop | — | — | NO |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# per-model comparison

| skill | sonnet recall | haiku recall |
|---|---|---|
| agent-context-budgeting | 100% | 100% |
| fuzz-mutate-kill-loop | 100% | 29% |
| generator-trampoline-evaluator | 100% | 75% |
| llm-engine-benchmarking | 100% | 33% |
| offline-agent-testing | 100% | 100% |
| shared-tip-immutable-lists | 100% | 67% |
| skill-authoring | 100% | 67% |
| subprocess-cli-testing | 100% | 100% |
| tiny-language-implementation | 75% | 100% |

| metric | sonnet | haiku |
|---|---|---|
| exact-match | 97% | 51% |
| neg false-fire | 0/7 | 2/7 |
| errored | 0 | 0 |
| displaced | 0 | 0 |
| cost | $1.581 | $1.544 |
