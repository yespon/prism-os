#!/bin/sh
set -eu
mkdir -p /run/sshd /run/ssh-keys
chmod 755 /run/sshd
chmod 700 /run/ssh-keys
ssh-keygen -q -t ed25519 -N '' -f /run/ssh-keys/host
install -m 644 /run/fixture-public-key.pub /run/authorized_keys
exec /usr/sbin/sshd -D -e -f /etc/ssh/prismos-test.conf
