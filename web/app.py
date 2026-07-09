import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
REPO = BASE.parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

app = FastAPI(title="SWIFT Web Demo")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

_sample_manifest = None


def _make_sample():
    global _sample_manifest
    fw, fh = 96, 96
    cols = 8
    sheet = Image.new("RGBA", (fw * cols, fh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    for i in range(cols):
        x = i * fw
        t = i / (cols - 1)
        cy = int(fh / 2 - (fh / 2 - 14) * math.sin(t * math.pi))
        cx = int(fw / 2)
        draw.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=(230, 90, 60, 255))
        draw.rectangle([4, fh - 10, int(fw - 4 - (fw - 8) * t), fh - 6], fill=(90, 160, 230, 220))
    sheet_path = DATA / "sample.png"
    sheet.save(sheet_path, "PNG")
    _sample_manifest = {
        "mappingVersion": "1.4.0",
        "sourceImage": {"w": fw * cols, "h": fh},
        "frameRects": {f"f{i}": [i * fw, 0, fw, fh] for i in range(cols)},
        "frames": [f"f{i}" for i in range(cols)],
        "animations": {
            "bounce": {"frames": [f"f{i}" for i in range(cols)], "fps": 10}
        },
    }
    return _sample_manifest


@app.get("/")
def index():
    return FileResponse(str(BASE / "static" / "index.html"))


@app.get("/api/sample")
def api_sample():
    return {"sheet": "/api/sheet/sample.png", "manifest": _make_sample()}


@app.get("/api/sheet/{name}")
def api_sheet(name: str):
    path = DATA / name
    if not path.exists() or not path.is_file():
        return JSONResponse({"error": "sheet not found"}, status_code=404)
    return FileResponse(str(path))


@app.post("/api/upload")
async def api_upload(sheet: UploadFile = File(...), manifest: UploadFile = File(...)):
    content = await sheet.read()
    try:
        manifest_data = json.loads(await manifest.read())
    except Exception:
        return JSONResponse({"error": "invalid manifest JSON"}, status_code=400)
    uid = uuid.uuid4().hex
    sheet_path = DATA / f"{uid}.png"
    sheet_path.write_bytes(content)
    return {"sheet": f"/api/sheet/{uid}.png", "manifest": manifest_data}


@app.post("/api/render")
async def api_render(
    fbx: UploadFile = File(...),
    anim: UploadFile = File(None),
    width: int = Form(64),
    height: int = Form(64),
    fps: int = Form(12),
    pixel_size: int = Form(4),
    camera: str = Form("front"),
):
    tmp = Path(tempfile.mkdtemp())
    fbx_path = tmp / "model.fbx"
    fbx_path.write_bytes(await fbx.read())
    anim_path = None
    if anim:
        anim_path = tmp / "anim.fbx"
        anim_path.write_bytes(await anim.read())
    out = tmp / "out.png"
    cmd = [
        sys.executable,
        str(REPO / "main.py"),
        "render",
        "--model",
        str(fbx_path),
        "--output",
        str(out),
        "--width",
        str(width),
        "--height",
        str(height),
        "--fps",
        str(fps),
        "--pixel-size",
        str(pixel_size),
        "--camera",
        camera,
    ]
    if anim_path:
        cmd += ["--anim", str(anim_path)]
    try:
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "render timed out (600s)"}, status_code=504)
    if proc.returncode != 0:
        return JSONResponse(
            {"error": "render failed", "detail": (proc.stderr or proc.stdout)[-2000:]},
            status_code=500,
        )
    if not out.exists():
        return JSONResponse(
            {"error": "no output produced", "detail": proc.stdout[-2000:]},
            status_code=500,
        )
    uid = uuid.uuid4().hex
    final = DATA / f"{uid}.png"
    shutil.copy(out, final)
    manifest_path = out.with_name("out_manifest.json")
    manifest_data = None
    if manifest_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text())
        except Exception:
            manifest_data = None
    return {"sheet": f"/api/sheet/{uid}.png", "manifest": manifest_data}
