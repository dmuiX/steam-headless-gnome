#!/usr/bin/env bash
# Start the standalone GNOME/Xorg desktop and Sunshine inside Docker.
set -euo pipefail
[[ -e /.dockerenv ]] || { echo 'This script must run inside Docker.' >&2; exit 1; }
if [[ ${1:-} == --session ]]; then
    [[ $EUID != 0 ]] || exit 1
    gnome-session --session=gnome --disable-acceleration-check &
    gnome_pid=$!
    trap 'kill "$gnome_pid" "${sunshine_pid:-}" 2>/dev/null || true' EXIT
    for ((attempt=0; attempt<30; attempt++)); do
        kill -0 "$gnome_pid"
        wm=$(xprop -root _NET_SUPPORTING_WM_CHECK | awk '/window id #/ {print $NF}')
        if [[ -n $wm ]] && xprop -id "$wm" _NET_WM_NAME | grep -q 'GNOME Shell'; then
            echo 'GNOME Shell is active on X11.'
            break
        fi
        sleep 1
    done
    (( attempt < 30 )) || { echo 'GNOME did not become ready.' >&2; exit 1; }
    for ((attempt=0; attempt<15; attempt++)); do
        windows=$(xwininfo -root -tree)
        if [[ $windows == *gnome-session-failed* ]]; then
            echo 'GNOME displayed its session failure dialog.' >&2
            exit 1
        fi
        if pgrep -u "$UID" -x gsd-power >/dev/null; then break; fi
        sleep 1
    done
    (( attempt < 15 )) || { echo 'GNOME power settings daemon did not start.' >&2; exit 1; }
    umask 077
    config="$HOME/.config/sunshine/sunshine.conf"
    mkdir -p -- "$(dirname -- "$config")"
    if [[ ${PHYSICAL:-0} == 1 ]]; then
        if [[ -S /run/steam-headless-bluez/bus ]]; then
            DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/steam-headless-bluez/bus \
                pulseaudio --start --exit-idle-time=-1
        else
            pulseaudio --start --exit-idle-time=-1
        fi
        pactl load-module module-null-sink sink_name=steam_headless_audio >/dev/null
        pactl set-default-sink steam_headless_audio
        if [[ ! -e $config ]]; then
            printf 'capture = x11\nencoder = vaapi\nadapter_name = /dev/dri/renderD128\norigin_web_ui_allowed = lan\ngamepad = x360\nsystem_tray = disabled\n' > "$config"
        fi
    else
        if [[ ! -e $config ]]; then
            printf 'capture = x11\nencoder = software\norigin_web_ui_allowed = pc\n' > "$config"
        fi
    fi
    sunshine "$config" &
    sunshine_pid=$!
    status=0
    ended=unknown
    wait -n -p ended "$gnome_pid" "$sunshine_pid" || status=$?
    if [[ ${ended:-} == "$gnome_pid" ]]; then service=GNOME; else service=Sunshine; fi
    printf '%s session process exited (status %s).\n' "$service" "$status"
    exit "$status"
fi
runuser -u gamer -- test -w /home/default || { echo 'The desktop home is not writable by UID 1000.' >&2; exit 1; }
runtime_dir=/run/steam-headless
install -d -m 0700 -o gamer -g gamer "$runtime_dir"
install -d /run/dbus /run/systemd/seats /run/systemd/sessions /run/systemd/users
dbus-daemon --system --fork --nopidfile
/usr/lib/systemd/systemd-logind &
# D-Bus cannot activate its setuid helper under no-new-privileges.
# GNOME treats an unavailable UPower as a failed required session component.
wait_for_bus_name() {
    local name=$1 pid=$2 attempt
    for ((attempt=0; attempt<15; attempt++)); do
        if ! kill -0 "$pid" 2>/dev/null; then break; fi
        if busctl --system --timeout=1s status "$name" >/dev/null 2>&1; then return 0; fi
        sleep 1
    done
    printf '%s did not register on the system bus.\n' "$name" >&2
    return 1
}
/usr/lib/polkit-1/polkitd --no-debug &
wait_for_bus_name org.freedesktop.PolicyKit1 "$!"
/usr/libexec/upowerd &
wait_for_bus_name org.freedesktop.UPower "$!"
if [[ ${PHYSICAL:-0} == 1 ]]; then
    render_gid=$(stat -c %g /dev/dri/renderD128)
    if ! getent group "$render_gid" >/dev/null; then groupadd --gid "$render_gid" steam-render; fi
    render_group=$(getent group "$render_gid" | cut -d: -f1)
    usermod -aG "$render_group" gamer
    auth=$runtime_dir/Xauthority
    runuser -u gamer -- xauth -f "$auth" add :55 MIT-MAGIC-COOKIE-1 "$(mcookie)"
    [[ -c /dev/uinput ]] || mknod -m 0660 /dev/uinput c 10 223
    chgrp gamer /dev/uinput
    bash /usr/local/bin/steam-headless-input.sh init
    # These paths are private to this container; clear leftovers from an earlier exit.
    rm -f -- /tmp/.X55-lock /tmp/.X11-unix/X55
    Xorg :55 vt7 -auth "$auth" -noreset -novtswitch -sharevts -nolisten tcp -dpms -s off \
        -config /etc/X11/steam-headless.conf &
    xorg_pid=$!
    trap 'kill "$xorg_pid" "${session_pid:-}" "${input_pid:-}" 2>/dev/null || true; wait "$xorg_pid" 2>/dev/null || true' EXIT
    trap 'exit 143' TERM INT
    for ((attempt=0; attempt<20; attempt++)); do
        kill -0 "$xorg_pid"
        if runuser -u gamer -- env DISPLAY=:55 XAUTHORITY="$auth" xdpyinfo >/dev/null 2>&1; then break; fi
        sleep 1
    done
    (( attempt < 20 )) || { echo 'Physical Xorg did not become ready.' >&2; exit 1; }
    bash /usr/local/bin/steam-headless-input.sh watch &
    input_pid=$!
    runuser -u gamer -- env DISPLAY=:55 XAUTHORITY="$auth" PHYSICAL=1 \
        XDG_RUNTIME_DIR="$runtime_dir" XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=GNOME \
        dbus-run-session -- bash /usr/local/bin/steam-headless-start.sh --session &
    session_pid=$!
    wait -n "$xorg_pid" "$session_pid" "$input_pid"
    exit
fi
exec runuser -u gamer -- env XDG_RUNTIME_DIR="$runtime_dir" XDG_SESSION_TYPE=x11 \
    XDG_CURRENT_DESKTOP=GNOME xvfb-run -a -s '-screen 0 1280x720x24 -nolisten tcp' \
    dbus-run-session -- bash /usr/local/bin/steam-headless-start.sh --session
