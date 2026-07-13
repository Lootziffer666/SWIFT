# SWIFT ↔ LAB

`integrations/lab_adapter.py` turns one LAB actor job into SWIFT's existing machine-readable CLI. It supports:

- video → `video2sprite` with smart crop, auto scale and manifest;
- model → `render` with optional depth pass and SHADED world-state variants;
- existing sheet → `spritesheet list` validation;
- local background removal after sheet generation.

## Background removal

`options.backgroundRemoval` accepts four modes:

| Mode | Dependency | Behavior |
|---|---|---|
| `none` | none | Keep the generated alpha/background unchanged. |
| `connected` | Pillow (already used by SWIFT) | Fast border-connected flood removal. |
| `color-key` | Pillow | Fast removal of every pixel matching the key color/tolerance. |
| `ai` | optional `rembg` + `onnxruntime` | Local ONNX segmentation. No image is uploaded. The selected rembg model downloads automatically on first use. |

The installer may offer the AI add-on as a yes/no choice. If it was skipped, install it later in the active environment:

```powershell
.venv\Scripts\python.exe -m pip install rembg onnxruntime
```

The LAB adapter does not treat a skipped AI add-on as a missing product capability. When `ai` is requested without the optional packages, it returns `status: needs_installation`, exit code `3`, and a local install command. Connected and Color Key remain available without ONNX.

Background removal is applied per manifest frame rather than to the atlas as one picture. This prevents one pose from influencing the mask of a neighboring pose. The transparent result is written as `<sheet>_transparent.png`; the original SWIFT sheet remains unchanged.

Feet/baseline normalization is exposed by the standalone Sprite Sheet Scaler, but the uploaded launcher does not define a machine-readable CLI for it. LAB therefore marks only that requested step as `needs_human_review`; it does not claim the capability is absent.

```bash
python integrations/lab_adapter.py actor.request.json --dry-run
python integrations/lab_adapter.py actor.request.json
```

Example options:

```json
{
  "backgroundRemoval": "ai",
  "rembgModel": "u2net",
  "backgroundTolerance": 24,
  "strictCapabilities": true
}
```
