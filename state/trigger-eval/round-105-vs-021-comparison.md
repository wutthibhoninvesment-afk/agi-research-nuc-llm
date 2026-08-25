# comparison vs baseline round-021-final-dualmodel.json — model=sonnet
exact-match 97% -> 95%; negatives false-fire 0/7 -> 0/14; verdicts: 35 same, 3 new, 2 REGRESSED, 1 CO-FIRE, 1 IMPROVED

| case | expect | base fired | new fired | Δ | base exact | new exact | verdict |
|---|---|---|---|---|---|---|---|
| sa-near | skill-authoring | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| sa-mid | skill-authoring | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| sa-far | skill-authoring | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| oat-near | offline-agent-testing | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| oat-mid | offline-agent-testing | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| oat-far | offline-agent-testing | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| acb-near | agent-context-budgeting | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| acb-mid | agent-context-budgeting | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| acb-far | agent-context-budgeting | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| gte-near | generator-trampoline-evaluator | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| gte-mid | generator-trampoline-evaluator | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| gte-far | generator-trampoline-evaluator | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| stil-near | shared-tip-immutable-lists | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| stil-mid | shared-tip-immutable-lists | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| stil-far | shared-tip-immutable-lists | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| fmk-near | fuzz-mutate-kill-loop | 1/1 | 2/2 | +0% | 1/1 | 1/2 | CO-FIRE |
| fmk-mid | fuzz-mutate-kill-loop | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| fmk-far | fuzz-mutate-kill-loop | 1/1 | 0/2 | -100% | 1/1 | 0/2 | REGRESSED |
| sct-near | subprocess-cli-testing | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| sct-mid | subprocess-cli-testing | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| sct-far | subprocess-cli-testing | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| tli-near | tiny-language-implementation | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| tli-mid | tiny-language-implementation | 0/1 | 2/2 | +100% | 0/1 | 2/2 | IMPROVED |
| tli-far | tiny-language-implementation | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| neg-1 | — | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| neg-2 | — | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| neg-3 | — | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| neg-4 | — | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| neg-5 | — | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| neg-6 | — | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| leb-near | llm-engine-benchmarking | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| leb-mid | llm-engine-benchmarking | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| leb-far | llm-engine-benchmarking | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| leb-neg | — | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| fmk-oracle | fuzz-mutate-kill-loop | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| fmk-modelreview | fuzz-mutate-kill-loop | 1/1 | 1/2 | -50% | 1/1 | 1/2 | REGRESSED |
| fmk-timeouts | fuzz-mutate-kill-loop | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| epr-near | engine-prefix-reuse-audit | — | 2/2 | — | — | 2/2 | new |
| epr-mid | engine-prefix-reuse-audit | — | 2/2 | — | — | 2/2 | new |
| epr-far | engine-prefix-reuse-audit | — | 2/2 | — | — | 2/2 | new |
