#!/usr/bin/env bash
# Run a command against the filtered host BlueZ bus when it is mounted.
# Without the socket the command runs unchanged against the container system bus.
set -euo pipefail
bus=/run/steam-headless-bluez/bus
if [[ -S $bus ]]; then
    export DBUS_SYSTEM_BUS_ADDRESS=unix:path=$bus
fi
exec "$@"
