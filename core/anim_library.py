"""
Animation library: scans folders for FBX / BVH files and catalogs them
with basic metadata (name, source type, thumbnail path if available).
"""
import os
import json
import hashlib
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


SUPPORTED_EXTENSIONS = {".fbx", ".bvh"}

SOURCE_TYPES = {
    "mixamo": "Mixamo",
    "kenney": "Kenney",
    "unreal": "Unreal Engine",
    "mocap": "Motion Capture",
    "unknown": "Unknown",
}


def _detect_source(path: str) -> str:
    lower = path.lower()
    if "mixamo" in lower:
        return "mixamo"
    if "kenney" in lower:
        return "kenney"
    if "unreal" in lower or "ue4" in lower or "ue5" in lower:
        return "unreal"
    if "mocap" in lower or "capture" in lower:
        return "mocap"
    return "unknown"


def _file_id(path: str) -> str:
    return hashlib.md5(path.encode()).hexdigest()[:12]


@dataclass
class AnimEntry:
    id: str
    name: str
    path: str
    ext: str
    source: str
    thumbnail: Optional[str] = None
    tags: list = field(default_factory=list)

    def display_name(self) -> str:
        return self.name.replace("_", " ").replace("-", " ").title()

    def source_label(self) -> str:
        return SOURCE_TYPES.get(self.source, self.source)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AnimEntry":
        return cls(**d)


class AnimLibrary:
    CACHE_FILENAME = ".swift_anim_cache.json"

    def __init__(self):
        self._entries: dict[str, AnimEntry] = {}
        self._scan_roots: list[str] = []

    def add_folder(self, folder: str, recursive: bool = True):
        """Scan a folder and add all supported animation files."""
        folder = os.path.abspath(folder)
        if not os.path.isdir(folder):
            raise NotADirectoryError(f"Not a directory: {folder}")
        if folder not in self._scan_roots:
            self._scan_roots.append(folder)
        self._scan(folder, recursive)

    def _scan(self, folder: str, recursive: bool):
        pattern = "**/*" if recursive else "*"
        for p in Path(folder).glob(pattern):
            if p.suffix.lower() in SUPPORTED_EXTENSIONS and p.is_file():
                self._add_file(str(p))

    def _add_file(self, path: str):
        entry_id = _file_id(path)
        if entry_id in self._entries:
            return
        entry = AnimEntry(
            id=entry_id,
            name=Path(path).stem,
            path=path,
            ext=Path(path).suffix.lower(),
            source=_detect_source(path),
        )
        self._entries[entry_id] = entry

    def add_file(self, path: str):
        """Add a single animation file."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")
        if Path(path).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported format: {path}")
        self._add_file(path)

    def all(self) -> list[AnimEntry]:
        return list(self._entries.values())

    def search(self, query: str) -> list[AnimEntry]:
        q = query.lower()
        return [e for e in self._entries.values() if q in e.name.lower()]

    def by_source(self, source: str) -> list[AnimEntry]:
        return [e for e in self._entries.values() if e.source == source]

    def get(self, entry_id: str) -> Optional[AnimEntry]:
        return self._entries.get(entry_id)

    def count(self) -> int:
        return len(self._entries)

    def save_cache(self, cache_dir: str):
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, self.CACHE_FILENAME)
        data = {
            "roots": self._scan_roots,
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_cache(self, cache_dir: str) -> bool:
        cache_path = os.path.join(cache_dir, self.CACHE_FILENAME)
        if not os.path.isfile(cache_path):
            return False
        with open(cache_path) as f:
            data = json.load(f)
        self._scan_roots = data.get("roots", [])
        for d in data.get("entries", []):
            e = AnimEntry.from_dict(d)
            self._entries[e.id] = e
        return True
