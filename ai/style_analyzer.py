"""
Claude Vision API integration for reference sheet style analysis.
Extracts StyleParams from uploaded reference images.
"""
import base64
import json
import os
from dataclasses import dataclass
from typing import Optional

from ai.prompts import STYLE_ANALYSIS_PROMPT, ANIMATION_SUGGEST_PROMPT
from core.renderer import StyleParams


def _image_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _media_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


class StyleAnalyzer:
    MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set. Pass api_key= or set the env var.")
        import anthropic
        self._client = anthropic.Anthropic(api_key=key)

    def analyze_sheet(self, image_path: str) -> StyleParams:
        """Send a reference sheet to Claude Vision and extract StyleParams."""
        b64 = _image_to_b64(image_path)
        mt = _media_type(image_path)

        message = self._client.messages.create(
            model=self.MODEL,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mt,
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": STYLE_ANALYSIS_PROMPT,
                        },
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        return StyleParams(
            pixel_size=int(data.get("pixel_size", 4)),
            width=int(data.get("width", 64)),
            height=int(data.get("height", 64)),
            fps=int(data.get("fps", 12)),
            camera_angle=data.get("camera_angle", "front"),
            palette_hint=data.get("palette_hint"),
            exaggeration=float(data.get("exaggeration", 1.0)),
        )

    def suggest_animations(
        self, image_path: str, animation_names: list[str]
    ) -> dict:
        """Given a reference sheet + library, suggest best matching animations."""
        b64 = _image_to_b64(image_path)
        mt = _media_type(image_path)
        names_str = ", ".join(animation_names[:50])  # cap to avoid token overflow

        prompt = ANIMATION_SUGGEST_PROMPT.format(animation_names=names_str)

        message = self._client.messages.create(
            model=self.MODEL,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mt,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
