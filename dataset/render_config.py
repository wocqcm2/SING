#!/usr/bin/env python3
"""Render a local MCP config from the public placeholder-only configuration.

The script intentionally does not execute or source the env files. Values are
parsed as data and substituted into JSON strings, so shell metacharacters in a
credential are not evaluated.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


VARIABLE_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def parse_env(path: Path) -> dict[str, str]:
    """Parse single-line assignments; quoted contents remain literal UTF-8."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected NAME=value")

        name, value = line.split("=", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"{path}:{line_number}: invalid variable name {name!r}")

        value = value.strip()
        if value and value[0] in {'"', "'"}:
            quote = value[0]
            if len(value) < 2 or value[-1] != quote:
                raise ValueError(f"{path}:{line_number}: unmatched quote")
            value = value[1:-1]
        else:
            value = re.sub(r"\s+#.*$", "", value).rstrip()
        values[name] = value
    return values


def collect_variables(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            found.update(collect_variables(child))
    elif isinstance(value, list):
        for child in value:
            found.update(collect_variables(child))
    elif isinstance(value, str):
        found.update(VARIABLE_RE.findall(value))
    return found


def substitute(value: object, variables: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {key: substitute(child, variables) for key, child in value.items()}
    if isinstance(value, list):
        return [substitute(child, variables) for child in value]
    if isinstance(value, str):
        return VARIABLE_RE.sub(lambda match: variables.get(match.group(1), match.group(0)), value)
    return value


def allow_noninteractive_npx(value: object) -> object:
    """Add npx's install-confirmation flag to launch configs on request."""
    if isinstance(value, dict):
        result = {key: allow_noninteractive_npx(child) for key, child in value.items()}
        args = result.get("args")
        if result.get("command") == "npx" and isinstance(args, list) and "-y" not in args and "--yes" not in args:
            result["args"] = ["-y", *args]
        return result
    if isinstance(value, list):
        return [allow_noninteractive_npx(child) for child in value]
    return value


def parse_args() -> argparse.Namespace:
    dataset_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=dataset_dir / "mcp_config_779.public.json",
        help="Public placeholder config to render.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=dataset_dir / "mcp_config_779.local.json",
        help="Destination; the input file is never overwritten.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=dataset_dir / ".env",
        help="Non-secret settings dotenv file, read as data.",
    )
    parser.add_argument(
        "--api-env-file",
        type=Path,
        default=dataset_dir / "api.env",
        help="API credentials dotenv file, read as data.",
    )
    parser.add_argument(
        "--servers",
        help="Comma-separated server names. Omit to retain all servers.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if a variable required by the selected template has no value.",
    )
    parser.add_argument(
        "--list-vars",
        action="store_true",
        help="Print variables needed by the selected servers and do not write output.",
    )
    parser.add_argument(
        "--client-config",
        action="store_true",
        help="Write only the mcpServers object in a client-ready config (omit _meta).",
    )
    parser.add_argument(
        "--npx-yes",
        action="store_true",
        help="Add -y to npx launches so package installation cannot pause for confirmation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    if input_path == output_path:
        print("error: refusing to overwrite the public input config", file=sys.stderr)
        return 2

    with input_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if args.client_config and not isinstance(config.get("mcpServers"), dict):
        print("error: --client-config requires an input containing mcpServers", file=sys.stderr)
        return 2
    if args.servers:
        if not isinstance(config.get("mcpServers"), dict):
            print("error: --servers requires an input containing mcpServers", file=sys.stderr)
            return 2
        requested = [name.strip() for name in args.servers.split(",") if name.strip()]
        missing = [name for name in requested if name not in config["mcpServers"]]
        if missing:
            print(f"error: unknown server(s): {', '.join(missing)}", file=sys.stderr)
            return 2
        config["mcpServers"] = {name: config["mcpServers"][name] for name in requested}

    scope = (
        config["mcpServers"]
        if isinstance(config.get("mcpServers"), dict)
        else {key: value for key, value in config.items() if key != "_meta"}
    )
    needed_vars = collect_variables(scope)
    # HTTP entries may launch a separate process recorded under _meta. Its
    # placeholders still belong to the selected server's setup.
    if isinstance(config.get("mcpServers"), dict):
        launch_requirements = config.get("_meta", {}).get("launch_requirements", {})
        for name in config["mcpServers"]:
            needed_vars.update(
                collect_variables(launch_requirements.get(name, {}).get("startup", {}))
            )
    needed = sorted(needed_vars)
    if args.list_vars:
        print("\n".join(needed))
        return 0

    try:
        dataset_dir = Path(__file__).resolve().parent
        local_names = parse_env(dataset_dir / ".env.example").keys()
        credential_names = parse_env(dataset_dir / "api.env.example").keys()
        dotenv_values = parse_env(args.env_file)
        api_values = parse_env(args.api_env_file)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    misplaced_credentials = sorted(dotenv_values.keys() & credential_names)
    misplaced_settings = sorted(api_values.keys() & local_names)
    if misplaced_credentials or misplaced_settings:
        if misplaced_credentials:
            print(
                f"error: {', '.join(misplaced_credentials)} belong in {args.api_env_file}",
                file=sys.stderr,
            )
        if misplaced_settings:
            print(
                f"error: {', '.join(misplaced_settings)} belong in {args.env_file}",
                file=sys.stderr,
            )
        return 2

    # Only HOME and PATH are inherited from the process. All other template
    # values use the two documented files, so there is one supported layout.
    variables = {key: os.environ[key] for key in ("HOME", "PATH") if os.environ.get(key)}
    variables.update({key: value for key, value in dotenv_values.items() if value != ""})
    variables.update({key: value for key, value in api_values.items() if value != ""})
    variables.setdefault("HOME", str(Path.home()))
    # Check the original template, not literal ${...} text inside supplied values.
    unresolved = sorted(set(needed) - variables.keys())
    rendered = substitute(config, variables)
    if args.strict and unresolved:
        print("error: unresolved variables: " + ", ".join(unresolved), file=sys.stderr)
        return 1
    if args.strict and isinstance(config.get("mcpServers"), dict):
        launch_requirements = config.get("_meta", {}).get("launch_requirements", {})
        for name in config["mcpServers"]:
            for variable, value_format in launch_requirements.get(name, {}).get(
                "variable_formats", {}
            ).items():
                if value_format != "json_object":
                    print(
                        f"error: unsupported format {value_format!r} for {variable}",
                        file=sys.stderr,
                    )
                    return 2
                try:
                    parsed = json.loads(variables[variable])
                except (KeyError, json.JSONDecodeError):
                    print(f"error: {variable} must be a JSON object", file=sys.stderr)
                    return 1
                if not isinstance(parsed, dict):
                    print(f"error: {variable} must be a JSON object", file=sys.stderr)
                    return 1

    if args.npx_yes:
        rendered = allow_noninteractive_npx(rendered)
    if args.client_config:
        rendered = {"mcpServers": rendered["mcpServers"]}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(rendered, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary_path.replace(output_path)
    print(f"wrote {output_path}")
    if unresolved:
        print("unresolved variables retained: " + ", ".join(unresolved))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
