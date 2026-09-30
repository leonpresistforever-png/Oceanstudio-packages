#!/usr/bin/env python3
"""Hydrate Ocean's minimal runtime from its signed APT repository.

This is a local-build fallback for environments without the package compiler
cache. It never invents packages: repository metadata is signature checked,
every downloaded .deb is SHA-256 checked, and the complete dependency closure
is installed into an Android-prefix staging tree.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import urllib.parse
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ROOT = Path(__file__).resolve().parents[2]
PREFIX = Path("data/data/studio.ocean.app/files/usr")
DEFAULT_SEEDS = ("bash", "apt", "libcurl", "curl", "ocean-pkg", "ocean-hello")


def paragraphs(text: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for block in text.strip().split("\n\n"):
        item: dict[str, str] = {}
        key = ""
        for line in block.splitlines():
            if line[:1].isspace() and key:
                item[key] += "\n" + line
            elif ": " in line:
                key, value = line.split(": ", 1)
                item[key] = value
        if item:
            result.append(item)
    return result


DEPENDENCY = re.compile(r"^([A-Za-z0-9][A-Za-z0-9+.-]*)(?::([a-z0-9-]+))?(?:\s*\((<<|<=|=|>=|>>)\s*([^()]+)\))?$")


def dependency_groups(value):
    groups = []
    for group in value.replace("\n", " ").split(","):
        if not group.strip():
            continue
        alternatives = []
        for choice in group.split("|"):
            match = DEPENDENCY.fullmatch(choice.strip())
            if not match:
                raise RuntimeError("Malformed binary dependency: " + choice)
            alternatives.append(match.groups())
        groups.append(alternatives)
    return groups


def version_matches(version, operator, required):
    if operator is None:
        return True
    if version is None:
        return False
    status = subprocess.run(["dpkg", "--compare-versions", version, operator, required]).returncode
    if status not in (0, 1):
        raise RuntimeError("Invalid dependency version comparison")
    return status == 0


def resolve(entries: list[dict[str, str]], seeds: tuple[str, ...]) -> list[dict[str, str]]:
    # This hydrates a fixed signed candidate set. Native APT remains responsible
    # for device-side solving, installs and upgrades; incompatible snapshots fail.
    by_name = {}
    for entry in entries:
        name = entry.get("Package", "")
        if not name or entry.get("Architecture", "all") not in ("aarch64", "all"):
            continue
        previous = by_name.get(name)
        if previous is None or version_matches(entry.get("Version"), ">>", previous.get("Version", "0")):
            by_name[name] = entry
    providers = {}
    for entry in by_name.values():
        for group in dependency_groups(entry.get("Provides", "")):
            for name, arch, operator, version in group:
                if operator not in (None, "="):
                    raise RuntimeError("Provides must use an exact version")
                providers.setdefault(name, []).append((entry, version))

    def choose(alternatives):
        for name, arch, operator, required in alternatives:
            candidates = ([(by_name[name], by_name[name].get("Version"))] if name in by_name else [])
            candidates += providers.get(name, [])
            for entry, version in candidates:
                if arch not in (None, "any", "native", "aarch64", "all"):
                    continue
                if version_matches(version, operator, required):
                    return entry
        return None

    pending = []
    for seed in seeds:
        chosen = choose([(seed, None, None, None)])
        if chosen is None:
            raise RuntimeError("repository cannot satisfy dependency: " + seed)
        pending.append(chosen)
    selected = {}
    while pending:
        entry = pending.pop(0)
        name = entry["Package"]
        if name in selected:
            continue
        selected[name] = entry
        for field in ("Pre-Depends", "Depends"):
            for alternatives in dependency_groups(entry.get(field, "")):
                chosen = choose(alternatives)
                if chosen is None:
                    raise RuntimeError(f"{name} has unresolved dependency: {alternatives!r}")
                pending.append(chosen)
    return [selected[name] for name in sorted(selected)]


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "OceanStudio-bootstrap-builder/1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(x) for x in args], check=True, text=True, **kwargs)


def compress_zstd(source: Path, destination: Path) -> None:
    """Compress reproducibly with the CLI, or python-zstandard on lean hosts."""
    if shutil.which("zstd"):
        run("zstd", "-19", "-T0", "-f", source, "-o", destination)
        return
    try:
        import zstandard
    except ImportError as error:
        raise RuntimeError("zstd or the Python zstandard module is required") from error
    compressor = zstandard.ZstdCompressor(level=19, threads=-1)
    with source.open("rb") as input_file, destination.open("wb") as output_file:
        compressor.copy_stream(input_file, output_file)


def verify_catalog_index(release: str, compressed: bytes) -> bytes:
    """Bind Packages.gz to the authenticated InRelease, not merely to HTTPS."""
    in_sha256 = False
    checksums = {}
    for line in release.splitlines():
        if line == "SHA256:":
            in_sha256 = True
            continue
        if in_sha256 and line and not line[0].isspace():
            break
        fields = line.split()
        if in_sha256 and len(fields) == 3:
            if fields[2] in checksums:
                raise RuntimeError("Duplicate signed repository checksum path")
            checksums[fields[2]] = (fields[0], int(fields[1]))
    name = "main/binary-aarch64/Packages"
    if checksums.get(name + ".gz") != (hashlib.sha256(compressed).hexdigest(), len(compressed)):
        raise RuntimeError("Packages.gz does not match the signed repository index")
    packages = gzip.decompress(compressed)
    if checksums.get(name) != (hashlib.sha256(packages).hexdigest(), len(packages)):
        raise RuntimeError("Packages does not match the signed repository index")
    return packages


def write_catalog(output: Path, repository: str, inrelease: Path, compressed: Path,
                  key: Path, packages: bytes) -> str:
    parsed = urllib.parse.urlsplit(repository)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
        raise RuntimeError("Ocean package repository must be a plain HTTPS URL")
    prefix = (parsed.netloc + parsed.path.rstrip("/")).replace("_", "%5f").replace("/", "_") + "_dists_stable_"
    output.mkdir(parents=True, exist_ok=True)
    values = {"format": "1", "repository_url": repository, "list_prefix": prefix,
              "package_count": str(len(paragraphs(packages.decode()))),
              "packages_length": str(len(packages)),
              "packages_sha256": hashlib.sha256(packages).hexdigest()}
    # Android asset packaging strips .gz suffixes; retain gzip bytes under .bin.
    for name, source in (("InRelease", inrelease), ("Packages.gz.bin", compressed), ("ocean.gpg", key)):
        data = source.read_bytes()
        (output / name).write_bytes(data)
        values[name + "_sha256"] = hashlib.sha256(data).hexdigest()
    (output / "catalog.properties").write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    return prefix


def package_file_list(deb: Path) -> str:
    """Write dpkg's machine format directly from tar member names.

    dpkg treats '/' as an empty filename; the archive root must be '/.'.
    Human-readable dpkg-deb -c output also appends symlink destinations.
    """
    process = subprocess.Popen(["dpkg-deb", "--fsys-tarfile", str(deb)], stdout=subprocess.PIPE)
    paths = []
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or any(c in member.name for c in "\n\r\0"):
                    raise RuntimeError(f"Invalid package file-list path: {member.name!r}")
                paths.append("/." if str(path) == "." else "/" + str(path))
        if process.wait() != 0:
            raise RuntimeError(f"Cannot read package payload: {deb.name}")
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
        process.wait()
    return "\n".join(paths) + "\n" if paths else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository-url", default="https://raw.githubusercontent.com/leonpresistforever-png/Oceanstudio-packages/main/apt")
    parser.add_argument("--download-url", help="Immutable snapshot URL; installed sources still use --repository-url")
    parser.add_argument("--seed", action="append", default=[])
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--catalog-output", type=Path,
                        default=ROOT / "android/app/src/main/assets/ocean/repository")
    args = parser.parse_args()
    seeds = tuple(args.seed) or DEFAULT_SEEDS
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ocean-bootstrap-") as temporary:
        work = Path(temporary)
        inrelease, compressed, key = work / "InRelease", work / "Packages.gz", work / "ocean.gpg"
        download_url = args.download_url or args.repository_url
        download(f"{download_url}/dists/stable/InRelease", inrelease)
        download(f"{download_url}/dists/stable/main/binary-aarch64/Packages.gz", compressed)
        download(f"{download_url}/ocean.gpg", key)
        release = work / "Release"
        run("gpgv", "--keyring", key, "--output", release, inrelease, stdout=subprocess.DEVNULL)
        expected = (ROOT / "ocean-packages/keys/ocean-development-repository.fingerprint").read_text().strip()
        shown = run("gpg", "--batch", "--show-keys", "--with-colons", key, stdout=subprocess.PIPE).stdout
        actual = next(line.split(":")[9] for line in shown.splitlines() if line.startswith("fpr:"))
        if actual != expected:
            raise RuntimeError(f"repository key mismatch: expected={expected} actual={actual}")
        release_fields = paragraphs(release.read_text())[0]
        if "Valid-Until" not in release_fields or parsedate_to_datetime(release_fields["Valid-Until"]) <= datetime.now(timezone.utc):
            raise RuntimeError("Refusing to bundle expired repository metadata")
        packages = verify_catalog_index(release.read_text(), compressed.read_bytes())
        list_prefix = write_catalog(args.catalog_output, args.repository_url, inrelease, compressed, key, packages)
        entries = paragraphs(packages.decode())
        if args.catalog_only:
            print(f"Prepared verified catalogue: {len(entries)} packages")
            return 0
        closure = resolve(entries, seeds)

        root = work / "root"
        prefix = root / PREFIX
        debs = work / "debs"
        info = prefix / "var/lib/dpkg/info"
        debs.mkdir(); info.mkdir(parents=True)
        status_blocks: list[str] = []
        installed: list[dict[str, object]] = []
        for entry in closure:
            for field in ("Package", "Version", "Architecture", "Filename", "SHA256"):
                if not entry.get(field):
                    raise RuntimeError(f"signed index entry lacks {field}: {entry.get('Package', '<unknown>')}")
            deb = debs / Path(entry["Filename"]).name
            download(f"{download_url}/{entry['Filename']}", deb)
            digest = hashlib.sha256(deb.read_bytes()).hexdigest()
            if digest != entry["SHA256"]:
                raise RuntimeError(f"package checksum mismatch: {deb.name}")
            run("dpkg-deb", "-x", deb, root)
            control = work / "control" / entry["Package"]
            control.mkdir(parents=True)
            run("dpkg-deb", "-e", deb, control)
            control_fields = (control / "control").read_text().rstrip()
            status_blocks.append(control_fields + "\nStatus: install ok installed\n")
            (info / f"{entry['Package']}.list").write_text(package_file_list(deb))
            for name in ("md5sums", "conffiles", "preinst", "postinst", "prerm", "postrm", "config", "triggers"):
                source = control / name
                if source.is_file():
                    target = info / f"{entry['Package']}.{name}"
                    shutil.copy2(source, target)
                    if name in {"preinst", "postinst", "prerm", "postrm", "config"}:
                        target.chmod(0o755)
            installed.append({"name": entry["Package"], "version": entry["Version"], "sha256": digest, "artifact": deb.name})

        (prefix / "var/lib/dpkg/status").write_text("\n".join(status_blocks))
        (prefix / "var/lib/dpkg/updates").mkdir(parents=True, exist_ok=True)
        (prefix / "tmp").mkdir(parents=True, exist_ok=True)
        (prefix / "tmp").chmod(0o700)
        (prefix / "var/run").mkdir(parents=True, exist_ok=True)
        (prefix / "var/lib/apt/lists/partial").mkdir(parents=True, exist_ok=True)
        lists = prefix / "var/lib/apt/lists"
        (lists / (list_prefix + "InRelease")).write_bytes(inrelease.read_bytes())
        (lists / (list_prefix + "main_binary-aarch64_Packages")).write_bytes(packages)
        (prefix / "var/cache/apt/archives/partial").mkdir(parents=True, exist_ok=True)
        (prefix / "var/log/apt").mkdir(parents=True, exist_ok=True)
        # Repository packages may carry their upstream default source files.
        # A hydrated Ocean runtime must trust and address only Ocean's signed
        # repository, so replace inherited source and keyring configuration.
        apt_etc = prefix / "etc/apt"
        for inherited in (apt_etc / "sources.list", apt_etc / "sources.list.d", apt_etc / "trusted.gpg.d", apt_etc / "keyrings"):
            if inherited.is_dir():
                shutil.rmtree(inherited)
            elif inherited.exists() or inherited.is_symlink():
                inherited.unlink()
        (apt_etc / "keyrings").mkdir(parents=True, exist_ok=True)
        shutil.copy2(key, prefix / "etc/apt/keyrings/ocean.gpg")
        sources = prefix / "etc/apt/sources.list.d"
        sources.mkdir(parents=True, exist_ok=True)
        (sources / "ocean.list").write_text(
            f"deb [signed-by=/data/data/studio.ocean.app/files/usr/etc/apt/keyrings/ocean.gpg] {args.repository_url} stable main\n"
        )
        shell = prefix / "bin/sh"
        if not shell.exists():
            shell.symlink_to("bash")

        # Build-prefix absolute symlinks are valid inside packages but Android
        # may expose filesDir as /data/user/0. Store relative links so the same
        # archive works through either canonical path spelling.
        canonical_prefix = "/data/data/studio.ocean.app/files/usr"
        for path in prefix.rglob("*"):
            if not path.is_symlink():
                continue
            target = os.readlink(path)
            if target == canonical_prefix or target.startswith(canonical_prefix + "/"):
                logical_target = prefix / target[len(canonical_prefix) + 1:]
                path.unlink()
                path.symlink_to(os.path.relpath(logical_target, path.parent))

        archive = output / "ocean-aarch64.tar.zst"
        tar_path = work / "ocean-aarch64.tar"
        def reproducible(member: tarfile.TarInfo) -> tarfile.TarInfo:
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            member.mtime = 0
            return member
        with tarfile.open(tar_path, "w") as tar:
            tar.add(prefix, arcname="usr", recursive=True, filter=reproducible)
        with tarfile.open(tar_path) as tar:
            archive_entries = len(set(tar.getnames()))
        compress_zstd(tar_path, archive)
        manifest = {
            "bootstrapVersion": "1.0.4",
            "architecture": "aarch64",
            "packageName": "studio.ocean.app",
            "prefix": "/data/data/studio.ocean.app/files/usr",
            "archive": archive.name,
            "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "archiveSize": archive.stat().st_size,
            "entryCount": archive_entries,
            "packageList": [x["name"] for x in installed],
            "packages": installed,
            "buildCommit": os.environ.get("GITHUB_SHA", "local-signed-repository-hydration"),
            "repositoryUrl": args.repository_url,
            "repositoryKeyFingerprint": actual,
        }
        (output / "ocean-aarch64.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Hydrated {len(installed)} signed packages into {archive} ({archive.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
