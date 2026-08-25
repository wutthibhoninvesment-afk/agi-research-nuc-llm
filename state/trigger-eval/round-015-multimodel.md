# skill trigger eval — mode=native model=sonnet

probes: 39 ok, 0 errored, exact-match 100%, negatives false-fire 0/7, cost $1.606

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
| tiny-language-implementation | 100% | 100% | 4 | 0 | 0 |

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
| acb-far | agent-context-budgeting | agent-context-budgeting | — | yes |
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
| tli-mid | tiny-language-implementation | tiny-language-implementation | — | yes |
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

probes: 39 ok, 0 errored, exact-match 51%, negatives false-fire 2/7, cost $1.683

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 33% | 10% | 1 | 9 | 2 |
| fuzz-mutate-kill-loop | 100% | 100% | 7 | 0 | 0 |
| generator-trampoline-evaluator | 50% | 100% | 2 | 0 | 2 |
| llm-engine-benchmarking | 33% | 100% | 1 | 0 | 2 |
| offline-agent-testing | 100% | 75% | 3 | 1 | 0 |
| shared-tip-immutable-lists | 67% | 100% | 2 | 0 | 1 |
| skill-authoring | 0% | n/a | 0 | 0 | 3 |
| subprocess-cli-testing | 100% | 40% | 4 | 6 | 0 |
| tiny-language-implementation | 100% | 67% | 4 | 2 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-near | skill-authoring | — | — | NO |
| sa-mid | skill-authoring | — | — | NO |
| sa-far | skill-authoring | subprocess-cli-testing | — | NO |
| oat-near | offline-agent-testing | offline-agent-testing,agent-context-budgeting,subprocess-cli-testing | — | NO |
| oat-mid | offline-agent-testing | offline-agent-testing,agent-context-budgeting,subprocess-cli-testing | — | NO |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| acb-near | agent-context-budgeting | — | — | NO |
| acb-mid | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-far | agent-context-budgeting | — | claude-api | NO |
| gte-near | generator-trampoline-evaluator | tiny-language-implementation | — | NO |
| gte-mid | generator-trampoline-evaluator | tiny-language-implementation,generator-trampoline-evaluator,subprocess-cli-testing | — | NO |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator,subprocess-cli-testing,agent-context-budgeting | — | NO |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists,agent-context-budgeting | — | NO |
| stil-mid | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-far | shared-tip-immutable-lists | — | — | NO |
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| sct-near | subprocess-cli-testing | subprocess-cli-testing,agent-context-budgeting | run | NO |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing,agent-context-budgeting | — | NO |
| sct-far | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| tli-near | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-mid | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-far | tiny-language-implementation | tiny-language-implementation | — | yes |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation,subprocess-cli-testing | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | fuzz-mutate-kill-loop,agent-context-budgeting,offline-agent-testing | — | NO |
| neg-1 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-3 | — | agent-context-budgeting | — | NO |
| neg-4 | — | — | — | yes |
| neg-5 | — | — | — | yes |
| neg-6 | — | agent-context-budgeting,subprocess-cli-testing | run | NO |
| leb-near | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-mid | llm-engine-benchmarking | — | — | NO |
| leb-far | llm-engine-benchmarking | — | — | NO |
| leb-neg | — | — | init | yes |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-modelreview | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# per-model comparison

| skill | sonnet recall | haiku recall |
|---|---|---|
| agent-context-budgeting | 100% | 33% |
| fuzz-mutate-kill-loop | 100% | 100% |
| generator-trampoline-evaluator | 100% | 50% |
| llm-engine-benchmarking | 100% | 33% |
| offline-agent-testing | 100% | 100% |
| shared-tip-immutable-lists | 100% | 67% |
| skill-authoring | 100% | 0% |
| subprocess-cli-testing | 100% | 100% |
| tiny-language-implementation | 100% | 100% |

| metric | sonnet | haiku |
|---|---|---|
| exact-match | 100% | 51% |
| neg false-fire | 0/7 | 2/7 |
| errored | 0 | 0 |
| displaced | 0 | 0 |
| cost | $1.606 | $1.683 |
