# Expansion to ~7.5k indexed packages

This shard tracks **new package names** that are not yet in the live APT index.
Each name must be built from official upstream source for the Ocean prefix before
publication. Duplicates and Termux-derived binaries are rejected by CI.

Run `python3 scripts/plan-expansion-packages.py` to refresh `target-packages.json`
against the current `Packages.gz` index.

Priority batch 1 (user-facing bugs): `alsa-utils` (`aplay`), `libnotify-bin`,
`x11-apps` (`xeyes`), `espeak-ng`, `ffprobe` as explicit package.
