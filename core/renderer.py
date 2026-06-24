"""
Render job orchestration: wraps BlenderBridge with a job queue
and optional style parameters from AI analysis.
"""
import os
import tempfile
from dataclasses import dataclass
from typing import Optional, Callable

from core.blender_bridge import BlenderBridge, RenderJob, RenderResult
from core.exporter import Exporter


@dataclass
class StyleParams:
    """Style parameters extracted from reference sheets by AI."""
    pixel_size: int = 4
    width: int = 64
    height: int = 64
    fps: int = 12
    camera_angle: str = "front"
    palette_hint: Optional[str] = None     # e.g. "warm, limited 16 colors"
    exaggeration: float = 1.0              # 1.0 = normal, >1 = more squash/stretch


@dataclass
class RendererConfig:
    blender_path: Optional[str] = None
    default_width: int = 64
    default_height: int = 64
    default_fps: int = 12
    default_pixel_size: int = 4
    default_camera_angle: str = "front"


class Renderer:
    def __init__(self, config: Optional[RendererConfig] = None):
        self._config = config or RendererConfig()
        self._bridge = BlenderBridge(self._config.blender_path)

    def render(
        self,
        char_fbx: str,
        anim_fbx: Optional[str] = None,
        out_dir: Optional[str] = None,
        style: Optional[StyleParams] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> RenderResult:
        s = style or StyleParams()
        job = RenderJob(
            char_fbx=char_fbx,
            anim_fbx=anim_fbx,
            out_dir=out_dir or tempfile.mkdtemp(prefix="swift_"),
            width=s.width or self._config.default_width,
            height=s.height or self._config.default_height,
            fps=s.fps or self._config.default_fps,
            pixel_size=s.pixel_size or self._config.default_pixel_size,
            camera_angle=s.camera_angle or self._config.default_camera_angle,
            blender_path=self._config.blender_path,
        )
        return self._bridge.render(job, progress_cb=progress_cb)

    def render_and_export(
        self,
        char_fbx: str,
        anim_fbx: Optional[str] = None,
        export_path: Optional[str] = None,
        export_format: str = "sprite_sheet",
        style: Optional[StyleParams] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        result = self.render(char_fbx, anim_fbx, style=style, progress_cb=progress_cb)
        if not result.success:
            raise RuntimeError(f"Render failed: {result.error}")

        exporter = Exporter(result.sprite_frames(), fps=style.fps if style else 12)
        out = export_path or os.path.join(result.frames_dir, "output")

        if export_format == "sprite_sheet":
            return exporter.to_sprite_sheet(out + ".png")
        elif export_format == "gif":
            return exporter.to_gif(out + ".gif")
        elif export_format == "frames_json":
            return exporter.to_frames_json(out + "_frames")
        else:
            raise ValueError(f"Unknown export format: {export_format}")

    def check(self) -> tuple[bool, str]:
        return self._bridge.check_blender()
