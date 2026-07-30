"""Minimaler glTF-2.0-Leser und -Schreiber fuer das Profil ``spar/1``.

Bewusst ohne externe Bibliothek: das Profil ist eine kleine Teilmenge, und eine
Referenz-Implementierung soll ihren Rechenweg vollstaendig zeigen. Was hier nicht
unterstuetzt wird, ist laut ``spec/gltf-profile.md`` ohnehin unzulaessig -- ein Clip mit
``scale``, ``matrix`` oder ``CUBICSPLINE`` ist kein SPAR-Clip.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import quat
from .rig import Rig

GLB_MAGIC = 0x46546C67  # 'glTF'
CHUNK_JSON = 0x4E4F534A  # 'JSON'
CHUNK_BIN = 0x004E4942  # 'BIN\x00'
COMPONENT_FLOAT = 5126

_TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


class GltfProfileError(Exception):
    """Der Clip verletzt das Profil ``spar/1``."""


@dataclass
class Clip:
    """Ein geladener SPAR-Clip: Skelett plus genau eine Animation."""

    name: str
    fps: int
    frame_count: int
    rig_id: str = "biped/1"
    rotations: dict[str, list[quat.Quat]] = field(default_factory=dict)
    """Bone-Name -> Rotation je Frame."""
    root_translation: list[quat.Vec3] = field(default_factory=list)
    """Visuelle Root-Motion von ``Hips`` je Frame. Leer, wenn nicht animiert."""

    def rotation_at(self, bone: str, frame: int) -> quat.Quat:
        track = self.rotations.get(bone)
        if not track:
            return quat.IDENTITY
        return track[min(frame, len(track) - 1)]

    def root_at(self, frame: int) -> quat.Vec3:
        if not self.root_translation:
            return (0.0, 0.0, 0.0)
        return self.root_translation[min(frame, len(self.root_translation) - 1)]


# ---------------------------------------------------------------- schreiben


def write_clip(path: str | Path, clip: Clip, rig: Rig) -> Path:
    """Schreibt einen Clip als ``.glb`` gemaess Profil ``spar/1``."""
    path = Path(path)
    times = [i / clip.fps for i in range(clip.frame_count)]

    blob = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []

    def push(values: list[float], kind: str) -> int:
        """Haengt Daten an den BIN-Chunk an, gibt den Accessor-Index zurueck."""
        comps = _TYPE_COMPONENTS[kind]
        offset = len(blob)
        blob.extend(struct.pack(f"<{len(values)}f", *values))
        # bufferView-Offsets muessen 4-Byte-aligned sein; float32 garantiert das.
        buffer_views.append(
            {"buffer": 0, "byteOffset": offset, "byteLength": len(blob) - offset}
        )
        count = len(values) // comps
        acc = {
            "bufferView": len(buffer_views) - 1,
            "componentType": COMPONENT_FLOAT,
            "count": count,
            "type": kind,
        }
        if kind == "SCALAR":
            # Vom Standard fuer Sampler-Inputs gefordert.
            acc["min"] = [min(values)]
            acc["max"] = [max(values)]
        accessors.append(acc)
        return len(accessors) - 1

    # Eine gemeinsame Zeitachse fuer alle Kanaele -- das Profil verlangt identische
    # Sampler-Zeiten ueber den ganzen Clip.
    time_acc = push(times, "SCALAR")

    nodes: list[dict] = []
    for bone in rig:
        node: dict = {
            "name": bone.name,
            "translation": list(bone.offset),
            "rotation": list(quat.IDENTITY),
        }
        kids = [rig.index[c] for c in rig.children_of(bone.name)]
        if kids:
            node["children"] = kids
        nodes.append(node)

    samplers: list[dict] = []
    channels: list[dict] = []

    for bone in rig:
        track = clip.rotations.get(bone.name)
        if not track:
            continue
        flat: list[float] = []
        for q in track:
            flat.extend(quat.canonical(q))
        out = push(flat, "VEC4")
        samplers.append({"input": time_acc, "output": out, "interpolation": "STEP"})
        channels.append(
            {
                "sampler": len(samplers) - 1,
                "target": {"node": rig.index[bone.name], "path": "rotation"},
            }
        )

    if clip.root_translation:
        flat = []
        for t in clip.root_translation:
            flat.extend(t)
        out = push(flat, "VEC3")
        samplers.append({"input": time_acc, "output": out, "interpolation": "STEP"})
        channels.append(
            {
                "sampler": len(samplers) - 1,
                "target": {"node": rig.index[rig.root], "path": "translation"},
            }
        )

    doc = {
        "asset": {
            "version": "2.0",
            "generator": "spar/1",
            "extras": {"spar_rig": rig.id},
        },
        "scene": 0,
        "scenes": [{"nodes": [rig.index[rig.root]]}],
        "nodes": nodes,
        "animations": [
            {"name": clip.name, "samplers": samplers, "channels": channels}
        ],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(blob)}],
    }

    _write_glb(path, doc, bytes(blob))
    return path


def _write_glb(path: Path, doc: dict, blob: bytes) -> None:
    json_bytes = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)  # Padding mit Leerzeichen
    bin_bytes = blob + b"\x00" * (-len(blob) % 4)  # Padding mit Nullen

    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(struct.pack("<III", GLB_MAGIC, 2, total))
        f.write(struct.pack("<II", len(json_bytes), CHUNK_JSON))
        f.write(json_bytes)
        f.write(struct.pack("<II", len(bin_bytes), CHUNK_BIN))
        f.write(bin_bytes)


# -------------------------------------------------------------------- lesen


def read_clip(path: str | Path, rig: Rig, animation: str | None = None) -> Clip:
    """Laedt einen ``.glb`` und prueft dabei das Profil ``spar/1``."""
    doc, blob = _read_glb(Path(path))
    _check_profile(doc)

    anims = doc.get("animations") or []
    if not anims:
        raise GltfProfileError("Clip enthaelt keine Animation")
    anim = next((a for a in anims if a.get("name") == animation), anims[0]) if animation else anims[0]

    nodes = doc["nodes"]
    name_of = {i: n.get("name", "") for i, n in enumerate(nodes)}

    rotations: dict[str, list[quat.Quat]] = {}
    root_translation: list[quat.Vec3] = []
    frame_count = 0
    fps: int | None = None

    for ch in anim.get("channels", []):
        sampler = anim["samplers"][ch["sampler"]]
        if sampler.get("interpolation", "LINEAR") not in ("STEP", "LINEAR"):
            raise GltfProfileError(
                f"Interpolation {sampler.get('interpolation')!r} ist im Profil unzulaessig"
            )
        target = ch["target"]
        bone = name_of.get(target["node"], "")
        path_kind = target["path"]

        if path_kind == "scale":
            raise GltfProfileError(
                f"Node {bone!r} hat einen scale-Kanal. Skalierung wuerde Knochenlaengen "
                "animierbar machen und die Kernaussage des Formats brechen."
            )

        times = _read_accessor(doc, blob, sampler["input"], "SCALAR")
        values = _read_accessor(
            doc, blob, sampler["output"], "VEC4" if path_kind == "rotation" else "VEC3"
        )
        frame_count = max(frame_count, len(times))
        if fps is None and len(times) > 1:
            step = times[1][0] - times[0][0]
            if step > 0:
                fps = int(round(1.0 / step))

        if path_kind == "rotation":
            rotations[bone] = [quat.canonical(tuple(v)) for v in values]  # type: ignore[arg-type]
        elif path_kind == "translation":
            if bone != rig.root:
                raise GltfProfileError(
                    f"Node {bone!r} hat einen Translationskanal. Nur {rig.root!r} darf "
                    "translatiert werden (visuelle Root-Motion)."
                )
            root_translation = [tuple(v) for v in values]  # type: ignore[misc]

    missing = rig.missing(set(name_of.values()))
    if missing:
        raise GltfProfileError(
            f"Bones des Rigs {rig.id!r} fehlen im Clip: {', '.join(missing)}"
        )

    declared = (doc.get("asset", {}).get("extras") or {}).get("spar_rig")
    if declared and declared != rig.id:
        raise GltfProfileError(
            f"Clip wurde fuer Rig {declared!r} geschrieben, geladen wurde {rig.id!r}"
        )

    return Clip(
        name=anim.get("name", "unnamed"),
        fps=fps or 60,
        frame_count=frame_count or 1,
        rig_id=rig.id,
        rotations=rotations,
        root_translation=root_translation,
    )


def _check_profile(doc: dict) -> None:
    for i, node in enumerate(doc.get("nodes", [])):
        who = node.get("name", f"#{i}")
        if "matrix" in node:
            raise GltfProfileError(f"Node {who!r} benutzt matrix statt TRS")
        if "scale" in node:
            raise GltfProfileError(f"Node {who!r} hat scale; im Profil unzulaessig")
    if len(doc.get("scenes", [])) > 1:
        raise GltfProfileError("Mehr als eine Szene; genau eine ist zulaessig")
    for bv in doc.get("buffers", []):
        if "uri" in bv:
            raise GltfProfileError("Externe Buffer-URI; alles muss im BIN-Chunk liegen")


def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, version, _total = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise GltfProfileError(f"{path} ist kein .glb")
    if version != 2:
        raise GltfProfileError(f"glTF-Version {version}, erwartet 2")

    doc: dict = {}
    blob = b""
    off = 12
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        payload = data[off + 8 : off + 8 + clen]
        if ctype == CHUNK_JSON:
            doc = json.loads(payload.decode("utf-8"))
        elif ctype == CHUNK_BIN:
            blob = payload
        off += 8 + clen
    return doc, blob


def _read_accessor(doc: dict, blob: bytes, index: int, expect: str) -> list[tuple]:
    acc = doc["accessors"][index]
    if acc["componentType"] != COMPONENT_FLOAT:
        raise GltfProfileError("Nur float32-Accessoren werden unterstuetzt")
    if acc["type"] != expect:
        raise GltfProfileError(f"Accessor {index}: {acc['type']}, erwartet {expect}")
    comps = _TYPE_COMPONENTS[acc["type"]]
    view = doc["bufferViews"][acc["bufferView"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    n = acc["count"] * comps
    flat = struct.unpack_from(f"<{n}f", blob, start)
    return [tuple(flat[i * comps : (i + 1) * comps]) for i in range(acc["count"])]
