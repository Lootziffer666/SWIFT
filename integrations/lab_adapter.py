#!/usr/bin/env python3
"""Execute a TRIVIUM LAB actor-realization job through SWIFT's existing CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read LAB request: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("LAB request must be an object")
    return value


def validate_request(request: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if request.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion must be 1.0.0")
    if request.get("module") != "trivium-lab":
        errors.append("module must be trivium-lab")
    if request.get("action") != "realize-actor":
        errors.append("action must be realize-actor")
    job = request.get("job")
    if not isinstance(job, dict):
        errors.append("job object is required")
    else:
        if job.get("kind") not in {"video", "model", "sheet"}:
            errors.append("job.kind must be video, model, or sheet")
        if not isinstance(job.get("source"), str) or not job["source"].strip():
            errors.append("job.source is required")
        if not isinstance(job.get("output"), str) or not job["output"].strip():
            errors.append("job.output is required")
    return errors


def unsupported_capabilities(request: dict[str, Any]) -> list[str]:
    options = request.get("options") or {}
    unsupported: list[str] = []
    if options.get("backgroundRemoval", "none") != "none":
        unsupported.append("background-removal")
    if options.get("baselineNormalization", False):
        unsupported.append("feet-baseline-normalization")
    return unsupported


def build_command(request: dict[str, Any], swift_root: Path) -> list[str]:
    job = request["job"]
    options = request.get("options") or {}
    source = str(Path(job["source"]).resolve())
    output = str(Path(job["output"]).resolve())
    common = [sys.executable, str(swift_root / "main.py")]

    if job["kind"] == "video":
        command = common + [
            "video2sprite", source,
            "--output", output,
            "--format", "sprite_sheet",
            "--width", str(options.get("width", 64)),
            "--height", str(options.get("height", 64)),
            "--colors", str(options.get("colors", 16)),
            "--manifest",
        ]
        if options.get("smartCrop", True):
            command.append("--smart-crop")
        if options.get("autoScale", True):
            command.append("--auto-scale")
    elif job["kind"] == "model":
        command = common + [
            "render",
            "--model", source,
            "--output", output,
            "--format", "sprite_sheet",
            "--width", str(options.get("width", 64)),
            "--height", str(options.get("height", 64)),
            "--fps", str(options.get("fps", 12)),
            "--anim-name", str(job.get("animation", "idle")),
        ]
        if options.get("depthPass", False):
            command.append("--depth-pass")
        world_states = options.get("worldStates") or []
        if world_states:
            command += ["--world-states", ",".join(map(str, world_states))]
    else:
        manifest = job.get("manifest")
        if not manifest:
            raise ValueError("sheet jobs require job.manifest")
        command = common + [
            "spritesheet", "list", source,
            "--manifest", str(Path(manifest).resolve()),
        ]

    command.append("--json")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--swift-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        request = load_json(args.request)
        errors = validate_request(request)
        if errors:
            raise ValueError("; ".join(errors))
        unsupported = unsupported_capabilities(request)
        strict = bool((request.get("options") or {}).get("strictCapabilities", True))
        if unsupported and strict:
            print(json.dumps({
                "status": "needs_human_review",
                "error": "requested capabilities are not verified in SWIFT",
                "unsupportedCapabilities": unsupported,
            }), file=sys.stderr)
            return 4
        command = build_command(request, args.swift_root.resolve())
        if args.dry_run:
            print(json.dumps({"status": "success", "dryRun": True, "command": command, "warnings": unsupported}))
            return 0
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            sys.stderr.write(result.stderr or json.dumps({"status": "error", "error": "SWIFT failed"}) + "\n")
            return result.returncode
        swift_summary = json.loads(result.stdout)
        envelope = {
            "schemaVersion": SCHEMA_VERSION,
            "module": "trivium-lab",
            "producer": "swift",
            "jobId": request.get("jobId"),
            "status": "success",
            "artifacts": swift_summary.get("artifacts", []),
            "sheetPath": swift_summary.get("sheet_path"),
            "manifestPath": swift_summary.get("manifest_path"),
            "depthPath": swift_summary.get("depth_path"),
            "animationNames": swift_summary.get("animation_names", []),
            "mappingVersion": swift_summary.get("mapping_version"),
            "warnings": unsupported,
        }
        print(json.dumps(envelope))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
