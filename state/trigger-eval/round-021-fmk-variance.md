# skill trigger eval — mode=native model=haiku

probes: 12 ok, 0 errored, exact-match 8%, negatives false-fire 0/0, cost $0.436

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | 42% | 100% | 5 | 0 | 7 |
| generator-trampoline-evaluator | n/a | 0% | 0 | 2 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | 0% | 0 | 1 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | 0% | 0 | 1 | 0 |
| subprocess-cli-testing | n/a | 0% | 0 | 3 | 0 |
| tiny-language-implementation | n/a | 0% | 0 | 1 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| fmk-near | fuzz-mutate-kill-loop | subprocess-cli-testing,fuzz-mutate-kill-loop,tiny-language-implementation | run,claude-api | NO |
| fmk-near | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop,offline-agent-testing,subprocess-cli-testing | run,init | NO |
| fmk-mid | fuzz-mutate-kill-loop | subprocess-cli-testing,skill-authoring | code-review,run,init | NO |
| fmk-mid | fuzz-mutate-kill-loop | — | — | NO |
| fmk-far | fuzz-mutate-kill-loop | — | security-review | NO |
| fmk-far | fuzz-mutate-kill-loop | — | security-review | NO |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop,generator-trampoline-evaluator | — | NO |
| fmk-oracle | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop,generator-trampoline-evaluator | — | NO |
| fmk-modelreview | fuzz-mutate-kill-loop | — | — | NO |
| fmk-modelreview | fuzz-mutate-kill-loop | — | — | NO |
| fmk-timeouts | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-timeouts | fuzz-mutate-kill-loop | — | — | NO |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec
