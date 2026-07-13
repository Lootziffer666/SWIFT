#!/usr/bin/env python3
"""Execute a TRIVIUM LAB actor-realization job through SWIFT's existing CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = "1.0.0"
BACKGROUND_MODES = {"none", "connected", "color-key", "ai"}


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
    options = request.get("options") or {}
    mode = options.get("backgroundRemoval", "none")
    if mode not in BACKGROUND_MODES:
        errors.append(f"options.backgroundRemoval must be one of {', '.join(sorted(BACKGROUND_MODES))}")
    tolerance = options.get("backgroundTolerance", 24)
    if not isinstance(tolerance, int) or not 0 <= tolerance <= 255:
        errors.append("options.backgroundTolerance must be an integer from 0 to 255")
    return errors


def unresolved_capabilities(request: dict[str, Any]) -> list[str]:
    options = request.get("options") or {}
    unresolved: list[str] = []
    if options.get("baselineNormalization", False):
        unresolved.append("feet-baseline-normalization")
    return unresolved


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


def parse_color(value: Any) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) == 6:
            try:
                return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError as exc:
                raise ValueError("options.backgroundColor must be #RRGGBB") from exc
    if isinstance(value, list) and len(value) == 3 and all(isinstance(x, int) and 0 <= x <= 255 for x in value):
        return tuple(value)  # type: ignore[return-value]
    raise ValueError("options.backgroundColor must be #RRGGBB or [r,g,b]")


def color_matches(pixel: tuple[int, int, int, int], target: tuple[int, int, int], tolerance: int) -> bool:
    return max(abs(pixel[i] - target[i]) for i in range(3)) <= tolerance


def remove_color_key(image: Any, target: tuple[int, int, int], tolerance: int) -> Any:
    rgba = image.convert("RGBA")
    pixels = list(rgba.getdata())
    rgba.putdata([
        (r, g, b, 0 if color_matches((r, g, b, a), target, tolerance) else a)
        for r, g, b, a in pixels
    ])
    return rgba


def remove_connected(image: Any, target: tuple[int, int, int], tolerance: int) -> Any:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    px = rgba.load()
    queue: deque[tuple[int, int]] = deque()
    visited: set[tuple[int, int]] = set()

    for x in range(width):
        queue.append((x, 0))
        if height > 1:
            queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        if width > 1:
            queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if (x, y) in visited:
            continue
        visited.add((x, y))
        pixel = px[x, y]
        if not color_matches(pixel, target, tolerance):
            continue
        px[x, y] = (pixel[0], pixel[1], pixel[2], 0)
        if x > 0:
            queue.append((x - 1, y))
        if x + 1 < width:
            queue.append((x + 1, y))
        if y > 0:
            queue.append((x, y - 1))
        if y + 1 < height:
            queue.append((x, y + 1))
    return rgba


def load_frame_rects(manifest_path: Path | None, image_size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rects = manifest.get("frameRects") if isinstance(manifest, dict) else None
        if isinstance(rects, dict):
            result: list[tuple[int, int, int, int]] = []
            for rect in rects.values():
                if isinstance(rect, dict) and all(isinstance(rect.get(k), int) for k in ("x", "y", "w", "h")):
                    x, y, w, h = (rect[k] for k in ("x", "y", "w", "h"))
                    result.append((x, y, x + w, y + h))
                elif isinstance(rect, list) and len(rect) == 4 and all(isinstance(v, int) for v in rect):
                    x, y, w, h = rect
                    result.append((x, y, x + w, y + h))
            if result:
                return result
    return [(0, 0, image_size[0], image_size[1])]


def ai_processor(model_name: str | None) -> Callable[[Any], Any]:
    try:
        from rembg import new_session, remove
    except ImportError as exc:
        raise RuntimeError(
            "AI background removal is optional and not installed. "
            f"Install it locally with: {sys.executable} -m pip install rembg onnxruntime"
        ) from exc

    session = new_session(model_name) if model_name else new_session()

    def process(image: Any) -> Any:
        result = remove(image.convert("RGBA"), session=session)
        if hasattr(result, "convert"):
            return result.convert("RGBA")
        from PIL import Image
        return Image.open(BytesIO(result)).convert("RGBA")

    return process


def apply_background_removal(
    sheet_path: Path,
    manifest_path: Path | None,
    options: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    mode = options.get("backgroundRemoval", "none")
    if mode == "none":
        return sheet_path, {"mode": "none", "local": True, "applied": False}

    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for background removal") from exc

    image = Image.open(sheet_path).convert("RGBA")
    rects = load_frame_rects(manifest_path, image.size)
    target = parse_color(options.get("backgroundColor"))
    tolerance = int(options.get("backgroundTolerance", 24))

    if mode == "ai":
        processor = ai_processor(options.get("rembgModel"))
    else:
        if target is None:
            target = image.getpixel((0, 0))[:3]
        processor = (
            (lambda frame: remove_connected(frame, target, tolerance))
            if mode == "connected"
            else (lambda frame: remove_color_key(frame, target, tolerance))
        )

    output = Image.new("RGBA", image.size, (0, 0, 0, 0))
    for box in rects:
        frame = image.crop(box)
        output.alpha_composite(processor(frame), dest=(box[0], box[1]))

    result_path = sheet_path.with_name(f"{sheet_path.stem}_transparent.png")
    output.save(result_path, "PNG")
    return result_path, {
        "mode": mode,
        "local": True,
        "cloudUpload": False,
        "applied": True,
        "frameCount": len(rects),
        "modelDownloadsOnFirstUse": mode == "ai",
    }


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
        unresolved = unresolved_capabilities(request)
        strict = bool((request.get("options") or {}).get("strictCapabilities", True))
        if unresolved and strict:
            print(json.dumps({
                "status": "needs_human_review",
                "error": "requested capabilities are not wired into the LAB adapter",
                "unresolvedCapabilities": unresolved,
            }), file=sys.stderr)
            return 4
        command = build_command(request, args.swift_root.resolve())
        if args.dry_run:
            print(json.dumps({
                "status": "success",
                "dryRun": True,
                "command": command,
                "backgroundRemoval": (request.get("options") or {}).get("backgroundRemoval", "none"),
                "warnings": unresolved,
            }))
            return 0
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            sys.stderr.write(result.stderr or json.dumps({"status": "error", "error": "SWIFT failed"}) + "\n")
            return result.returncode
        swift_summary = json.loads(result.stdout)
        sheet_value = swift_summary.get("sheet_path")
        manifest_value = swift_summary.get("manifest_path")
        sheet_path = Path(sheet_value).resolve() if sheet_value else None
        manifest_path = Path(manifest_value).resolve() if manifest_value else None
        background = {"mode": "none", "local": True, "applied": False}
        if sheet_path and sheet_path.exists():
            sheet_path, background = apply_background_removal(
                sheet_path,
                manifest_path,
                request.get("options") or {},
            )
        artifacts = list(swift_summary.get("artifacts", []))
        if background.get("applied") and sheet_path:
            artifacts.append({"type": "transparent_sprite_sheet", "path": str(sheet_path)})
        envelope = {
            "schemaVersion": SCHEMA_VERSION,
            "module": "trivium-lab",
            "producer": "swift",
            "jobId": request.get("jobId"),
            "status": "success",
            "artifacts": artifacts,
            "sheetPath": str(sheet_path) if sheet_path else sheet_value,
            "manifestPath": manifest_value,
            "depthPath": swift_summary.get("depth_path"),
            "animationNames": swift_summary.get("animation_names", []),
            "mappingVersion": swift_summary.get("mapping_version"),
            "backgroundRemoval": background,
            "warnings": unresolved,
        }
        print(json.dumps(envelope))
        return 0
    except RuntimeError as exc:
        print(json.dumps({
            "status": "needs_installation",
            "error": str(exc),
            "localOnly": True,
            "installCommand": f"{sys.executable} -m pip install rembg onnxruntime",
        }), file=sys.stderr)
        return 3
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
