"""
Blender subprocess bridge. Finds the Blender executable, launches it headless,
and runs scripts/blender_render.py with the given parameters.
"""
import os
import sys
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


BLENDER_SEARCH_PATHS = [
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/snap/bin/blender",
    "blender",  # PATH fallback
]


def find_blender(override: Optional[str] = None) -> str:
    if override and os.path.isfile(override):
        return override

    env_path = os.environ.get("SWIFT_BLENDER_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    for candidate in BLENDER_SEARCH_PATHS:
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("blender")
    if found:
        return found
    raise FileNotFoundError(
        "Blender not found. Set SWIFT_BLENDER_PATH or install Blender 4.x."
    )


@dataclass
class RenderJob:
    char_fbx: str
    anim_fbx: Optional[str] = None
    out_dir: Optional[str] = None
    width: int = 64
    height: int = 64
    fps: int = 12
    frame_start: int = 1
    frame_end: Optional[int] = None
    camera_angle: str = "front"
    pixel_size: int = 4
    blender_path: Optional[str] = None

    def validate(self):
        if not os.path.isfile(self.char_fbx):
            raise FileNotFoundError(f"Character FBX not found: {self.char_fbx}")
        if self.anim_fbx and not os.path.isfile(self.anim_fbx):
            raise FileNotFoundError(f"Animation FBX not found: {self.anim_fbx}")


@dataclass
class RenderResult:
    success: bool
    frames_dir: str
    frame_count: int
    frame_paths: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None

    def sprite_frames(self):
        """Return sorted list of frame PNG paths."""
        return sorted(
            p for p in self.frame_paths
            if p.endswith(".png")
        )


class BlenderBridge:
    RENDER_SCRIPT = Path(__file__).parent.parent / "scripts" / "blender_render.py"

    def __init__(self, blender_path: Optional[str] = None):
        self._blender_path = blender_path

    @property
    def blender_path(self) -> str:
        return find_blender(self._blender_path)

    def render(self, job: RenderJob, progress_cb=None) -> RenderResult:
        job.validate()

        out_dir = job.out_dir or tempfile.mkdtemp(prefix="swift_render_")
        meta_path = os.path.join(out_dir, "meta.json")

        cmd = [
            self.blender_path,
            "--background",
            "--python", str(self.RENDER_SCRIPT),
            "--",
            "--fbx", job.char_fbx,
            "--out", out_dir,
            "--width", str(job.width),
            "--height", str(job.height),
            "--fps", str(job.fps),
            "--start", str(job.frame_start),
            "--camera-angle", job.camera_angle,
            "--pixel-size", str(job.pixel_size),
            "--meta", meta_path,
        ]
        if job.anim_fbx:
            cmd += ["--anim", job.anim_fbx]
        if job.frame_end is not None:
            cmd += ["--end", str(job.frame_end)]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            output_lines = []
            for line in proc.stdout:
                output_lines.append(line.rstrip())
                if progress_cb:
                    progress_cb(line.rstrip())

            proc.wait()
            if proc.returncode != 0:
                return RenderResult(
                    success=False,
                    frames_dir=out_dir,
                    frame_count=0,
                    error="\n".join(output_lines[-20:]),
                )

            # Collect results
            meta = {}
            if os.path.isfile(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)

            frames = sorted(
                str(p) for p in Path(out_dir).glob("frame_*.png")
            )
            return RenderResult(
                success=True,
                frames_dir=out_dir,
                frame_count=len(frames),
                frame_paths=frames,
                metadata=meta,
            )

        except FileNotFoundError as e:
            return RenderResult(
                success=False,
                frames_dir=out_dir,
                frame_count=0,
                error=str(e),
            )

    def check_blender(self) -> tuple[bool, str]:
        """Quick sanity check that Blender is callable."""
        try:
            path = self.blender_path
            result = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            version_line = result.stdout.split("\n")[0]
            return True, version_line
        except Exception as e:
            return False, str(e)
