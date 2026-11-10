#!/bin/bash
# run_all.sh - same as: python3 bilien.py <episodes> [--show "Name"]
#   bash run_all.sh 2-29 --show "My Show"
cd "$(dirname "$0")" && exec python3 bilien.py "$@"
