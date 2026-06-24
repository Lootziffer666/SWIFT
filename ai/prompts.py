"""
Prompt templates for Claude Vision API style analysis.
"""

STYLE_ANALYSIS_PROMPT = """You are an expert in 2D sprite art and character animation.
Analyze this reference sheet and extract the following parameters as JSON.

Return ONLY valid JSON, no explanation:

{
  "pixel_size": <int, 1-16, pixel block size for pixel art, e.g. 4 for 64px sprites>,
  "width": <int, recommended sprite width in pixels, e.g. 32, 48, 64>,
  "height": <int, recommended sprite height in pixels>,
  "fps": <int, recommended animation fps based on movement style, e.g. 8-24>,
  "camera_angle": <string, one of: "front", "side", "three-quarter">,
  "palette_hint": <string, brief color palette description, e.g. "warm, limited 16 colors">,
  "exaggeration": <float, 1.0=normal, >1.0=more squash and stretch, based on style>,
  "notes": <string, brief observation about the animation style>
}

Focus on:
- Body proportions (chibi = big head, short body → small sprite size)
- Movement energy (bouncy/exaggerated vs subtle)
- Dominant viewing angle
- Color style (flat vs shaded, palette size)
"""

ANIMATION_SUGGEST_PROMPT = """You are a sprite animation expert.
Given this reference sheet showing character poses and movements,
list the most suitable animations from this library that match the style:

Available animations: {animation_names}

Return ONLY valid JSON:
{{
  "recommended": [<animation_name>, ...],
  "reason": "<brief explanation>"
}}
"""
