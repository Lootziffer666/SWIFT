# SWIFT ↔ LAB

`integrations/lab_adapter.py` turns one LAB actor job into SWIFT's existing machine-readable CLI. It supports:

- video → `video2sprite` with smart crop, auto scale and manifest;
- model → `render` with optional depth pass and SHADED world-state variants;
- existing sheet → `spritesheet list` validation.

The adapter deliberately reports background removal and feet-baseline normalization as unsupported until those capabilities exist in SWIFT. The uploaded Vid2Sheet launcher names those operations but does not contain the three implementation files, so LAB must not advertise them as working.

```bash
python integrations/lab_adapter.py actor.request.json --dry-run
python integrations/lab_adapter.py actor.request.json
```
