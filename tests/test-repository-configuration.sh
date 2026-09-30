#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=/dev/null
source "$ROOT/ocean-packages/config.env"
[[ "$OCEAN_REPOSITORY_URL" == https://raw.githubusercontent.com/leonpresistforever-png/Oceanstudio-packages/main/apt ]]
EXPECTED=$(tr -d '[:space:]' < "$ROOT/ocean-packages/keys/ocean-development-repository.fingerprint")
ACTUAL=$(gpg --batch --show-keys --with-colons "$ROOT/ocean-packages/keys/ocean-development-repository.asc" 2>/dev/null | awk -F: '$1=="fpr"{print $10;exit}')
[[ "$EXPECTED" == "$ACTUAL" ]]
grep -Fq 'ocean.list' "$ROOT/ocean-packages/scripts/hydrate-signed-bootstrap.py"
if grep -Fq 'ocean.list.disabled' "$ROOT/ocean-packages/scripts/hydrate-signed-bootstrap.py"; then
  echo 'Online Ocean repository is still disabled in generated bootstraps.' >&2
  exit 1
fi
echo 'Ocean repository configuration tests passed.'
