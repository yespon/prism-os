#!/bin/bash
set -e
if [ "${1:-}" = "build" ]; then
  exec env UV_DEFAULT_INDEX=https://pypi.org/simple UV_INDEX_URL=https://pypi.org/simple /root/.local/bin/uv "$@"
fi
exec /root/.local/bin/uv "$@"
