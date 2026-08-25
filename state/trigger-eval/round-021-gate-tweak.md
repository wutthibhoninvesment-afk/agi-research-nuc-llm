# skill trigger eval — mode=native model=sonnet

probes: 16 ok, 0 errored, exact-match 94%, negatives false-fire 0/0, cost $0.687

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 100% | 6 | 0 | 0 |
| fuzz-mutate-kill-loop | 50% | 100% | 1 | 0 | 1 |
| generator-trampoline-evaluator | 100% | 100% | 4 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 2 | 0 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 2 | 0 | 0 |
| skill-authoring | 100% | 100% | 2 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-far | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| gte-far | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator | — | NO |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# skill trigger eval — mode=native model=haiku

probes: 16 ok, 0 errored, exact-match 44%, negatives false-fire 0/0, cost $0.589

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 75% | 6 | 2 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 2 | 0 | 0 |
| generator-trampoline-evaluator | 50% | 100% | 2 | 0 | 2 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | 100% | 50% | 2 | 2 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 2 | 0 | 0 |
| skill-authoring | 100% | 67% | 2 | 1 | 0 |
| subprocess-cli-testing | n/a | 0% | 0 | 6 | 0 |
| tiny-language-implementation | n/a | 0% | 0 | 1 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-far | skill-authoring | skill-authoring,subprocess-cli-testing | — | NO |
| sa-far | skill-authoring | skill-authoring,subprocess-cli-testing | run | NO |
| oat-near | offline-agent-testing | offline-agent-testing,subprocess-cli-testing | — | NO |
| oat-near | offline-agent-testing | offline-agent-testing,subprocess-cli-testing | — | NO |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting,subprocess-cli-testing | — | NO |
| acb-far | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | claude-api | yes |
| gte-far | generator-trampoline-evaluator | agent-context-budgeting,offline-agent-testing,generator-trampoline-evaluator | run | NO |
| gte-far | generator-trampoline-evaluator | skill-authoring,subprocess-cli-testing,offline-agent-testing,generator-trampoline-evaluator,agent-context-budgeting | — | NO |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-near | shared-tip-immutable-lists | shared-tip-immutable-lists | run,init | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | fuzz-mutate-kill-loop | — | NO |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | fuzz-mutate-kill-loop,tiny-language-implementation | — | NO |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# per-model comparison

| skill | sonnet recall | haiku recall |
|---|---|---|
| agent-context-budgeting | 100% | 100% |
| fuzz-mutate-kill-loop | 50% | 100% |
| generator-trampoline-evaluator | 100% | 50% |
| llm-engine-benchmarking | n/a | n/a |
| offline-agent-testing | 100% | 100% |
| shared-tip-immutable-lists | 100% | 100% |
| skill-authoring | 100% | 100% |
| subprocess-cli-testing | n/a | n/a |
| tiny-language-implementation | n/a | n/a |

| metric | sonnet | haiku |
|---|---|---|
| exact-match | 94% | 44% |
| neg false-fire | 0/0 | 0/0 |
| errored | 0 | 0 |
| displaced | 0 | 0 |
| cost | $0.687 | $0.589 |
