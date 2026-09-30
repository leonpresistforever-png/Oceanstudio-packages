#!/usr/bin/env bash
set -euo pipefail
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
export OCEAN_PKG_TMPDIR="$ROOT/tmp"
mkdir -p "$OCEAN_PKG_TMPDIR"
printf 'wrong archive' > "$ROOT/wrong.tar"
printf 'verified archive' > "$ROOT/right.tar"
SHA=$(sha256sum "$ROOT/right.tar" | cut -d' ' -f1)

bash "$(dirname "$0")/ocean-download.sh" \
  "file://$ROOT/wrong.tar|file://$ROOT/right.tar" "$ROOT/result.tar" "$SHA"
test "$(sha256sum "$ROOT/result.tar" | cut -d' ' -f1)" = "$SHA"
# The second retrieval must reuse the checksum-verified destination without
# contacting either now-missing origin candidate.
rm "$ROOT/wrong.tar" "$ROOT/right.tar"
bash "$(dirname "$0")/ocean-download.sh" \
  "file://$ROOT/wrong.tar|file://$ROOT/right.tar" "$ROOT/result.tar" "$SHA"
test "$(sha256sum "$ROOT/result.tar" | cut -d' ' -f1)" = "$SHA"

# Missing/unchecked digests are rejected before contacting any mirror.
if bash "$(dirname "$0")/ocean-download.sh" https://example.invalid/source "$ROOT/nope" SKIP_CHECKSUM; then
    echo 'Unchecked source unexpectedly accepted' >&2; exit 1
fi
# Simulate a resumed HTTP success with corrupt bytes, then a clean good response.
# The real shell helper and checksum/move logic run; only transport is replaced.
export OCEAN_TEST_STATE="$ROOT/curl-attempts"
export OCEAN_TEST_GOOD="$ROOT/result.tar"
curl() {
    local output=''
    while (($#)); do
        if [[ "$1" == --output ]]; then output="$2"; shift; fi
        shift
    done
    if [[ ! -f "$OCEAN_TEST_STATE" ]]; then
        printf corrupt > "$output"
        printf first > "$OCEAN_TEST_STATE"
    else
        test ! -e "$output" || return 88
        cp "$OCEAN_TEST_GOOD" "$output"
    fi
}
export -f curl
bash "$(dirname "$0")/ocean-download.sh" https://upstream.invalid/source "$ROOT/retried.tar" "$SHA"
test "$(sha256sum "$ROOT/retried.tar" | cut -d' ' -f1)" = "$SHA"
echo "Ocean source fallback, verified cache, strict digests and clean corrupt-resume retry: PASS"
