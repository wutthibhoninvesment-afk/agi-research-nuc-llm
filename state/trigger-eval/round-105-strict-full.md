# skill trigger eval — mode=native model=sonnet

probes: 102 ok, 0 errored, exact-match 100%, negatives false-fire 0/20, cost $4.058

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 100% | 6 | 0 | 0 |
| engine-prefix-reuse-audit | 100% | 100% | 6 | 0 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 14 | 0 | 0 |
| generator-trampoline-evaluator | 100% | 100% | 8 | 0 | 0 |
| llm-engine-benchmarking | 100% | 100% | 6 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 6 | 0 | 0 |
| prediction-banking | 100% | 100% | 6 | 0 | 0 |
| session-inheritance-audit | 100% | 100% | 6 | 0 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 6 | 0 | 0 |
| skill-authoring | 100% | 100% | 6 | 0 | 0 |
| subprocess-cli-testing | 100% | 100% | 8 | 0 | 0 |
| tiny-language-implementation | 100% | 100% | 8 | 0 | 0 |

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
| fmk-near | 2 | 2 (100%) | 2 (100%) | 0 |
| fmk-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| fmk-far | 2 | 2 (100%) | 2 (100%) | 0 |
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
| fmk-modelreview | 2 | 2 (100%) | 2 (100%) | 0 |
| fmk-timeouts | 2 | 2 (100%) | 2 (100%) | 0 |
| epr-near | 2 | 2 (100%) | 2 (100%) | 0 |
| epr-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| epr-far | 2 | 2 (100%) | 2 (100%) | 0 |
| pb-near | 2 | 2 (100%) | 2 (100%) | 0 |
| pb-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| pb-far | 2 | 2 (100%) | 2 (100%) | 0 |
| sia-near | 2 | 2 (100%) | 2 (100%) | 0 |
| sia-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| sia-far | 2 | 2 (100%) | 2 (100%) | 0 |
| pb-neg | 2 | 2 (100%) | 2 (100%) | 0 |
| sia-neg | 2 | 2 (100%) | 2 (100%) | 0 |
| pm-neg | 2 | 2 (100%) | 2 (100%) | 0 |

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
| oat-mid | offline-agent-testing | offline-agent-testing | — | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-near | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-mid | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | — | yes |
| acb-far | agent-context-budgeting | agent-context-budgeting | — | yes |
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
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-mid | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
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
| fmk-modelreview | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-modelreview | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| epr-near | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-near | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-mid | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-mid | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-far | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-far | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| pb-near | prediction-banking | prediction-banking | — | yes |
| pb-near | prediction-banking | prediction-banking | — | yes |
| pb-mid | prediction-banking | prediction-banking | — | yes |
| pb-mid | prediction-banking | prediction-banking | — | yes |
| pb-far | prediction-banking | prediction-banking | — | yes |
| pb-far | prediction-banking | prediction-banking | — | yes |
| sia-near | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-near | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-mid | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-mid | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-far | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-far | session-inheritance-audit | session-inheritance-audit | — | yes |
| pb-neg | — | — | — | yes |
| pb-neg | — | — | — | yes |
| sia-neg | — | — | — | yes |
| sia-neg | — | — | — | yes |
| pm-neg | — | — | — | yes |
| pm-neg | — | — | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# comparison vs baseline state/trigger-eval/round-105-sonnet-full.json — model=sonnet
exact-match 95% -> 100%; negatives false-fire 0/14 -> 0/20; verdicts: 39 same, 9 new, 2 noise?, 1 IMPROVED

| case | expect | base fired | new fired | Δ | base exact | new exact | verdict |
|---|---|---|---|---|---|---|---|
| sa-near | skill-authoring | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| sa-mid | skill-authoring | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| sa-far | skill-authoring | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| oat-near | offline-agent-testing | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| oat-mid | offline-agent-testing | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| oat-far | offline-agent-testing | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| acb-near | agent-context-budgeting | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| acb-mid | agent-context-budgeting | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| acb-far | agent-context-budgeting | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| gte-near | generator-trampoline-evaluator | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| gte-mid | generator-trampoline-evaluator | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| gte-far | generator-trampoline-evaluator | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| stil-near | shared-tip-immutable-lists | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| stil-mid | shared-tip-immutable-lists | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| stil-far | shared-tip-immutable-lists | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| fmk-near | fuzz-mutate-kill-loop | 2/2 | 2/2 | +0% | 1/2 | 2/2 | noise? |
| fmk-mid | fuzz-mutate-kill-loop | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| fmk-far | fuzz-mutate-kill-loop | 0/2 | 2/2 | +100% | 0/2 | 2/2 | IMPROVED |
| sct-near | subprocess-cli-testing | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| sct-mid | subprocess-cli-testing | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| sct-far | subprocess-cli-testing | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| tli-near | tiny-language-implementation | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| tli-mid | tiny-language-implementation | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| tli-far | tiny-language-implementation | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| neg-1 | — | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| neg-2 | — | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| neg-3 | — | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| neg-4 | — | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| neg-5 | — | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| neg-6 | — | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| leb-near | llm-engine-benchmarking | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| leb-mid | llm-engine-benchmarking | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| leb-far | llm-engine-benchmarking | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| leb-neg | — | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| fmk-oracle | fuzz-mutate-kill-loop | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| fmk-modelreview | fuzz-mutate-kill-loop | 1/2 | 2/2 | +50% | 1/2 | 2/2 | noise? |
| fmk-timeouts | fuzz-mutate-kill-loop | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| epr-near | engine-prefix-reuse-audit | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| epr-mid | engine-prefix-reuse-audit | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| epr-far | engine-prefix-reuse-audit | 2/2 | 2/2 | +0% | 2/2 | 2/2 | same |
| pb-near | prediction-banking | — | 2/2 | — | — | 2/2 | new |
| pb-mid | prediction-banking | — | 2/2 | — | — | 2/2 | new |
| pb-far | prediction-banking | — | 2/2 | — | — | 2/2 | new |
| sia-near | session-inheritance-audit | — | 2/2 | — | — | 2/2 | new |
| sia-mid | session-inheritance-audit | — | 2/2 | — | — | 2/2 | new |
| sia-far | session-inheritance-audit | — | 2/2 | — | — | 2/2 | new |
| pb-neg | — | — | 2/2 | — | — | 2/2 | new |
| sia-neg | — | — | 2/2 | — | — | 2/2 | new |
| pm-neg | — | — | 2/2 | — | — | 2/2 | new |
