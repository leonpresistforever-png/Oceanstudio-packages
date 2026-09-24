# Ocean package repair checkpoint — 2026-09-24

This is an evidence ledger, not a claim that the package collection works.
Preserve `/data/data/studio.ocean.app/files/usr` and the separate
`/data/data/studio.ocean.app/files/glibc` runtime. Native Ocean, ocean-distro
guests and proot-distro guests must retain independent state.

## Verified repository state

- Current unsigned Packages: 6,482 entries / 6,482 unique names.
- Complete forensic snapshot: 7,444 pool paths and 5,450 staged paths,
  representing 7,445 distinct archive byte streams. All 6,482 live records were covered.
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
- OpenJDK and its required headless JRE own 365 identical files with no Replaces
  declaration. Real dpkg rejects the same ownership pattern even with identical
  bytes. The JDK/JRE also contain foreign-prefix references in ELF files; proper
  upstream rebuilding and a non-overlapping split remain necessary. A good archive
  checksum is not a successful installation.

## Completed static forensic pass

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

The complete evidence is in
`audits/forensic/9dbec922bac216cb2f13fa84d398f3ecb5ad08b8/`, committed as
`91af6c6ad85b9c6acc22d97bdd05bcd40ac515c8` (Actions run 35885286777).
All archives decoded; zero invalid/truncated repository archives were found.
There were 427 overlapping live paths, 107 foreign-prefix findings in files of
39 live packages (88 ELF files, 5 scripts, 14 other files), and the previously
reported 305 ready-message stub files. Some ELF strings can be build paths;
they require review and do not alone prove a runtime failure or clean provenance.

## Shared-file ownership repair

18 shared Python files were owned by 1,250 separate command packages. Each source
file was matched by SHA256 against the committed original Ocean source, and each
old package's complete file layout was verified before constructing a repair.

`build-shared-runtime-repairs.py` now rebuilds all 1,250 existing command packages
plus 18 distinct shared runtime packages. Existing command names, source bytes,
architectures and the native prefix are preserved. Versioned Replaces/Breaks and
exact dependencies provide an explicit ownership migration. No foreign binary is
copied into these source builds and no original package is deleted.

Local verification passed:
- 6 real dpkg/APT regression tests, including old overlap reproduction, upgrade,
  fresh install, removal survival, source hash enforcement and reproducible bytes.
- All 1,268 built archives scanned; no duplicate file ownership among candidates.
- All 1,268 co-installed and configured together in a temporary host dpkg root
  using a host-only Python fixture and foreign-architecture support.
- Removing one command from each group preserved every shared source file.
- Actual installed GCD and subnet commands returned expected results.
- Workbench's 300 help paths and 15 functional-domain checks passed.

These establish packaging behavior. They do not certify all command semantics or
Android execution. CI stages the tested artifacts; live APT remains unchanged
until existing-key signing succeeds. The 18 shared collisions are repaired by the
candidate overlay; 409 other overlapping live paths remain for investigation.

## Distro installer/source verification

Ocean-distro source now uses real JSON selection, case-normalized names,
checksum-addressed downloads, clean restart after a corrupt partial, temporary
extraction and separate Ocean/proot-distro guest state. Seven installer tests and
three guest symlink-resolution tests pass. These source fixes are not yet a newly
published distro package or APK.

Ubuntu 24.04.5 and Void official downloads passed checksum, OS identity and actual
ARM shell execution under QEMU. Gentoo's failed extraction is specifically from
archived dev/null and dev/console requiring mknod; the installer now skips guest
/dev contents because login binds the native /dev. Alpine's auditor needed both
guest-aware absolute symlink resolution and BusyBox's original shell argv[0].
Remaining distro source problems (including Debian, Arch and container archives)
are recorded honestly in `audits/rootfs/`; a workflow's success only means its
evidence was saved, not that every distro passed.

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
