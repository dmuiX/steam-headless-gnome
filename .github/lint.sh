#!/usr/bin/env bash
set -euo pipefail
scripts=(start.sh bluez-env.sh input-devices.sh .github/*.sh)
for script in "${scripts[@]}"; do bash -n "$script"; done
shellcheck "${scripts[@]}"

if command -v actionlint >/dev/null; then
    actionlint
else
    tmp=$(mktemp -d)
    trap 'rm -rf -- "$tmp"' EXIT
    curl --fail --location --silent --show-error --proto '=https' --max-time 45 \
        https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz \
        -o "$tmp/actionlint.tar.gz"
    printf '%s  %s\n' 8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 \
        "$tmp/actionlint.tar.gz" | sha256sum --check --strict
    tar -xzf "$tmp/actionlint.tar.gz" -C "$tmp" actionlint
    "$tmp/actionlint"
fi
