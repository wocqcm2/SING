#!/usr/bin/env python3
"""Locate or fetch the external source trees required by MCPDATA_ROOT entries.

This prepares source layout only. It never installs dependencies or starts a
server. Existing directories are left untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from render_config import parse_env


DATASET_DIR = Path(__file__).resolve().parent
MARKER = "${MCPDATA_ROOT}/"
SOURCES = {
    "mcp-bench": (
        "mcp_bench/mcp-bench",
        "https://github.com/Accenture/mcp-bench.git",
        "7a8eaeae83a842a2949080acc5473f65e1569daf",
    ),
    "mcp-atlas": (
        "run_servers/Evaluation/mcp-atlas",
        "https://github.com/scaleapi/mcp-atlas.git",
        "f24ba3fb0bfa484c86acb28431fad6d7282455f9",
    ),
}


def source_for_path(value: str) -> str:
    if not value.startswith(MARKER):
        raise ValueError(f"not an MCPDATA_ROOT path: {value}")
    relative = value[len(MARKER) :]
    parts = Path(relative.replace("\\", "/")).parts
    if not parts or ".." in parts or any(part == "" for part in parts):
        raise ValueError(f"unsafe MCPDATA_ROOT path: {value}")
    for name, (prefix, _, _) in SOURCES.items():
        if relative == prefix or relative.startswith(prefix + "/"):
            return name
    raise ValueError(f"no upstream source is recorded for {value}")


def all_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from all_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from all_strings(item)


def inventory() -> tuple[
    dict[str, list[str]], dict[str, list[tuple[str, str]]], dict[str, list[tuple[str, str]]]
]:
    config = json.loads((DATASET_DIR / "mcp_config_779.public.json").read_text(encoding="utf-8"))
    by_source: dict[str, list[str]] = {name: [] for name in SOURCES}
    cwd_entries: dict[str, list[tuple[str, str]]] = {name: [] for name in SOURCES}
    path_entries: dict[str, list[tuple[str, str]]] = {name: [] for name in SOURCES}
    for name, launch in config["mcpServers"].items():
        paths = [value for value in all_strings(launch) if value.startswith(MARKER)]
        roots = {source_for_path(value) for value in paths}
        if len(roots) > 1:
            raise ValueError(f"{name}: references more than one external source")
        for source in roots:
            by_source[source].append(name)
        for value in set(paths):
            path_entries[source_for_path(value)].append((name, value[len(MARKER) :]))
        cwd = launch.get("cwd")
        if isinstance(cwd, str) and cwd.startswith(MARKER):
            cwd_entries[source_for_path(cwd)].append((name, cwd[len(MARKER) :]))
    recorded = config.get("_meta", {}).get("external_source_checkouts", {})
    for source, (relative, url, commit) in SOURCES.items():
        expected = {
            "repository": url,
            "commit": commit,
            "checkout": MARKER + relative,
            "server_names": by_source[source],
        }
        if recorded.get(source) != expected:
            raise ValueError(f"{source}: source metadata does not match the launch templates")
    return by_source, cwd_entries, path_entries


def root_from_args(explicit: str | None) -> Path:
    value = explicit or parse_env(DATASET_DIR / ".env").get("MCPDATA_ROOT") or os.environ.get("MCPDATA_ROOT")
    if not value:
        raise ValueError("set MCPDATA_ROOT in dataset/.env or pass --root ABSOLUTE_PATH")
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise ValueError("MCPDATA_ROOT must be an absolute path")
    return root.resolve()


def clone_source(destination: Path, url: str, commit: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"cloning {url} into {destination}", flush=True)
    subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", url, str(destination)], check=True)
    subprocess.run(["git", "-C", str(destination), "checkout", "--detach", commit], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Absolute MCPDATA_ROOT; otherwise read dataset/.env or environment")
    parser.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    parser.add_argument("--clone", action="store_true", help="Fetch missing upstream checkouts at the recorded commits")
    args = parser.parse_args()
    try:
        root = root_from_args(args.root)
        by_source, cwd_entries, path_entries = inventory()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    selected = list(SOURCES) if args.source == "all" else [args.source]
    missing = False
    for name in selected:
        relative, url, commit = SOURCES[name]
        destination = root.joinpath(*relative.split("/"))
        if not destination.exists() and args.clone:
            try:
                clone_source(destination, url, commit)
            except (OSError, subprocess.CalledProcessError) as exc:
                print(f"error: could not prepare {name}: {exc}", file=sys.stderr)
                missing = True
                continue
        if not destination.is_dir():
            print(f"MISSING {name}: {destination} ({url} at {commit})")
            missing = True
            continue
        print(f"FOUND {name}: {destination} ({len(by_source[name])} launch entries)")
        for server, cwd in cwd_entries[name]:
            path = root.joinpath(*cwd.split("/"))
            if path.is_dir():
                print(f"  OK      {server}: {path}")
            else:
                print(f"  MISSING {server}: {path}")
                missing = True
        if name == "mcp-atlas":
            for server, relative_path in path_entries[name]:
                path = root.joinpath(*relative_path.split("/"))
                if path.name == ".venv":
                    print(f"  GENERATED {server}: {path} (create before using code execution)")
                elif path.exists():
                    print(f"  OK      {server}: {path}")
                else:
                    print(f"  MISSING {server}: {path}")
                    missing = True
    if not missing:
        print("Source paths are present. Install each selected server's dependencies before launching it.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
