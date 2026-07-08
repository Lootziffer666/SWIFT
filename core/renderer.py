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
    enable_depth: bool = False             # Enable Z-buffer depth pass rendering
    enable_normal: bool = False            # Enable normal-map pass rendering
    enable_emissive: bool = False          # Enable emissive pass rendering


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
            enable_depth=s.enable_depth,
            enable_normal=s.enable_normal,
            enable_emissive=s.enable_emissive,
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
        anim_name: Optional[str] = None,
    ) -> str:
        result = self.render(char_fbx, anim_fbx, style=style, progress_cb=progress_cb)
        if not result.success:
            raise RuntimeError(f"Render failed: {result.error}")

        s = style or StyleParams()
        exporter = Exporter(
            result.sprite_frames(),
            fps=s.fps or self._config.default_fps,
            depth_frame_paths=result.depth_frames() if s.enable_depth else None,
            normal_frame_paths=result.normal_frames() if s.enable_normal else None,
            emissive_frame_paths=result.emissive_frames() if s.enable_emissive else None,
        )
        out = export_path or os.path.join(result.frames_dir, "output")

        if export_format == "sprite_sheet":
            sheet_path = exporter.to_sprite_sheet(out + ".png")

            # Export depth sheet if available
            depth_sheet_path = None
            if s.enable_depth and result.depth_frames():
                depth_sheet_path = exporter.to_depth_sheet(out + "_depth.png")

            # Export normal-map sheet if available
            normal_sheet_path = None
            if s.enable_normal and result.normal_frames():
                normal_sheet_path = exporter.to_normal_sheet(out + "_normal.png")

            # Export emissive sheet if available
            emissive_sheet_path = None
            if s.enable_emissive and result.emissive_frames():
                emissive_sheet_path = exporter.to_emissive_sheet(out + "_emissive.png")

            # Export manifest with depth/normal/emissive metadata
            name = anim_name or os.path.splitext(os.path.basename(anim_fbx or char_fbx))[0]
            depth_image = os.path.basename(depth_sheet_path) if depth_sheet_path else None
            normal_image = os.path.basename(normal_sheet_path) if normal_sheet_path else None
            emissive_image = os.path.basename(emissive_sheet_path) if emissive_sheet_path else None
            exporter.to_manifest(
                out + "_manifest.json",
                animation_name=name,
                depth_image=depth_image,
                normal_image=normal_image,
                emissive_image=emissive_image,
            )
            return sheet_path
        elif export_format == "gif":
            return exporter.to_gif(out + ".gif")
        elif export_format == "frames_json":
            return exporter.to_frames_json(out + "_frames")
        else:
            raise ValueError(f"Unknown export format: {export_format}")

    def check(self) -> tuple[bool, str]:
        return self._bridge.check_blender()
