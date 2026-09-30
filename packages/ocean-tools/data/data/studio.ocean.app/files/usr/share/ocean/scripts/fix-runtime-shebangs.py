#!/data/data/studio.ocean.app/files/usr/bin/python3
"""Rewrite /usr/bin/env and /bin/* shebangs to Ocean prefix interpreters."""
from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

DEFAULT_PREFIX = "/data/data/studio.ocean.app/files/usr"
INTERPRETERS = {
    "bash": "bash",
    "sh": "sh",
    "dash": "dash",
    "zsh": "zsh",
    "python": "python",
    "python3": "python3",
    "node": "node",
    "nodejs": "node",
    "perl": "perl",
    "ruby": "ruby",
    "php": "php",
}


def rewrite_line(line: str, prefix: str) -> str | None:
    if not line.startswith("#!"):
        return None
    body = line[2:].strip()
    if not body:
        return None
    parts = body.split()
    index = 1 if parts and parts[0] == "-S" else 0
    if index >= len(parts):
        return None

    def tail(from_index: int) -> str:
        return " ".join(parts[from_index:])

    if parts[index].endswith("env") or parts[index] == "env" or "/usr/bin/env" in parts[index]:
        command_index = index + 1
        if command_index < len(parts) and parts[command_index] == "-S":
            command_index += 1
        if command_index >= len(parts):
            return None
        interpreter = parts[command_index]
        extra = tail(command_index + 1)
    else:
        interpreter = parts[index]
        extra = tail(index + 1)

    name = interpreter.rsplit("/", 1)[-1].lower()
    mapped = INTERPRETERS.get(name)
    if mapped is None and (interpreter.startswith("/bin/") or interpreter.startswith("/usr/bin/")):
        mapped = name
    if mapped is None:
        return None
    rewritten = f"#!{prefix}/bin/{mapped}"
    if extra:
        rewritten += f" {extra}"
    return rewritten if rewritten != line else None


def rewrite_file(path: Path, prefix: str, dry_run: bool) -> bool:
    data = path.read_bytes()
    if len(data) < 2 or not data.startswith(b"#!"):
        return False
    end = data.find(b"\n")
    if end < 0:
        end = len(data)
    line = data[:end].decode("utf-8", errors="replace")
    rewritten = rewrite_line(line, prefix)
    if rewritten is None:
        return False
    if dry_run:
        print(f"would rewrite {path}: {line} -> {rewritten}")
        return True
    new_data = rewritten.encode("utf-8") + data[end:]
    path.write_bytes(new_data)
    mode = path.stat().st_mode
    if not (mode & stat.S_IXUSR):
        path.chmod(mode | stat.S_IXUSR)
    print(f"rewrote {path}")
    return True


def scan_roots(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default=os.environ.get("PREFIX", DEFAULT_PREFIX))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    prefix = args.prefix.rstrip("/")
    roots = args.paths or [
        Path(prefix) / "bin",
        Path(prefix) / "libexec",
        Path(prefix) / "lib" / "apt" / "methods",
    ]
    changed = 0
    for path in scan_roots(roots):
        try:
            if rewrite_file(path, prefix, args.dry_run):
                changed += 1
        except OSError as error:
            print(f"skip {path}: {error}")
    print(f"{'would rewrite' if args.dry_run else 'rewrote'} {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
