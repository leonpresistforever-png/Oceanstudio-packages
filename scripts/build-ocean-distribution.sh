#!/usr/bin/env bash
set -euo pipefail
cat >&2 <<'MSG'
The legacy distribution builder is retired: it used the Termux build framework
and could import binary caches without official-source provenance.
Use ocean-packages/scripts/build-source-packages.py for pinned upstream builds.
That builder creates quarantined candidates, not a complete signed distribution.
Promotion requires dependency validation, Android execution tests and the repository signing key.
MSG
exit 78
