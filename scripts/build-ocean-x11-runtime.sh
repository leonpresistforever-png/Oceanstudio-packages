#!/usr/bin/env bash
set -euo pipefail
ROOTFS="${1:?rootfs directory required}"
OUT="${2:-staging/ocean-device-suite}"
PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

test -x "$ROOTFS/usr/bin/Xvfb"
test -x "$ROOTFS/usr/bin/x11vnc"
test -x "$ROOTFS/usr/bin/openbox"
test -x "$ROOTFS/usr/bin/xterm"
test -e "$ROOTFS/lib/ld-linux-aarch64.so.1" -o -e "$ROOTFS/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PKG="$WORK/pkg"
DEST="$PKG${PREFIX}/var/lib/ocean-x11/rootfs"
mkdir -p "$PKG/DEBIAN" "$PKG${PREFIX}/bin" "$DEST"
cp -a "$ROOTFS/." "$DEST/"

cat > "$PKG/DEBIAN/control" <<EOF
Package: ocean-x11-runtime
Version: ${VERSION}
Architecture: aarch64
Maintainer: OceanStudio <packages@ocean.studio>
Section: x11
Priority: optional
Depends: ocean-api (= 1.0.0-1), proot
Description: OceanStudio independent X11 display backend
 AArch64 Xvfb, x11vnc, Openbox, xterm and Mesa software-rendering runtime
 assembled from official Debian packages. Runs inside OceanStudio with PRoot
 and feeds the native Ocean X11 renderer over localhost RFB.
EOF

cat > "$PKG${PREFIX}/bin/ocean-x11-runtime" <<'EOF'
#!/system/bin/sh
if [ -z "$PREFIX" ]; then PREFIX="/data/data/studio.ocean.app/files/usr"; fi
exec "$PREFIX/bin/python" "$PREFIX/lib/ocean-device/ocean_device.py" ocean-x11-runtime "$@"
EOF
chmod 755 "$PKG${PREFIX}/bin/ocean-x11-runtime"

rm -f "$OUT/pool/main/ocean-x11-runtime_${VERSION}_all.deb" "$OUT/pool/main/ocean-x11-runtime_${VERSION}_aarch64.deb"
dpkg-deb -Zxz -z9 --root-owner-group --build "$PKG" "$OUT/pool/main/ocean-x11-runtime_${VERSION}_aarch64.deb" >/dev/null

SIZE="$(stat -c%s "$OUT/pool/main/ocean-x11-runtime_${VERSION}_aarch64.deb")"
if [ "$SIZE" -ge 99000000 ]; then
  echo "X11 runtime package is too large for ordinary GitHub storage: $SIZE" >&2
  exit 1
fi

dpkg-scanpackages "$OUT/pool/main" /dev/null > "$OUT/Packages.repaired"
python3 - "$OUT" "$SIZE" <<'PY'
import hashlib,json,sys
from pathlib import Path
out=Path(sys.argv[1]);size=int(sys.argv[2])
p=out/"provenance.json";d=json.loads(p.read_text())
artifact=out/"pool/main/ocean-x11-runtime_1.0.0-1_aarch64.deb"
row=next(x for x in d["packages"] if x["package"]=="ocean-x11-runtime")
row.update({
  "artifact":artifact.name,
  "bytes":size,
  "sha256":hashlib.sha256(artifact.read_bytes()).hexdigest(),
  "depends":"ocean-api (= 1.0.0-1), proot",
  "backend":"Xvfb+x11vnc+Openbox+xterm+Mesa llvmpipe",
  "backendSource":"official Debian arm64 packages",
})
d["x11Runtime"]={
  "architecture":"aarch64",
  "transport":"localhost RFB",
  "display":":1",
  "rfbPort":5901,
  "rootfs":"/data/data/studio.ocean.app/files/usr/var/lib/ocean-x11/rootfs",
  "sourcePolicy":"official Debian packages; no Termux:X11 application or Termux binary source",
}
p.write_text(json.dumps(d,indent=2)+"\n")
PY

echo "Built Ocean X11 runtime: $SIZE bytes"
