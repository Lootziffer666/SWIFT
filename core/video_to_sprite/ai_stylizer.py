"""
AI-backed pixel art stylization.
Pluggable backend: currently supports any img2img API endpoint.
The user already has working consistency via their own models (Image 2.0 / Nano Banana 2).
This module provides the frame context and API plumbing - the model provides the style.
"""
import base64
import os
from dataclasses import dataclass
from typing import Optional, Callable

from PIL import Image


@dataclass
class StylizerConfig:
    api_url: str = ""
    api_key: str = ""
    style_prompt: str = "pixel art sprite, 64x64, flat colors, crisp edges, game sprite"
    negative_prompt: str = "blurry, smooth, photorealistic, 3d render"
    strength: float = 0.6       # img2img denoising strength
    anchor_frame_path: Optional[str] = None   # First frame used as style reference


def _image_to_b64(img: Image.Image) -> str:
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class AiStylizer:
    def __init__(self, config: Optional[StylizerConfig] = None):
        self._cfg = config or StylizerConfig()

    def stylize_frame(
        self,
        frame_path: str,
        out_path: str,
        context_description: Optional[str] = None,
    ) -> str:
        """
        Stylize a single frame. Falls back to pixelizer if no API configured.
        Returns output path.
        """
        if not self._cfg.api_url:
            from core.video_to_sprite.pixelizer import pixelize, PixelizeConfig
            img = Image.open(frame_path).convert("RGBA")
            result = pixelize(img, PixelizeConfig())
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            result.save(out_path)
            return out_path

        return self._call_api(frame_path, out_path, context_description)

    def _call_api(self, frame_path: str, out_path: str, context: Optional[str]) -> str:
        import urllib.request
        import json

        img = Image.open(frame_path).convert("RGB")
        img_b64 = _image_to_b64(img)

        prompt = self._cfg.style_prompt
        if context:
            prompt = f"{prompt}, {context}"

        payload = json.dumps({
            "init_images": [img_b64],
            "prompt": prompt,
            "negative_prompt": self._cfg.negative_prompt,
            "denoising_strength": self._cfg.strength,
            "steps": 20,
            "sampler_name": "DPM++ 2M Karras",
        }).encode()

        req = urllib.request.Request(
            self._cfg.api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._cfg.api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())

        img_data = base64.b64decode(result["images"][0])
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(img_data)
        return out_path

    def stylize_sequence(
        self,
        frame_paths: list[str],
        out_dir: str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> list[str]:
        os.makedirs(out_dir, exist_ok=True)
        out_paths = []
        for i, path in enumerate(frame_paths):
            out_name = f"styled_{i:04d}.png"
            out_path = os.path.join(out_dir, out_name)
            self.stylize_frame(path, out_path)
            out_paths.append(out_path)
            if progress_cb:
                progress_cb(i + 1, len(frame_paths))
        return out_paths
