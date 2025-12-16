#!/usr/bin/env bash
# Filters commits matching ^feat: or ^fix: and outputs Discord embeds JSON
# Usage: echo '$commits_json' | ./filter-commits.sh
#    or: ./filter-commits.sh < commits.json

set -euo pipefail

commits_json=$(cat)

embeds=$(echo "$commits_json" | jq -c '
  [.[] | select(.message | test("^(feat|fix):"; "m")) | {
    title: (.message | split("\n")[0]),
    url: .url
  }]
')

count=$(echo "$embeds" | jq 'length')

echo "count=$count"
echo "embeds=$embeds"
