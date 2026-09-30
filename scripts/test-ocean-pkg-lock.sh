#!/usr/bin/env bash
set -euo pipefail
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
PREFIX="$ROOT/prefix"
BIN="$ROOT/bin"
LOG="$ROOT/apt.log"
mkdir -p "$PREFIX/var/run" "$BIN"

cat > "$BIN/apt-get" <<SH
#!$(command -v bash || echo /usr/bin/env bash)
printf '%s start %s\n' "\$\$" "\$*" >> "\$OCEAN_TEST_LOG"
mkdir -p "\$PREFIX/var/lib/apt/lists"
printf 'Package: ocean-hello\n' > "\$PREFIX/var/lib/apt/lists/ocean_Packages"
sleep "\${OCEAN_TEST_SLEEP:-0}"
printf '%s end %s\n' "\$\$" "\$*" >> "\$OCEAN_TEST_LOG"
SH
chmod +x "$BIN/apt-get"
for tool in apt-cache dpkg-query; do ln -s apt-get "$BIN/$tool"; done

if [[ -f "$PWD/packages/ocean-pkg/pkg" ]]; then
  PKG="$PWD/packages/ocean-pkg/pkg"
else
  PKG="$PWD/ocean-packages/packages/ocean-pkg/pkg"
fi
export PREFIX PATH="$BIN:$PATH" OCEAN_TEST_LOG="$LOG" OCEAN_PKG_LOCK_WAIT=5
OCEAN_TEST_SLEEP=1 bash "$PKG" update & first=$!
sleep .2
OCEAN_TEST_SLEEP=0 bash "$PKG" install ocean-hello & second=$!
wait "$first" "$second"
test "$(grep -c ' start ' "$LOG")" = 2
grep -q 'end update' "$LOG"
test "$(sed -n '2p' "$LOG")" = "$(grep 'end update' "$LOG")"

# A dead/non-numeric owner is recovered rather than becoming a permanent busy result.
mkdir -p "$PREFIX/var/run/ocean-pkg.lock.d"
printf 'not-a-pid\n' > "$PREFIX/var/run/ocean-pkg.lock.d/pid"
OCEAN_TEST_SLEEP=0 bash "$PKG" search ocean
test ! -e "$PREFIX/var/run/ocean-pkg.lock.d"

# A PID whose start time does not match is stale even if that PID is alive.
mkdir -p "$PREFIX/var/run/ocean-pkg.lock.d"
printf '%s\n' "$$" > "$PREFIX/var/run/ocean-pkg.lock.d/pid"
printf '1\n' > "$PREFIX/var/run/ocean-pkg.lock.d/start"
printf 'old-owner\n' > "$PREFIX/var/run/ocean-pkg.lock.d/token"
OCEAN_TEST_SLEEP=0 bash "$PKG" search ocean
test ! -e "$PREFIX/var/run/ocean-pkg.lock.d"

# A live owner cannot be stolen and a timed-out contender must leave the
# owner's token untouched.
mkdir -p "$PREFIX/var/run/ocean-pkg.lock.d"
printf '%s\n' "$$" > "$PREFIX/var/run/ocean-pkg.lock.d/pid"
stat=$(cat "/proc/$$/stat"); rest=${stat##*) }; set -- $rest
printf '%s\n' "${20}" > "$PREFIX/var/run/ocean-pkg.lock.d/start"
printf 'live-owner\n' > "$PREFIX/var/run/ocean-pkg.lock.d/token"
if OCEAN_PKG_LOCK_WAIT=0 bash "$PKG" update; then
  echo 'contender stole a live package lock' >&2; exit 1
else
  test "$?" = 75
fi
test "$(cat "$PREFIX/var/run/ocean-pkg.lock.d/token")" = live-owner
rm -rf "$PREFIX/var/run/ocean-pkg.lock.d"
echo 'Ocean pkg atomic lock tests passed.'
