#!/usr/bin/env python3
"""Quality gate for Ocean-owned APT candidates (staging and optional pool audit)."""
from __future__ import annotations

import io
import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PREFIX = "/data/data/studio.ocean.app/files/usr"

# Names that are part of the verified Ocean runtime; never treat as filler.
OCEAN_ECOSYSTEM_ALLOWLIST = frozenset(
    {
        "ocean-distro",
        "ocean-pkg",
        "ocean-tools",
        "ocean-hello",
        "proot-distro",
        "ocean-shard-router",
        "ocean-shard-auth-store",
        "ocean-shard-tool-mux",
        "ocean-shard-agent-flow",
        "ocean-shard-blob-split",
        "ocean-fixture",
    }
)

JUNK_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^ocean-term-media-\d+$", re.I),
    re.compile(r"^ocean-term-media-core$", re.I),
    re.compile(r"^ocean-term-[a-z]+-\d{2,}$", re.I),
    re.compile(r"^ocean-pack-\d{3,}$", re.I),
    re.compile(r"^ocean-skill-filler-", re.I),
    re.compile(r"^placeholder-", re.I),
    re.compile(r"^stub-", re.I),
    re.compile(r"-placeholder$", re.I),
    re.compile(r"^visual-only-", re.I),
)

PLACEHOLDER_TEXT = re.compile(
    r"\b(placeholder|visual[- ]only|lorem ipsum|todo:\s*implement|not implemented|dummy package|filler package)\b",
    re.I,
)

MIN_SKILL_BODY = 80


@dataclass(frozen=True)
class QualityVerdict:
    package: str
    version: str
    reject: bool
    reasons: tuple[str, ...]


def _fields(control_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    key = ""
    for line in control_text.splitlines():
        if line.startswith((" ", "\t")) and key:
            result[key] += "\n" + line
        elif ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def _list_deb_members(deb: Path) -> list[tuple[str, str]]:
    """Return (mode, path) rows from dpkg-deb -c."""
    output = subprocess.check_output(["dpkg-deb", "-c", str(deb)], text=True)
    rows: list[tuple[str, str]] = []
    for line in output.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6:
            rows.append((parts[0], parts[5]))
    return rows


def _skill_paths(members: Iterable[tuple[str, str]]) -> list[str]:
    found: list[str] = []
    for _mode, path in members:
        if path.endswith("/SKILL.md") or path.endswith("SKILL.md"):
            found.append(path)
    return found


def _read_skill_bodies(deb: Path, skill_paths: list[str]) -> dict[str, str]:
    if not skill_paths:
        return {}
    data = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(deb)])
    bodies: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for name in skill_paths:
            member = archive.getmember(name.lstrip("./"))
            if not member.isfile():
                continue
            raw = archive.extractfile(member)
            if raw is None:
                continue
            bodies[name] = raw.read().decode("utf-8", errors="replace")
    return bodies


def _entry_points(members: Iterable[tuple[str, str]]) -> list[str]:
    bin_marker = f"{PREFIX.lstrip('/')}/bin/"
    alt_marker = "/bin/"
    hits: list[str] = []
    for mode, path in members:
        normalized = path.lstrip("./")
        if "x" not in mode:
            continue
        if bin_marker in normalized or normalized.startswith("bin/"):
            hits.append(normalized)
        elif alt_marker in normalized and normalized.endswith(
            (
                "ocean-shard-router",
                "ocean-shard-auth-store",
                "ocean-shard-tool-mux",
                "ocean-shard-agent-flow",
                "ocean-shard-blob-split",
            )
        ):
            hits.append(normalized)
    return hits


def junk_name_reason(package: str) -> str | None:
    if package in OCEAN_ECOSYSTEM_ALLOWLIST:
        return None
    for pattern in JUNK_NAME_PATTERNS:
        if pattern.search(package):
            return f"junk name pattern: {pattern.pattern}"
    if re.fullmatch(r"ocean_\d+", package):
        return "sequential filler package name ocean_<n>"
    return None


def assess_control(control_text: str, members: list[tuple[str, str]] | None = None) -> QualityVerdict:
    control = _fields(control_text)
    package = control.get("Package", "<unknown>")
    version = control.get("Version", "?")
    reasons: list[str] = []

    name_reason = junk_name_reason(package)
    if name_reason:
        reasons.append(name_reason)

    description = control.get("Description", "")
    if PLACEHOLDER_TEXT.search(description):
        reasons.append("placeholder description text")

    return QualityVerdict(
        package=package,
        version=version,
        reject=bool(reasons),
        reasons=tuple(reasons),
    )


def assess_deb(deb: Path, control_text: str | None = None) -> QualityVerdict:
    if control_text is None:
        data = subprocess.check_output(["dpkg-deb", "--ctrl-tarfile", str(deb)])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            controls = [m for m in archive if m.name.removeprefix("./") == "control"]
            control_text = archive.extractfile(controls[0]).read().decode("utf-8")
    members = _list_deb_members(deb)
    verdict = assess_control(control_text, members)
    reasons = list(verdict.reasons)

    skill_paths = _skill_paths(members)
    if skill_paths:
        bodies = _read_skill_bodies(deb, skill_paths)
        for path, body in bodies.items():
            stripped = body.strip()
            if len(stripped) < MIN_SKILL_BODY:
                reasons.append(f"empty or stub SKILL.md: {path} ({len(stripped)} bytes)")
            if PLACEHOLDER_TEXT.search(body):
                reasons.append(f"placeholder SKILL.md: {path}")

    executables = _entry_points(members)
    control = _fields(control_text)
    section = control.get("Section", "").lower()
    description = control.get("Description", "").lower()
    is_non_bin_or_fixture = (
        section in ("doc", "utils", "misc", "libs", "libdevel", "fonts")
        or verdict.package.startswith("lib")
        or verdict.package.endswith(("-doc", "-dev", "-data", "-common"))
        or "fixture" in description
        or verdict.package in OCEAN_ECOSYSTEM_ALLOWLIST
    )
    if not executables and not control.get("Provides", "").strip() and not is_non_bin_or_fixture:
        if not reasons or "no entry point" not in reasons[-1]:
            reasons.append("no entry point (missing executable under prefix bin/ and no Provides)")

    return QualityVerdict(
        package=verdict.package,
        version=verdict.version,
        reject=bool(reasons),
        reasons=tuple(reasons),
    )


def assess_name_set(names: Iterable[str]) -> dict[str, list[str]]:
    """Return duplicate package keys and junk hits for an index name list."""
    seen: dict[str, int] = {}
    duplicates: dict[str, list[str]] = {}
    junk: dict[str, list[str]] = {}
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        reason = junk_name_reason(name)
        if reason:
            junk.setdefault(reason, []).append(name)
    for name, count in seen.items():
        if count > 1:
            duplicates[name] = [f"indexed {count} times"]
    return {"duplicates": duplicates, "junk_by_reason": junk}
