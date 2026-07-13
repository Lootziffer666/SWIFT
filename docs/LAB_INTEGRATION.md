# SWIFT ↔ LAB

`integrations/lab_adapter.py` turns one LAB actor job into SWIFT's existing machine-readable CLI. It supports:

- video → `video2sprite` with smart crop, auto scale and manifest;
- model → `render` with optional depth pass and SHADED world-state variants;
- existing sheet → `spritesheet list` validation;
- local background removal after sheet generation.

## Provenance correction

The inspected `launcher.py` and installer behavior came from the third-party `Vid2Sheet-main.zip`. They are not authored by the owner of SWIFT/LAB. LAB uses them only as reference material and does not copy or rebrand that launcher.

The LAB adapter's background-removal implementation is its own explicit integration layer and must be judged by its code and tests, not by ownership of the Vid2Sheet source package.

## Background removal

`options.backgroundRemoval` accepts four modes:

| Mode | Dependency | Behavior |
|---|---|---|
| `none` | none | Keep the generated alpha/background unchanged. |
| `connected` | Pillow | Fast border-connected flood removal. |
| `color-key` | Pillow | Fast removal of every pixel matching the key color/tolerance. |
| `ai` | optional `rembg` + `onnxruntime` | Local ONNX segmentation. No image is uploaded. The selected model downloads automatically on first use. |

If the optional AI add-on was skipped, install it later in the active environment:

```powershell
.venv\Scripts\python.exe -m pip install rembg onnxruntime
```

Background removal is applied per manifest frame rather than to the atlas as one picture. The transparent result is written as `<sheet>_transparent.png`; the original SWIFT sheet remains unchanged.

## BELLOWS boundary

ONNX remains a local image runtime and is not replaced by BELLOWS. Any LLM/provider call used for semantic interpretation, prompt expansion, asset selection or uncertain classification must go through the `aiGateway` supplied by LAB. The current actor adapter itself is deterministic and therefore makes no provider call.

Feet/baseline normalization exists as a standalone scaler capability, but no machine-readable scaler contract was present in the inspected package. LAB marks only that wiring step as `needs_human_review`; it does not claim the capability is absent.

```bash
python integrations/lab_adapter.py actor.request.json --dry-run
python integrations/lab_adapter.py actor.request.json
```
