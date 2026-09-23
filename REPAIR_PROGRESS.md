# Ocean package repair checkpoint — 2026-09-23

This is an evidence ledger, not a claim that the package collection works.
Preserve `/data/data/studio.ocean.app/files/usr` and the separate
`/data/data/studio.ocean.app/files/glibc` runtime. Native Ocean, ocean-distro
guests and proot-distro guests must retain independent state.

## Verified repository state

- Current unsigned Packages: 6,482 entries / 6,482 unique names.
- Last complete pool/staging reconciliation: 7,444 pool paths, 5,448 staged paths.
  Two further upstream repair candidates were subsequently staged; they are not live.
- The current InRelease still authenticates the old 1,046-entry catalogue.
  It does not authenticate the current Packages.gz. Release.gpg also fails against
  the current Release. This explains successful-looking updates that retain old lists.
- Archive fingerprint: `09D45DD2CDC37BD4F9BC2C458EC15431CA5542E2`.
  The existing private signing key is unavailable to the publisher. Do not replace
  the trusted key or disable signature checks to manufacture a successful update.
- Five newer pool versions were omitted by the old staging-only publisher.
  The canonical publisher now selects from the complete pool and staging, preserves
  historical artifacts, and records same-version conflicts. Fifteen regression tests pass.
- The earlier bounded payload audit found 305 confirmed ready-message stubs in
  252 indexed packages. They remain in the current live index; they are not certified.
- Earlier confirmed active defects include the apt package's foreign repository
  source and foreign interpreter paths in guile and unzip. SSH metadata repacking
  does not establish official-source rebuilding: the compared ELF bytes were unchanged.

## Actual upstream builds and execution

Commit `cd7dad14747417be8d59d1c300ee1e94c16aa478` stages:

- pigz 2.8-1, official madler/pigz + madler/zlib commits, compiled with Android NDK r27.
  Actual ARM Android executable reports pigz 2.8 and passes two compression /
  decompression round trips under QEMU. This replaces the old 942-byte stub candidate.
- librsync 2.3.4-1, official librsync/librsync source, compiled with the Android NDK.
  Actual ARM static-library test passes signature, delta and patch round trip.
  The shared library is compiled but not tested on an Android device.

Build run: https://github.com/leonpresistforever-png/Oceanstudio-packages/actions/runs/35884505366
Source hashes and test details are in `staging/upstream-repairs/provenance.json`.
The initial static builds aborted because ARM64 Bionic requires 64-byte TLS
alignment. An assembly alignment input now fixes this while linking, before tests.
Neither package is published through APT until the complete signed publication passes.

## Distro failures reproduced from actual indexed archives

- `ocean-distro_1.0.0_all.deb` SHA256
  `c57427c64c3b27d6f6a82e657e5d06aa2325325f66162a3f08e30afc85f5b71d`
  still contains Termux-hosted rootfs URLs, despite different app source files.
- Its awk JSON parser matches the inner `"arch"` metadata field when asked for the
  top-level `arch` distribution. Consequently `install arch` reads Debian's URL.
  Distro names are also case-sensitive. These match the phone screenshots.
- `proot-distro_4.18.0_all.deb` SHA256
  `8e6cca74e9576cf02951b13b10fc8bac1f67cf0ace7ea1f4c90eff520ffa47b4`
  is still the attributed Termux implementation. Its command checks require awk
  and other tools absent from its declared dependency list. It has not been replaced
  with an independently implemented and feature-verified Ocean manager.
- OpenJDK's reported partial install remains under investigation. Do not conflate a
  valid downloaded archive with successful dependency resolution and installation.

## Ongoing complete forensic pass

`scripts/forensic_repository.py` hashes and reads every byte of every unique pool
and staged archive, including maintainer scripts, full binary contents, symlink
targets and runtime URLs. It records overlapping file ownership to investigate
dpkg overwrite / partial installation failures. Exact duplicate archives are
scanned once with every referring path recorded. No payload is executed.

File inventories and findings are committed by the forensic workflow under
`audits/forensic/<source-commit>/`. Review the report's explicit limitations:
static checks do not prove upstream provenance or Android execution, and nested
compressed payloads are not recursively expanded. Guile VM bytecode and Go
cross-target object files are classified separately from native executables.

## APK status

Ocean native paths were preserved. Signed-catalogue validation, known-cache
migration, native pkg diagnostics/update checks and a source production build
workflow are committed in Oceanstudio.apk. Unknown user catalogues and dpkg state
are preserved. Concurrent UI work was retained.

No new production APK has been built or released by this repair. Private Actions
jobs currently fail before any steps execute. The production gate also rejects
the mixed old signature/new bundled catalogue and unresolved payload defects.
The reserved version 1.2.2 is not evidence of a release. Existing signing material
and functional package repairs are still required. Never publish a debug-key,
repacked-old-DEX or authentication-bypass APK as a production repair.
