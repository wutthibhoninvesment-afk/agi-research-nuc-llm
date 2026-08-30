# skill trigger eval — mode=native model=sonnet protocol=strict

probes: 105 ok, 0 errored, exact-match 90%, negatives false-fire 0/17, cost $6.861
declared-not-invoked: 1 probe(s) wrote SKILLS=<expected> without a Skill tool_use (protocol artifact — re-probe before treating the miss as a selection failure)

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-completion-guards | 100% | 100% | 3 | 0 | 0 |
| agent-context-budgeting | 100% | 100% | 3 | 0 | 0 |
| carried-claim-rot | 100% | 100% | 3 | 0 | 0 |
| citation-registry-integrity | 67% | 100% | 2 | 0 | 1 |
| colocated-model-lane | 100% | 100% | 3 | 0 | 0 |
| copied-mirror-drift | 100% | 100% | 3 | 0 | 0 |
| declaration-scope-parity | 100% | 100% | 3 | 0 | 0 |
| deleted-vs-never-written | 33% | 100% | 1 | 0 | 2 |
| engine-prefix-reuse-audit | 100% | 100% | 3 | 0 | 0 |
| errors-that-name-the-fix | 100% | 75% | 3 | 1 | 0 |
| fuzz-mutate-kill-loop | 86% | 100% | 6 | 0 | 1 |
| generator-trampoline-evaluator | 100% | 80% | 4 | 1 | 0 |
| llm-engine-benchmarking | 100% | 100% | 4 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 3 | 0 | 0 |
| one-shot-agent-no-background-wait | 100% | 100% | 3 | 0 | 0 |
| optimization-transparency-differential | 33% | 100% | 1 | 0 | 2 |
| prediction-banking | 100% | 100% | 3 | 0 | 0 |
| preflight-priced-task-scripts | 100% | 100% | 3 | 0 | 0 |
| pristine-checkout-differential | 33% | 100% | 1 | 0 | 2 |
| sampled-interval-brackets | 100% | 100% | 3 | 0 | 0 |
| self-updating-driver-loop | 100% | 100% | 3 | 0 | 0 |
| session-inheritance-audit | 100% | 100% | 4 | 0 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 3 | 0 | 0 |
| skill-authoring | 100% | 100% | 3 | 0 | 0 |
| subprocess-cli-testing | 100% | 100% | 4 | 0 | 0 |
| tiny-language-implementation | 100% | 100% | 4 | 0 | 0 |
| unenforced-documented-rule | 100% | 75% | 3 | 1 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-near | skill-authoring | skill-authoring | — | yes |
| sa-mid | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |
| oat-near | offline-agent-testing | offline-agent-testing | — | yes |
| oat-mid | offline-agent-testing | offline-agent-testing | — | yes |
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
| fmk-near | fuzz-mutate-kill-loop | — | — | NO |
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
| sib-near | sampled-interval-brackets | sampled-interval-brackets | — | yes |
| sib-mid | sampled-interval-brackets | sampled-interval-brackets | — | yes |
| sib-far | sampled-interval-brackets | sampled-interval-brackets | — | yes |
| etnf-near | errors-that-name-the-fix | errors-that-name-the-fix | — | yes |
| etnf-mid | errors-that-name-the-fix | errors-that-name-the-fix | — | yes |
| etnf-far | errors-that-name-the-fix | errors-that-name-the-fix | — | yes |
| pcd-near | pristine-checkout-differential | pristine-checkout-differential | — | yes |
| pcd-mid | pristine-checkout-differential | — | — | NO |
| pcd-far | pristine-checkout-differential | — | — | NO |
| udr-near | unenforced-documented-rule | unenforced-documented-rule | — | yes |
| udr-mid | unenforced-documented-rule | errors-that-name-the-fix,unenforced-documented-rule | — | NO |
| udr-far | unenforced-documented-rule | unenforced-documented-rule | — | yes |
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
| epr-near | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-mid | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| epr-far | engine-prefix-reuse-audit | engine-prefix-reuse-audit | — | yes |
| pb-near | prediction-banking | prediction-banking | — | yes |
| pb-mid | prediction-banking | prediction-banking | — | yes |
| pb-far | prediction-banking | prediction-banking | — | yes |
| sia-near | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-mid | session-inheritance-audit | session-inheritance-audit | — | yes |
| sia-far | session-inheritance-audit | session-inheritance-audit | — | yes |
| pb-neg | — | — | — | yes |
| sia-neg | — | — | — | yes |
| pm-neg | — | — | — | yes |
| cml-near | colocated-model-lane | colocated-model-lane | — | yes |
| cml-mid | colocated-model-lane | colocated-model-lane | — | yes |
| cml-far | colocated-model-lane | colocated-model-lane | — | yes |
| cml-neg | — | — | — | yes |
| acg-near | agent-completion-guards | agent-completion-guards | — | yes |
| acg-mid | agent-completion-guards | agent-completion-guards | — | yes |
| acg-far | agent-completion-guards | agent-completion-guards | — | yes |
| acg-neg | — | — | — | yes |
| pts-near | preflight-priced-task-scripts | preflight-priced-task-scripts | — | yes |
| pts-mid | preflight-priced-task-scripts | preflight-priced-task-scripts | — | yes |
| pts-far | preflight-priced-task-scripts | preflight-priced-task-scripts | — | yes |
| pts-neg | llm-engine-benchmarking | llm-engine-benchmarking | dataviz | yes |
| sudl-near | self-updating-driver-loop | self-updating-driver-loop | — | yes |
| sudl-mid | self-updating-driver-loop | self-updating-driver-loop | — | yes |
| sudl-far | self-updating-driver-loop | self-updating-driver-loop | — | yes |
| sudl-neg | — | — | — | yes |
| sia-concurrent | session-inheritance-audit | session-inheritance-audit | — | yes |
| obw-near | one-shot-agent-no-background-wait | one-shot-agent-no-background-wait | — | yes |
| obw-mid | one-shot-agent-no-background-wait | one-shot-agent-no-background-wait | — | yes |
| obw-far | one-shot-agent-no-background-wait | one-shot-agent-no-background-wait | — | yes |
| obw-neg | — | — | — | yes |
| otd-near | optimization-transparency-differential | generator-trampoline-evaluator | — | NO |
| otd-mid | optimization-transparency-differential | optimization-transparency-differential | — | yes |
| otd-far | optimization-transparency-differential | — | — | NO |
| cri-near | citation-registry-integrity | citation-registry-integrity | — | yes |
| cri-mid | citation-registry-integrity | citation-registry-integrity | — | yes |
| cri-far | citation-registry-integrity | — | — | NO |
| neg-15 | — | — | — | yes |
| dvnw-near | deleted-vs-never-written | — | — | NO |
| dvnw-mid | deleted-vs-never-written | deleted-vs-never-written | — | yes |
| dvnw-far | deleted-vs-never-written | — | — | NO |
| neg-16 | — | — | — | yes |
| neg-17 | — | — | — | yes |
| ccr-near | carried-claim-rot | carried-claim-rot | update-config | yes |
| ccr-mid | carried-claim-rot | carried-claim-rot | — | yes |
| ccr-far | carried-claim-rot | carried-claim-rot | — | yes |
| cmd-near | copied-mirror-drift | copied-mirror-drift | — | yes |
| cmd-mid | copied-mirror-drift | copied-mirror-drift | — | yes |
| cmd-far | copied-mirror-drift | copied-mirror-drift | — | yes |
| dsp-near | declaration-scope-parity | declaration-scope-parity | — | yes |
| dsp-mid | declaration-scope-parity | declaration-scope-parity | — | yes |
| dsp-far | declaration-scope-parity | declaration-scope-parity,unenforced-documented-rule | — | NO |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
