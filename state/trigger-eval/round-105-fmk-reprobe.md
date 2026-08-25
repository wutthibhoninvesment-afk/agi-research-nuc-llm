# skill trigger eval — mode=native model=sonnet

probes: 27 ok, 0 errored, exact-match 89%, negatives false-fire 0/0, cost $1.362
declared-not-invoked: 3 probe(s) wrote SKILLS=<expected> without a Skill tool_use (protocol artifact — re-probe before treating the miss as a selection failure)

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | 86% | 100% | 18 | 0 | 3 |
| generator-trampoline-evaluator | 100% | 100% | 3 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | 100% | 100% | 6 | 0 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| fmk-near | 3 | 3 (100%) | 3 (100%) | 0 |
| fmk-mid | 3 | 3 (100%) | 3 (100%) | 0 |
| fmk-far | 3 | 0 (0%) | 0 (0%) | 0 |
| tli-near | 3 | 3 (100%) | 3 (100%) | 0 |
| tli-far | 3 | 3 (100%) | 3 (100%) | 0 |
| multi-2 | 3 | 3 (100%) | 3 (100%) | 0 |
| fmk-oracle | 3 | 3 (100%) | 3 (100%) | 0 |
| fmk-modelreview | 3 | 3 (100%) | 3 (100%) | 0 |
| fmk-timeouts | 3 | 3 (100%) | 3 (100%) | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | — | — | NO |
| fmk-far | fuzz-mutate-kill-loop | — | — | NO |
| fmk-far | fuzz-mutate-kill-loop | — | — | NO |
| tli-near | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-near | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-near | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-far | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-far | tiny-language-implementation | tiny-language-implementation | — | yes |
| tli-far | tiny-language-implementation | tiny-language-implementation | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | generator-trampoline-evaluator,fuzz-mutate-kill-loop | — | yes |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-modelreview | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-modelreview | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-modelreview | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# comparison vs baseline state/trigger-eval/round-105-sonnet-full.json — model=sonnet
exact-match 95% -> 89%; negatives false-fire 0/14 -> 0/0; verdicts: 33 dropped, 7 same, 1 IMPROVED, 1 noise?

| case | expect | base fired | new fired | Δ | base exact | new exact | verdict |
|---|---|---|---|---|---|---|---|
| fmk-near | fuzz-mutate-kill-loop | 2/2 | 3/3 | +0% | 1/2 | 3/3 | noise? |
| fmk-mid | fuzz-mutate-kill-loop | 2/2 | 3/3 | +0% | 2/2 | 3/3 | same |
| fmk-far | fuzz-mutate-kill-loop | 0/2 | 0/3 | +0% | 0/2 | 0/3 | same |
| tli-near | tiny-language-implementation | 2/2 | 3/3 | +0% | 2/2 | 3/3 | same |
| tli-far | tiny-language-implementation | 2/2 | 3/3 | +0% | 2/2 | 3/3 | same |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | 2/2 | 3/3 | +0% | 2/2 | 3/3 | same |
| fmk-oracle | fuzz-mutate-kill-loop | 2/2 | 3/3 | +0% | 2/2 | 3/3 | same |
| fmk-modelreview | fuzz-mutate-kill-loop | 1/2 | 3/3 | +50% | 1/2 | 3/3 | IMPROVED |
| fmk-timeouts | fuzz-mutate-kill-loop | 2/2 | 3/3 | +0% | 2/2 | 3/3 | same |
| sa-near | skill-authoring | 2/2 | — | — | 2/2 | — | dropped |
| sa-mid | skill-authoring | 2/2 | — | — | 2/2 | — | dropped |
| sa-far | skill-authoring | 2/2 | — | — | 2/2 | — | dropped |
| oat-near | offline-agent-testing | 2/2 | — | — | 2/2 | — | dropped |
| oat-mid | offline-agent-testing | 2/2 | — | — | 2/2 | — | dropped |
| oat-far | offline-agent-testing | 2/2 | — | — | 2/2 | — | dropped |
| acb-near | agent-context-budgeting | 2/2 | — | — | 2/2 | — | dropped |
| acb-mid | agent-context-budgeting | 2/2 | — | — | 2/2 | — | dropped |
| acb-far | agent-context-budgeting | 2/2 | — | — | 2/2 | — | dropped |
| gte-near | generator-trampoline-evaluator | 2/2 | — | — | 2/2 | — | dropped |
| gte-mid | generator-trampoline-evaluator | 2/2 | — | — | 2/2 | — | dropped |
| gte-far | generator-trampoline-evaluator | 2/2 | — | — | 2/2 | — | dropped |
| stil-near | shared-tip-immutable-lists | 2/2 | — | — | 2/2 | — | dropped |
| stil-mid | shared-tip-immutable-lists | 2/2 | — | — | 2/2 | — | dropped |
| stil-far | shared-tip-immutable-lists | 2/2 | — | — | 2/2 | — | dropped |
| sct-near | subprocess-cli-testing | 2/2 | — | — | 2/2 | — | dropped |
| sct-mid | subprocess-cli-testing | 2/2 | — | — | 2/2 | — | dropped |
| sct-far | subprocess-cli-testing | 2/2 | — | — | 2/2 | — | dropped |
| tli-mid | tiny-language-implementation | 2/2 | — | — | 2/2 | — | dropped |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | 2/2 | — | — | 2/2 | — | dropped |
| neg-1 | — | 2/2 | — | — | 2/2 | — | dropped |
| neg-2 | — | 2/2 | — | — | 2/2 | — | dropped |
| neg-3 | — | 2/2 | — | — | 2/2 | — | dropped |
| neg-4 | — | 2/2 | — | — | 2/2 | — | dropped |
| neg-5 | — | 2/2 | — | — | 2/2 | — | dropped |
| neg-6 | — | 2/2 | — | — | 2/2 | — | dropped |
| leb-near | llm-engine-benchmarking | 2/2 | — | — | 2/2 | — | dropped |
| leb-mid | llm-engine-benchmarking | 2/2 | — | — | 2/2 | — | dropped |
| leb-far | llm-engine-benchmarking | 2/2 | — | — | 2/2 | — | dropped |
| leb-neg | — | 2/2 | — | — | 2/2 | — | dropped |
| epr-near | engine-prefix-reuse-audit | 2/2 | — | — | 2/2 | — | dropped |
| epr-mid | engine-prefix-reuse-audit | 2/2 | — | — | 2/2 | — | dropped |
| epr-far | engine-prefix-reuse-audit | 2/2 | — | — | 2/2 | — | dropped |
