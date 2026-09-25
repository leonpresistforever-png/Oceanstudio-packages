# Ocean repair checkpoint — 2026-09-25

This is a record of verified work and remaining defects, not a claim that all packages work.
Native Ocean remains at `/data/data/studio.ocean.app/files/usr`; the isolated glibc
runtime remains at `/data/data/studio.ocean.app/files/glibc`.

## Current verified state

Package snapshot: `45bd61a0d25f7676f1dbef2c8fcac9065b3e446d`.
The later distro build added repair candidates; it did not publish them.

- Live APT: **6,483 entries / 6,483 unique names** (previously 6,482).
- Actual GPG verification passed for both InRelease and Release.gpg with archive key
  `DE6CC7B9B2CF51DA5434663F5FBBA12482C45CC3`. InRelease's payload equals Release;
  every advertised size/hash and decompression of Packages.gz matched Packages.
- A real isolated host APT client, configured for Ocean's aarch64 repository,
  downloaded InRelease **and the 843 kB Packages index**, persisted it, found all
  seven ocean-glibc package names, and resolved the glibc suite's eight-package
  transaction. This verifies repository/client metadata, not Android execution.
- Full forensic run **36031758771** read **14,176 archive paths / 8,720 distinct
  archive byte streams**. Zero invalid/truncated archives and zero unresolved
  dependency references were found.
- Live defects remain: **252 packages with 305 ready-message stubs**, **38 packages
  with foreign-prefix findings**, and **62 overlapping live paths**. Some prefix
  strings are build paths; none establish clean upstream provenance.
- The 1,268 shared-runtime repair archives (1,250 command packages plus 18 new
  runtimes) are staged, not live. No ocean-runtime-* package is in the current index.
- The official pigz 2.8-1 replacement is staged. Live pigz still references the old
  942-byte archive.
- The newer unindexed pool GDB 16.3-4 contains a foreign app prefix. It must not
  supersede the official-source GDB candidate solely because its version is higher.

Full evidence:
[forensic snapshot](audits/forensic/45bd61a0d25f7676f1dbef2c8fcac9065b3e446d/).

## Gemini CLI changes reviewed

The CLI published a coherent signed catalogue and selected critical replacements
for Caddy, strace, GDB, librsync, LuaJIT, OpenJDK's ownership split, and the distro
commands. The signing improvement is verified from the actual metadata bytes.

OpenJDK's 365 overlapping JDK/JRE paths were removed from the JDK archive.
The JRE is unchanged, still has foreign-prefix findings, and its maintainer scripts
and Android JVM execution have not been validated by the unpack-only replay.
This is not a complete official-source JDK/JRE replacement.

The CLI's proot-distro package invoked ocean-distro directly, sharing its guest
state. Its APK job repacked an existing APK, retained all eight DEX files and the
manifest, and generated a different signing certificate. It did not compile the
new Java/native source fixes.

## Repairs made after that review

- **45bd61a**: replace the unsafe APK repack workflow with a request to the private
  source production builder; no new signing identity or PAT workflow input.
- **b5855fe**: independently implemented PRoot command and registry; own state at
  `$PREFIX/var/lib/proot-distro/installed-rootfs` and own download cache.
  It does not invoke or depend on the ocean-distro command.
- Ocean remains in `${OCEAN_HOME}/.distro`. Thirteen PRoot command tests cover
  install/login, removal, cache separation, failed reset preservation, rename,
  backup/restore and rejection of overlapping or symlinked state directories.
- A versioned ownership transfer moves the old Ocean tools manager executable into
  ocean-distro while preserving all 25 unrelated Ocean script byte streams.
- CI **36033997429** built the three distro/tool repair candidates, passed the
  command tests and actual host dpkg ownership/upgrade/removal test.
  The ownership test uses --force-depends and does not certify the dependency
  runtime on Android. Candidates are in [staging](staging/ocean-distro-repair/).
- The repacked APK release was marked as a prerelease and its unsupported clean /
  complete claims were replaced with the byte-level findings.

The subsequent publisher run **36034195488** failed to push because main advanced.
It also still selected the older hardcoded distro versions. The new distro/tool
candidates are **not yet live**.

## Distro rootfs status

Run **36033997422** tested all 13 registry entries. Six passed checksum, OS identity
and actual ARM shell execution under QEMU: Ubuntu, Alpine, Arch, openSUSE, Void,
Gentoo. Debian and Rocky were not usable flat rootfs archives; Fedora returned 404.
Alma, Kali, CentOS and Devuan still require official verified sources. A pinned
checksum alone does not make a distribution installable.

Evidence: [rootfs report](audits/rootfs/b5855fead43f47ed6484670ed2bebba5b62b7ee5/report.json).

## Work still required

1. Reconcile every eligible staged/pool candidate through one publication path;
   retain explicit evidence for rejected foreign/placeholder candidates.
2. Publish the tested shared-runtime, pigz and independent distro repairs; repeat
   checksum, dependency and ownership verification on the resulting live index.
3. Rebuild the remaining foreign-origin and stub packages from upstream source.
   Removing strings or rebadging existing binaries does not satisfy this.
4. Repair remaining official rootfs sources and verify their actual guest shells.
5. Finish app key migration even when an APT index already exists; preserve
   user-selected repositories, unknown keys and installed package state.
6. Compile current app sources, refresh/verify the bootstrap, use the established
   APK signing identity, and smoke-test before a new production release.

No repaired production APK has been built by this work. The file labelled 1.2.2
is a catalogue repack of 1.2.1, not that deliverable. Earlier source and audit work,
including real ARM glibc/pigz/librsync checks and the 1,268-package shared ownership
migration, remains in Git history and the existing audit/staging receipts.
