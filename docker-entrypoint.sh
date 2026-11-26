#!/bin/sh
set -eu

# Render mounts persistent disks at runtime, replacing the image directory
# ownership. Repair ownership before dropping privileges to the app user.
mkdir -p /var/data
chown -R 10001:10001 /var/data

exec gosu appuser "$@"
