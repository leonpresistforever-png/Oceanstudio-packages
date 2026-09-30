#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd); TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
make_deb() {
  local name=$1 depends=${2:-} dir="$TMP/$1"
  mkdir -p "$dir/DEBIAN" "$dir/data/data/studio.ocean.app/files/usr/share/$name"
  chmod -R 755 "$TMP"
  cat > "$dir/DEBIAN/control" <<EOF
Package: $name
Version: 1.0
Architecture: all
Maintainer: OceanStudio
Depends: $depends
Description: dependency closure fixture
EOF
  dpkg-deb --root-owner-group --build "$dir" "$TMP/${name}_1.0_all.deb" >/dev/null
}
make_deb libc ''; make_deb bash 'libc'; make_deb apt 'libc'; make_deb expansion 'libc'
mapfile -t closure < <(python3 "$ROOT/ocean-packages/scripts/bootstrap-closure.py" "$TMP" --seed bash --seed apt)
printf '%s\n' "${closure[@]}" | grep -q 'bash_1.0_all.deb'
printf '%s\n' "${closure[@]}" | grep -q 'apt_1.0_all.deb'
printf '%s\n' "${closure[@]}" | grep -q 'libc_1.0_all.deb'
if printf '%s\n' "${closure[@]}" | grep -q 'expansion_1.0_all.deb'; then
  echo 'repository-only expansion leaked into bootstrap closure' >&2; exit 1
fi
echo 'Minimal bootstrap dependency closure tests passed.'
