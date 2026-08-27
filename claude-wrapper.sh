#!/usr/bin/env bash
cd /home/pgain/agi-research-nuc-llm
source .venv/bin/activate
export PATH="$PWD/node_modules/.bin:$PATH"
node_modules/.bin/claude "$@"
