# skill trigger eval — mode=native model=sonnet protocol=strict

probes: 6 ok, 0 errored, exact-match 100%, negatives false-fire 0/0, cost $0.485

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-completion-guards | n/a | n/a | 0 | 0 | 0 |
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| carried-claim-rot | n/a | n/a | 0 | 0 | 0 |
| citation-registry-integrity | 100% | 100% | 6 | 0 | 0 |
| colocated-model-lane | n/a | n/a | 0 | 0 | 0 |
| copied-mirror-drift | n/a | n/a | 0 | 0 | 0 |
| declaration-scope-parity | n/a | n/a | 0 | 0 | 0 |
| deleted-vs-never-written | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| errors-that-name-the-fix | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | n/a | n/a | 0 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| one-shot-agent-no-background-wait | n/a | n/a | 0 | 0 | 0 |
| optimization-transparency-differential | n/a | n/a | 0 | 0 | 0 |
| prediction-banking | n/a | n/a | 0 | 0 | 0 |
| preflight-priced-task-scripts | n/a | n/a | 0 | 0 | 0 |
| pristine-checkout-differential | n/a | n/a | 0 | 0 | 0 |
| sampled-interval-brackets | n/a | n/a | 0 | 0 | 0 |
| self-updating-driver-loop | n/a | n/a | 0 | 0 | 0 |
| session-inheritance-audit | n/a | n/a | 0 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |
| unenforced-documented-rule | n/a | n/a | 0 | 0 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| cri-near | 2 | 2 (100%) | 2 (100%) | 0 |
| cri-mid | 2 | 2 (100%) | 2 (100%) | 0 |
| cri-far | 2 | 2 (100%) | 2 (100%) | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| cri-near | citation-registry-integrity | citation-registry-integrity | — | yes |
| cri-near | citation-registry-integrity | citation-registry-integrity | — | yes |
| cri-mid | citation-registry-integrity | citation-registry-integrity | — | yes |
| cri-mid | citation-registry-integrity | citation-registry-integrity | — | yes |
| cri-far | citation-registry-integrity | citation-registry-integrity | — | yes |
| cri-far | citation-registry-integrity | citation-registry-integrity | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# comparison vs baseline state/trigger-eval/round-357-full-corpus.json — model=sonnet
exact-match 90% -> 100%; negatives false-fire 0/17 -> 0/0; verdicts: 102 dropped, 2 same, 1 low-n
descriptions edited since the baseline: citation-registry-integrity

