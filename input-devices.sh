#!/usr/bin/env bash
# Populate private evdev nodes from the kernel and the host's read-only udev metadata.
set -euo pipefail
shopt -s nullglob
[[ -e /.dockerenv && $EUID == 0 ]]
mode=${1:?Use init or watch.}
[[ $mode == init || $mode == watch ]]
install -d -m 0755 /dev/input

declare -A previous current
scan() {
    local entry dev db name alias label node signature major minor old
    current=()
    for entry in /sys/class/input/event*; do
        read -r dev < "$entry/dev" || continue
        [[ $dev =~ ^13:[0-9]+$ ]] || continue
        db="/run/udev/data/c$dev"
        [[ -f $db ]] || continue
        alias='' label=''
        if grep -Fxq 'S:input/steam-headless-kbd' "$db"; then
            alias=steam-headless-kbd; label='Bolt keyboard'
        elif grep -Fxq 'S:input/steam-headless-mouse-mxv' "$db"; then
            alias=steam-headless-mouse-mxv; label='Unifying mouse'
        elif grep -Fxq 'S:input/steam-headless-mouse-rcv' "$db"; then
            alias=steam-headless-mouse-rcv; label='Bolt mouse'
        elif [[ $(realpath -e "$entry" 2>/dev/null) == /sys/devices/virtual/* ]] &&
            grep -Fxq 'E:ID_INPUT_JOYSTICK=1' "$db" &&
            read -r name < "$entry/device/name" && [[ $name == 'Sunshine '* ]]; then
            alias=${entry##*/}
        fi
        [[ -n $alias ]] || continue
        node=/dev/input/$alias
        signature="$dev:$(stat -c '%i:%y' "$db" 2>/dev/null)" || continue
        current[$alias]=$signature
        old=${previous[$alias]:-}
        if [[ $old != "$signature" || ! -c $node ]]; then
            IFS=: read -r major minor <<< "$dev"
            rm -f -- "$node"
            mknod -m 0600 "$node" c "$major" "$minor"
            if [[ -z $label ]]; then
                chgrp gamer "$node"
                chmod 0660 "$node"
            elif [[ $mode == watch ]]; then
                # Reopen an already registered Xorg device, also when its minor is reused.
                runuser -u gamer -- env DISPLAY=:55 XAUTHORITY=/run/steam-headless/Xauthority \
                    xinput disable "$label" >/dev/null 2>&1 || true
                runuser -u gamer -- env DISPLAY=:55 XAUTHORITY=/run/steam-headless/Xauthority \
                    xinput enable "$label" >/dev/null 2>&1 || true
            fi
        fi
    done
    for alias in "${!previous[@]}"; do
        if [[ ! -v current[$alias] ]]; then rm -f -- "/dev/input/$alias"; fi
    done
    previous=()
    for alias in "${!current[@]}"; do previous[$alias]=${current[$alias]}; done
}

scan
if [[ $mode == watch ]]; then
    while sleep 1; do scan; done
fi
