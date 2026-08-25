# skill trigger eval — mode=native model=sonnet

probes: 84 ok, 0 errored, exact-match 95%, negatives false-fire 0/14, cost $3.330

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 100% | 6 | 0 | 0 |
| engine-prefix-reuse-audit | 100% | 100% | 6 | 0 | 0 |
| fuzz-mutate-kill-loop | 79% | 100% | 11 | 0 | 3 |
| generator-trampoline-evaluator | 100% | 100% | 8 | 0 | 0 |
| llm-engine-benchmarking | 100% | 100% | 6 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 6 | 0 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 6 | 0 | 0 |
| skill-authoring | 100% | 100% | 6 | 0 | 0 |
| subprocess-cli-testing | 100% | 100% | 8 | 0 | 0 |
| tiny-language-implementation | 100% | 80% | 8 | 2 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| sa-near | 2 | 2 (100%) | 2 (100%) | 0 |
| sa-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| sa-far | 2 | 2 (100%) | 2 (100%) | 0 |
| oat-near | 2 | 2 (100%) | 2 (100%) | 0 |
| oat-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| oat-far | 2 | 2 (100%) | 2 (100%) | 0 |
| acb-near | 2 | 2 (100%) | 2 (100%) | 0 |
| acb-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| acb-far | 2 | 2 (100%) | 2 (100%) | 0 |
| gte-near | 2 | 2 (100%) | 2 (100%) | 0 |
| gte-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| gte-far | 2 | 2 (100%) | 2 (100%) | 0 |
| stil-near | 2 | 2 (100%) | 2 (100%) | 0 |
| stil-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| stil-far | 2 | 2 (100%) | 2 (100%) | 0 |
| fmk-near | 2 | 2 (100%) | 1 (50%) | 0 |
| fmk-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| fmk-far | 2 | 0 (0%) | 0 (0%) | 0 |
| sct-near | 2 | 2 (100%) | 2 (100%) | 0 |
| sct-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| sct-far | 2 | 2 (100%) | 2 (100%) | 0 |
| tli-near | 2 | 2 (100%) | 2 (100%) | 0 |
| tli-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| tli-far | 2 | 2 (100%) | 2 (100%) | 0 |
| multi-1 | 2 | 2 (100%) | 2 (100%) | 0 |
| multi-2 | 2 | 2 (100%) | 2 (100%) | 0 |
| neg-1 | 2 | 2 (100%) | 2 (100%) | 0 |
| neg-2 | 2 | 2 (100%) | 2 (100%) | 0 |
| neg-3 | 2 | 2 (100%) | 2 (100%) | 0 |
| neg-4 | 2 | 2 (100%) | 2 (100%) | 0 |
| neg-5 | 2 | 2 (100%) | 2 (100%) | 0 |
| neg-6 | 2 | 2 (100%) | 2 (100%) | 0 |
| leb-near | 2 | 2 (100%) | 2 (100%) | 0 |
| leb-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| leb-far | 2 | 2 (100%) | 2 (100%) | 0 |
| leb-neg | 2 | 2 (100%) | 2 (100%) | 0 |
| fmk-oracle | 2 | 2 (100%) | 2 (100%) | 0 |
| fmk-modelreview | 2 | 1 (50%) | 1 (50%) | 0 |
| fmk-timeouts | 2 | 2 (100%) | 2 (100%) | 0 |
| epr-near | 2 | 2 (100%) | 2 (100%) | 0 |
| epr-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| epr-far | 2 | 2 (100%) | 2 (100%) | 0 |

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
| oat-mid | offline-agent-testing | offline-agent-testing | claude-api | yes |
| oat-mid | offline-agent-testing | offline-agent-testing | — | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| gte-near | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-near | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-mid | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-mid | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-mid | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-mid | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-far | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-far | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop,tiny-language-implementation | — | NO |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | tiny-language-implementation | — | NO |
| fmk-far | fuzz-mutate-kill-loop | — | security-review | NO |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-near | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-mid | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-far | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-far | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| tli-near | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-near | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-mid | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-mid | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-far | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-far | tiny-language-implementation | tiny-language-implementation | — | yes |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation,subprocess-cli-testing | — | yes |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation,subprocess-cli-testing | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |
| neg-1 | — | — | — | yes |
| neg-1 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-2 | — | — | — | yes |
| neg-3 | — | — | — | yes |
| neg-3 | — | — | — | yes |
| neg-4 | — | — | — | yes |
| neg-4 | — | — | — | yes |
| neg-5 | — | — | — | yes |
| neg-5 | — | — | — | yes |
| neg-6 | — | — | — | yes |
| neg-6 | — | — | — | yes |
| leb-near | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-near | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-mid | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-mid | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-far | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-far | llm-engine-benchmarking | llm-engine-benchmarking | — | yes |
| leb-neg | — | — | — | yes |
| leb-neg | — | — | — | yes |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-modelreview | fuzz-mutate-kill-loop | — | — | NO |
| fmk-modelreview | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | code-review | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| epr-near | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-near | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-mid | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-mid | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-far | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-far | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