| case | expect | base fired | new fired | Δ | base exact | new exact | verdict |
|---|---|---|---|---|---|---|---|
| cri-near | citation-registry-integrity | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| cri-mid | citation-registry-integrity | 1/1 | 2/2 | +0% | 1/1 | 2/2 | same |
| cri-far | citation-registry-integrity | 0/1 | 2/2 | +100% | 0/1 | 2/2 | low-n |
| sa-near | skill-authoring | 1/1 | — | — | 1/1 | — | dropped |
| sa-mid | skill-authoring | 1/1 | — | — | 1/1 | — | dropped |
| sa-far | skill-authoring | 1/1 | — | — | 1/1 | — | dropped |
| oat-near | offline-agent-testing | 1/1 | — | — | 1/1 | — | dropped |
| oat-mid | offline-agent-testing | 1/1 | — | — | 1/1 | — | dropped |
| oat-far | offline-agent-testing | 1/1 | — | — | 1/1 | — | dropped |
| acb-near | agent-context-budgeting | 1/1 | — | — | 1/1 | — | dropped |
| acb-mid | agent-context-budgeting | 1/1 | — | — | 1/1 | — | dropped |
| acb-far | agent-context-budgeting | 1/1 | — | — | 1/1 | — | dropped |
| gte-near | generator-trampoline-evaluator | 1/1 | — | — | 1/1 | — | dropped |
| gte-mid | generator-trampoline-evaluator | 1/1 | — | — | 1/1 | — | dropped |
| gte-far | generator-trampoline-evaluator | 1/1 | — | — | 1/1 | — | dropped |
| stil-near | shared-tip-immutable-lists | 1/1 | — | — | 1/1 | — | dropped |
| stil-mid | shared-tip-immutable-lists | 1/1 | — | — | 1/1 | — | dropped |
| stil-far | shared-tip-immutable-lists | 1/1 | — | — | 1/1 | — | dropped |
| fmk-near | fuzz-mutate-kill-loop | 0/1 | — | — | 0/1 | — | dropped |
| fmk-mid | fuzz-mutate-kill-loop | 1/1 | — | — | 1/1 | — | dropped |
| fmk-far | fuzz-mutate-kill-loop | 1/1 | — | — | 1/1 | — | dropped |
| sct-near | subprocess-cli-testing | 1/1 | — | — | 1/1 | — | dropped |
| sct-mid | subprocess-cli-testing | 1/1 | — | — | 1/1 | — | dropped |
| sct-far | subprocess-cli-testing | 1/1 | — | — | 1/1 | — | dropped |
| tli-near | tiny-language-implementation | 1/1 | — | — | 1/1 | — | dropped |
| tli-mid | tiny-language-implementation | 1/1 | — | — | 1/1 | — | dropped |
| tli-far | tiny-language-implementation | 1/1 | — | — | 1/1 | — | dropped |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | 1/1 | — | — | 1/1 | — | dropped |
| multi-2 | fuzz-mutate-kill-loop,generator-trampoline-evaluator | 1/1 | — | — | 1/1 | — | dropped |
| sib-near | sampled-interval-brackets | 1/1 | — | — | 1/1 | — | dropped |
| sib-mid | sampled-interval-brackets | 1/1 | — | — | 1/1 | — | dropped |
| sib-far | sampled-interval-brackets | 1/1 | — | — | 1/1 | — | dropped |
| etnf-near | errors-that-name-the-fix | 1/1 | — | — | 1/1 | — | dropped |
| etnf-mid | errors-that-name-the-fix | 1/1 | — | — | 1/1 | — | dropped |
| etnf-far | errors-that-name-the-fix | 1/1 | — | — | 1/1 | — | dropped |
| pcd-near | pristine-checkout-differential | 1/1 | — | — | 1/1 | — | dropped |
| pcd-mid | pristine-checkout-differential | 0/1 | — | — | 0/1 | — | dropped |
| pcd-far | pristine-checkout-differential | 0/1 | — | — | 0/1 | — | dropped |
| udr-near | unenforced-documented-rule | 1/1 | — | — | 1/1 | — | dropped |
| udr-mid | unenforced-documented-rule | 1/1 | — | — | 0/1 | — | dropped |
| udr-far | unenforced-documented-rule | 1/1 | — | — | 1/1 | — | dropped |
| neg-1 | — | 1/1 | — | — | 1/1 | — | dropped |
| neg-2 | — | 1/1 | — | — | 1/1 | — | dropped |
| neg-3 | — | 1/1 | — | — | 1/1 | — | dropped |
| neg-4 | — | 1/1 | — | — | 1/1 | — | dropped |
| neg-5 | — | 1/1 | — | — | 1/1 | — | dropped |
| neg-6 | — | 1/1 | — | — | 1/1 | — | dropped |
| leb-near | llm-engine-benchmarking | 1/1 | — | — | 1/1 | — | dropped |
| leb-mid | llm-engine-benchmarking | 1/1 | — | — | 1/1 | — | dropped |
| leb-far | llm-engine-benchmarking | 1/1 | — | — | 1/1 | — | dropped |
| leb-neg | — | 1/1 | — | — | 1/1 | — | dropped |
| fmk-oracle | fuzz-mutate-kill-loop | 1/1 | — | — | 1/1 | — | dropped |
| fmk-modelreview | fuzz-mutate-kill-loop | 1/1 | — | — | 1/1 | — | dropped |
| fmk-timeouts | fuzz-mutate-kill-loop | 1/1 | — | — | 1/1 | — | dropped |
| epr-near | engine-prefix-reuse-audit | 1/1 | — | — | 1/1 | — | dropped |
| epr-mid | engine-prefix-reuse-audit | 1/1 | — | — | 1/1 | — | dropped |
| epr-far | engine-prefix-reuse-audit | 1/1 | — | — | 1/1 | — | dropped |
| pb-near | prediction-banking | 1/1 | — | — | 1/1 | — | dropped |
| pb-mid | prediction-banking | 1/1 | — | — | 1/1 | — | dropped |
| pb-far | prediction-banking | 1/1 | — | — | 1/1 | — | dropped |
| sia-near | session-inheritance-audit | 1/1 | — | — | 1/1 | — | dropped |
| sia-mid | session-inheritance-audit | 1/1 | — | — | 1/1 | — | dropped |
| sia-far | session-inheritance-audit | 1/1 | — | — | 1/1 | — | dropped |
| pb-neg | — | 1/1 | — | — | 1/1 | — | dropped |
| sia-neg | — | 1/1 | — | — | 1/1 | — | dropped |
| pm-neg | — | 1/1 | — | — | 1/1 | — | dropped |
| cml-near | colocated-model-lane | 1/1 | — | — | 1/1 | — | dropped |
| cml-mid | colocated-model-lane | 1/1 | — | — | 1/1 | — | dropped |
| cml-far | colocated-model-lane | 1/1 | — | — | 1/1 | — | dropped |
| cml-neg | — | 1/1 | — | — | 1/1 | — | dropped |
| acg-near | agent-completion-guards | 1/1 | — | — | 1/1 | — | dropped |
| acg-mid | agent-completion-guards | 1/1 | — | — | 1/1 | — | dropped |
| acg-far | agent-completion-guards | 1/1 | — | — | 1/1 | — | dropped |
| acg-neg | — | 1/1 | — | — | 1/1 | — | dropped |
| pts-near | preflight-priced-task-scripts | 1/1 | — | — | 1/1 | — | dropped |
| pts-mid | preflight-priced-task-scripts | 1/1 | — | — | 1/1 | — | dropped |
| pts-far | preflight-priced-task-scripts | 1/1 | — | — | 1/1 | — | dropped |
| pts-neg | llm-engine-benchmarking | 1/1 | — | — | 1/1 | — | dropped |
| sudl-near | self-updating-driver-loop | 1/1 | — | — | 1/1 | — | dropped |
| sudl-mid | self-updating-driver-loop | 1/1 | — | — | 1/1 | — | dropped |
| sudl-far | self-updating-driver-loop | 1/1 | — | — | 1/1 | — | dropped |
| sudl-neg | — | 1/1 | — | — | 1/1 | — | dropped |
| sia-concurrent | session-inheritance-audit | 1/1 | — | — | 1/1 | — | dropped |
| obw-near | one-shot-agent-no-background-wait | 1/1 | — | — | 1/1 | — | dropped |
| obw-mid | one-shot-agent-no-background-wait | 1/1 | — | — | 1/1 | — | dropped |
| obw-far | one-shot-agent-no-background-wait | 1/1 | — | — | 1/1 | — | dropped |
| obw-neg | — | 1/1 | — | — | 1/1 | — | dropped |
| otd-near | optimization-transparency-differential | 0/1 | — | — | 0/1 | — | dropped |
| otd-mid | optimization-transparency-differential | 1/1 | — | — | 1/1 | — | dropped |
| otd-far | optimization-transparency-differential | 0/1 | — | — | 0/1 | — | dropped |
| neg-15 | — | 1/1 | — | — | 1/1 | — | dropped |
| dvnw-near | deleted-vs-never-written | 0/1 | — | — | 0/1 | — | dropped |
| dvnw-mid | deleted-vs-never-written | 1/1 | — | — | 1/1 | — | dropped |
| dvnw-far | deleted-vs-never-written | 0/1 | — | — | 0/1 | — | dropped |
| neg-16 | — | 1/1 | — | — | 1/1 | — | dropped |
| neg-17 | — | 1/1 | — | — | 1/1 | — | dropped |
| ccr-near | carried-claim-rot | 1/1 | — | — | 1/1 | — | dropped |
| ccr-mid | carried-claim-rot | 1/1 | — | — | 1/1 | — | dropped |
| ccr-far | carried-claim-rot | 1/1 | — | — | 1/1 | — | dropped |
| cmd-near | copied-mirror-drift | 1/1 | — | — | 1/1 | — | dropped |
| cmd-mid | copied-mirror-drift | 1/1 | — | — | 1/1 | — | dropped |
| cmd-far | copied-mirror-drift | 1/1 | — | — | 1/1 | — | dropped |
| dsp-near | declaration-scope-parity | 1/1 | — | — | 1/1 | — | dropped |
| dsp-mid | declaration-scope-parity | 1/1 | — | — | 1/1 | — | dropped |
| dsp-far | declaration-scope-parity | 1/1 | — | — | 0/1 | — | dropped |
