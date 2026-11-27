"""Phiên bản: một nguồn (version.py) và phải khớp package.json (bộ cài Electron)."""

import json
from pathlib import Path

import version

ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_package_json():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert version.VERSION == pkg["version"]
    assert version.APP_NAME == pkg["productName"]


def test_version_format():
    parts = version.VERSION.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


def test_author_and_homepage_match_package_json():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert version.AUTHOR == pkg["author"]
    assert version.HOMEPAGE == pkg["homepage"]
