#!/usr/bin/env bash
# Experimental GDM mode; never start an unlocked fallback session.
set -euo pipefail
[[ $EUID == 0 && $$ == 1 && -e /.dockerenv ]] || {
    echo 'GDM mode requires the container entrypoint as PID 1 (no Docker init).' >&2
    exit 1
}
[[ ${PHYSICAL:-0} == 1 && -c /dev/dri/card0 ]] || {
    echo 'GDM mode requires the physical display configuration.' >&2
    exit 1
}
# This must be the container's own cgroup2 mount, not a bind of the host hierarchy.
[[ $(findmnt -n -o FSTYPE /sys/fs/cgroup) == cgroup2 && $(< /proc/1/cgroup) == '0::/' ]]
secret=/run/secrets/desktop-password-hash
[[ -f $secret && ! -L $secret && $(stat -c '%u:%a' "$secret") == 0:400 ]] || {
    echo 'Mount the desktop password hash as a root-owned 0400 secret.' >&2
    exit 1
}
IFS= read -r hash < "$secret"
[[ $hash =~ ^\$(y|6)\$[./a-zA-Z0-9$=,]+$ ]] || { echo 'Invalid desktop password hash.' >&2; exit 1; }
printf 'gamer:%s\n' "$hash" | chpasswd --encrypted
unset hash
runuser -u gamer -- test -w /home/default
render_gid=$(stat -c %g /dev/dri/renderD128)
if ! getent group "$render_gid" >/dev/null; then groupadd --gid "$render_gid" steam-render; fi
render_group=$(getent group "$render_gid" | cut -d: -f1)
usermod -aG "$render_group" gamer
[[ -c /dev/uinput ]] || mknod -m 0660 /dev/uinput c 10 223
chgrp gamer /dev/uinput
bash /usr/local/bin/steam-headless-input.sh init
install -m 0644 /etc/X11/steam-headless.conf /etc/X11/xorg.conf
mount -o remount,rw /sys/fs/cgroup
exec /lib/systemd/systemd --unit=graphical.target
