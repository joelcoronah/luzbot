#!/bin/sh
# Heartbeat client for any always-on Linux box (Raspberry Pi, home server...).
#
# Usage (cron, every minute):
#   * * * * * LUZBOT_URL=https://203-0-113-10.sslip.io LUZBOT_TOKEN=... /path/to/heartbeat.sh
#
# The token is passed to curl through stdin, not as an argument, so other
# users on the machine cannot read it from the process list.
set -eu

: "${LUZBOT_URL:?set LUZBOT_URL, e.g. https://203-0-113-10.sslip.io}"
: "${LUZBOT_TOKEN:?set LUZBOT_TOKEN}"

printf 'Authorization: Bearer %s\n' "$LUZBOT_TOKEN" |
	curl --fail --silent --show-error --max-time 10 --retry 2 \
		--header @- --request POST "${LUZBOT_URL%/}/heartbeat" >/dev/null
