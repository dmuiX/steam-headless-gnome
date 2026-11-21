#!/usr/bin/env bash
# Hash the Debian package indexes for the same base, components and architectures as the build.
set -euo pipefail
base=$(awk '$1 == "FROM" { print $2; exit }' Dockerfile)
[[ $base =~ ^debian:13-slim@sha256:[a-f0-9]{64}$ ]]
backports=$(realpath -e trixie-backports.sources)
docker run --rm --platform linux/amd64 \
    --mount "type=bind,src=$backports,dst=/etc/apt/sources.list.d/trixie-backports.sources,readonly" \
    --entrypoint /bin/bash "$base" -ec '
    set -o pipefail
    dpkg --add-architecture i386
    sed -i "s/^Components: main$/Components: main contrib non-free non-free-firmware/" /etc/apt/sources.list.d/debian.sources
    apt-get -o APT::Update::Error-Mode=any update -qq >&2
    cd /var/lib/apt/lists
    shopt -s nullglob
    indexes=(*_Packages*)
    (( ${#indexes[@]} > 0 ))
    sha256sum -- "${indexes[@]}" | LC_ALL=C sort | sha256sum | cut -d" " -f1
'
