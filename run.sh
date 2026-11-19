#!/usr/bin/env bash
# Compatibility shim: older systemd units start <repo>/run.sh. The real script is scripts/run.sh.
# Re-running ./scripts/setup-server.sh points the service at scripts/run.sh directly.
exec "$(dirname "$0")/scripts/run.sh" "$@"
