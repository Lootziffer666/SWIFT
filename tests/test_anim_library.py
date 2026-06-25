"""Tests for AnimLibrary - no Blender needed."""
import os
import tempfile
import pytest
from core.anim_library import AnimLibrary, AnimEntry, _detect_source, _file_id


def _make_fake_fbx(dir_path, name):
    p = os.path.join(dir_path, name)
    with open(p, "w") as f:
        f.write("FBX stub")
    return p


class TestDetectSource:
    def test_mixamo(self):
        assert _detect_source("/animations/mixamo/walk.fbx") == "mixamo"

    def test_kenney(self):
        assert _detect_source("/kenney_assets/run.fbx") == "kenney"

    def test_unreal(self):
        assert _detect_source("/unreal_project/Anims/jump.fbx") == "unreal"

    def test_unknown(self):
        assert _detect_source("/some/random/path/spin.fbx") == "unknown"


class TestAnimLibrary:
    def test_add_folder_finds_fbx(self, tmp_path):
        _make_fake_fbx(str(tmp_path), "walk.fbx")
        _make_fake_fbx(str(tmp_path), "run.fbx")
        lib = AnimLibrary()
        lib.add_folder(str(tmp_path))
        assert lib.count() == 2

    def test_add_folder_ignores_non_fbx(self, tmp_path):
        open(tmp_path / "image.png", "w").close()
        open(tmp_path / "readme.txt", "w").close()
        lib = AnimLibrary()
        lib.add_folder(str(tmp_path))
        assert lib.count() == 0

    def test_add_bvh(self, tmp_path):
        p = tmp_path / "mocap.bvh"
        p.write_text("BVH stub")
        lib = AnimLibrary()
        lib.add_folder(str(tmp_path))
        assert lib.count() == 1
        entry = lib.all()[0]
        assert entry.ext == ".bvh"

    def test_search(self, tmp_path):
        _make_fake_fbx(str(tmp_path), "walk_forward.fbx")
        _make_fake_fbx(str(tmp_path), "jump_high.fbx")
        lib = AnimLibrary()
        lib.add_folder(str(tmp_path))
        results = lib.search("walk")
        assert len(results) == 1
        assert results[0].name == "walk_forward"

    def test_no_duplicates_on_double_scan(self, tmp_path):
        _make_fake_fbx(str(tmp_path), "walk.fbx")
        lib = AnimLibrary()
        lib.add_folder(str(tmp_path))
        lib.add_folder(str(tmp_path))
        assert lib.count() == 1

    def test_cache_roundtrip(self, tmp_path):
        anim_dir = tmp_path / "anims"
        anim_dir.mkdir()
        _make_fake_fbx(str(anim_dir), "run.fbx")
        lib = AnimLibrary()
        lib.add_folder(str(anim_dir))
        lib.save_cache(str(tmp_path))

        lib2 = AnimLibrary()
        assert lib2.load_cache(str(tmp_path))
        assert lib2.count() == 1
        assert lib2.all()[0].name == "run"

    def test_display_name(self, tmp_path):
        _make_fake_fbx(str(tmp_path), "walk_cycle_v2.fbx")
        lib = AnimLibrary()
        lib.add_folder(str(tmp_path))
        entry = lib.all()[0]
        assert entry.display_name() == "Walk Cycle V2"

    def test_add_single_file(self, tmp_path):
        p = _make_fake_fbx(str(tmp_path), "spin.fbx")
        lib = AnimLibrary()
        lib.add_file(p)
        assert lib.count() == 1

    def test_add_unsupported_file_raises(self, tmp_path):
        p = tmp_path / "image.png"
        p.write_text("not an anim")
        lib = AnimLibrary()
        with pytest.raises(ValueError):
            lib.add_file(str(p))

    def test_recursive_scan(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        _make_fake_fbx(str(subdir), "nested.fbx")
        lib = AnimLibrary()
        lib.add_folder(str(tmp_path), recursive=True)
        assert lib.count() == 1
