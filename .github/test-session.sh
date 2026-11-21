#!/usr/bin/env bash
# Smoke test with real image entrypoint and an isolated virtual display.
set -euo pipefail
image=${1:?Provide the image name or ID.}
mounts=()
if [[ $# == 2 ]]; then
    home_dir=$(realpath -e -- "$2")
    mounts+=(--mount "type=bind,src=$home_dir,dst=/home/default")
fi
id=$(docker run -d --rm --init --network none --security-opt=no-new-privileges --shm-size=512m "${mounts[@]}" "$image")
trap 'docker stop -t 3 "$id" >/dev/null 2>&1 || true' EXIT
for ((attempt=0; attempt<30; attempt++)); do
    if docker exec "$id" curl -ksSf --max-time 1 -o /dev/null https://127.0.0.1:47990 2>/dev/null; then break; fi
    [[ $(docker inspect --format '{{.State.Running}}' "$id" 2>/dev/null || true) == true ]] || exit 1
    sleep 1
done
(( attempt < 30 ))
docker exec --user gamer "$id" bash -ec '
    auth=(/tmp/xvfb-run.*/Xauthority)
    export DISPLAY=:99 XAUTHORITY=${auth[0]}
    windows=$(xwininfo -root -tree)
    if [[ $windows == *gnome-session-failed* ]]; then
        printf "GNOME session failure dialog detected.\n" >&2
        exit 1
    fi
    [[ $windows == *"GNOME Shell"* ]]
    busctl --system status org.freedesktop.PolicyKit1 >/dev/null
    busctl --system status org.freedesktop.UPower >/dev/null
    pgrep -x gsd-power >/dev/null
    test -s "$HOME/.config/sunshine/sunshine.conf"
    printf "GNOME and Sunshine session ready.\n"
'
