#!/usr/bin/env python3
"""
SWIFT→SHADED Manifest Schema Compatibility Check
Verifies that generated manifests match v1.4.0 specification and can be consumed by SHADED.
"""
import json
import sys
from pathlib import Path

def check_manifest(manifest_path: str) -> bool:
    """Check if manifest conforms to v1.4.0 schema."""
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"❌ Cannot read manifest: {e}")
        return False

    version = manifest.get('mappingVersion', 'unknown')
    if version not in ['1.3.0', '1.4.0']:
        print(f"⚠️ Manifest version {version} (expected 1.3.0 or 1.4.0)")

    # v1.4.0+ required fields
    required_fields = ['sourceImage', 'frameRects', 'frames', 'animations']
    missing = [f for f in required_fields if f not in manifest]
    if missing:
        print(f"❌ Missing required fields: {missing}")
        return False

    # Validate sourceImage
    source = manifest.get('sourceImage', {})
    if not isinstance(source, dict) or 'w' not in source or 'h' not in source:
        print(f"❌ Invalid sourceImage: must have w, h")
        return False

    # Validate frameRects (dict of [x,y,w,h])
    frame_rects = manifest.get('frameRects', {})
    if not isinstance(frame_rects, dict):
        print(f"❌ frameRects must be a dict")
        return False
    for fid, rect in frame_rects.items():
        if not isinstance(rect, (list, dict)) or len(rect) < 4:
            print(f"❌ Invalid rect for {fid}: {rect}")
            return False

    # Validate animations
    animations = manifest.get('animations', {})
    if not isinstance(animations, dict):
        print(f"❌ animations must be a dict")
        return False
    for anim_name, anim in animations.items():
        if 'frames' not in anim or 'fps' not in anim:
            print(f"❌ Animation {anim_name} missing frames or fps")
            return False

    # v1.4.0 optional fields
    if 'depthImage' in manifest:
        print(f"✓ Depth image: {manifest['depthImage']}")
    if 'depthFrameRects' in manifest:
        depth_rects = manifest.get('depthFrameRects', {})
        if len(depth_rects) != len(frame_rects):
            print(f"⚠️ Depth frame count mismatch: {len(depth_rects)} vs {len(frame_rects)}")

    print(f"✓ Manifest v{version} schema valid")
    print(f"  - Frames: {len(frame_rects)}")
    print(f"  - Animations: {len(animations)}")
    if 'variants' in manifest:
        print(f"  - Variants: {len(manifest['variants'])}")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python check-manifest-schema.py <manifest.json>")
        sys.exit(1)

    manifest_path = sys.argv[1]
    ok = check_manifest(manifest_path)
    sys.exit(0 if ok else 1)
