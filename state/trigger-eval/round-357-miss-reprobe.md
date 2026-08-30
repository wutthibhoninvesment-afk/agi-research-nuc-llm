# skill trigger eval — mode=native model=sonnet protocol=strict

probes: 8 ok, 0 errored, exact-match 88%, negatives false-fire 0/0, cost $0.634

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-completion-guards | n/a | n/a | 0 | 0 | 0 |
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| carried-claim-rot | n/a | n/a | 0 | 0 | 0 |
| citation-registry-integrity | 0% | n/a | 0 | 0 | 1 |
| colocated-model-lane | n/a | n/a | 0 | 0 | 0 |
| copied-mirror-drift | n/a | n/a | 0 | 0 | 0 |
| declaration-scope-parity | n/a | n/a | 0 | 0 | 0 |
| deleted-vs-never-written | 100% | 100% | 2 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| errors-that-name-the-fix | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 1 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| one-shot-agent-no-background-wait | n/a | n/a | 0 | 0 | 0 |
| optimization-transparency-differential | 100% | 100% | 2 | 0 | 0 |
| prediction-banking | n/a | n/a | 0 | 0 | 0 |
| preflight-priced-task-scripts | n/a | n/a | 0 | 0 | 0 |
| pristine-checkout-differential | 100% | 100% | 2 | 0 | 0 |
| sampled-interval-brackets | n/a | n/a | 0 | 0 | 0 |
| self-updating-driver-loop | n/a | n/a | 0 | 0 | 0 |
| session-inheritance-audit | n/a | n/a | 0 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |
| unenforced-documented-rule | n/a | n/a | 0 | 0 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| pcd-mid | pristine-checkout-differential | pristine-checkout-differential | — | yes |
| pcd-far | pristine-checkout-differential | pristine-checkout-differential | — | yes |
| otd-near | optimization-transparency-differential | optimization-transparency-differential | — | yes |
| otd-far | optimization-transparency-differential | optimization-transparency-differential | — | yes |
| cri-far | citation-registry-integrity | — | — | NO |
| dvnw-near | deleted-vs-never-written | deleted-vs-never-written | — | yes |
| dvnw-far | deleted-vs-never-written | deleted-vs-never-written | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
