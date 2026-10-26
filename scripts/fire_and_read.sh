#!/usr/bin/env bash
# Fire one trigger by hand, then read back what the run left behind.
#
#   ./scripts/fire_and_read.sh daily-digest
#
# Why by hand: a trigger you have only seen on the clock teaches you nothing
# until 09:00 tomorrow. Firing it the hour you write it shows you the machine
# boot, the first tool call and the first wrong assumption while the row is
# still open in your editor.
set -euo pipefail

slug="${1:?usage: fire_and_read.sh <trigger-slug>}"

command -v kortix >/dev/null 2>&1 || {
  echo "kortix CLI not on PATH. Install it from https://kortix.com/docs" >&2
  exit 1
}

echo "→ triggers before"
kortix triggers ls

echo
echo "→ firing $slug"
kortix triggers fire "$slug"

echo
echo "→ waiting for the run to settle (5-minute idle timeout is the ceiling)"
sleep 20
kortix triggers ls

echo
echo "→ opening the change request the run produced"
echo "  (kortix cr prints the change requests toward main; read the diff,"
echo "   the files it touched, and whether the branch holds anything the"
echo "   prompt did not ask for)"
kortix cr
