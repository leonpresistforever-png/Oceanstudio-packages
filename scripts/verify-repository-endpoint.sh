#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=/dev/null
source "$ROOT/ocean-packages/config.env"
EXPECTED=$(tr -d '[:space:]' < "$ROOT/ocean-packages/keys/ocean-development-repository.fingerprint")
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "$OCEAN_REPOSITORY_URL/dists/stable/InRelease" -o "$TMP/InRelease"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "$OCEAN_REPOSITORY_URL/dists/stable/main/binary-aarch64/Packages.gz" -o "$TMP/Packages.gz"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "$OCEAN_REPOSITORY_URL/ocean.gpg" -o "$TMP/ocean.gpg"

ACTUAL=$(gpg --batch --show-keys --with-colons "$TMP/ocean.gpg" 2>/dev/null | awk -F: '$1=="fpr"{print $10;exit}')
[[ -n "$ACTUAL" && "$ACTUAL" == "$EXPECTED" ]] || {
  echo "Ocean repository key mismatch: expected=$EXPECTED actual=${ACTUAL:-missing}" >&2
  exit 1
}
gpgv --keyring "$TMP/ocean.gpg" --output "$TMP/Release" "$TMP/InRelease" >/dev/null
python3 - "$ROOT" "$TMP" <<'PY'
import importlib.util, pathlib, sys
root, temporary = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location('hydrate', root / 'ocean-packages/scripts/hydrate-signed-bootstrap.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.verify_catalog_index((temporary / 'Release').read_text(), (temporary / 'Packages.gz').read_bytes())
PY
PACKAGE_COUNT=$(gzip -dc "$TMP/Packages.gz" | awk '/^Package: /{count++} END{print count+0}')
(( PACKAGE_COUNT > 0 )) || { echo 'Ocean repository index is empty.' >&2; exit 1; }
printf 'Ocean repository endpoint verified: fingerprint=%s packages=%s\n' "$ACTUAL" "$PACKAGE_COUNT"
