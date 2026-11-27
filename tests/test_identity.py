"""Định danh project tách khỏi Floola-Next.

Code, giao diện và hướng dẫn không còn định danh cũ (FLOOLA_*, window.floola, Floola*).
Ghi công bản gốc (GPL) chỉ được nằm ở THIRD_PARTY_NOTICES.md, CHANGELOG.md
và mục "## Credits" của README.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = ["static", "electron", "packaging", "tests", "scripts"]
SCAN_ROOT_GLOBS = ["*.py", "*.json", "*.bat", "*.command", "PERSONALIZE.md"]
SUFFIXES = {".py", ".js", ".html", ".css", ".json", ".md", ".spec", ".bat", ".command"}
SKIP_PARTS = {"node_modules", ".venv", "out", "vendor-ffmpeg", "__pycache__"}
SKIP_FILES = {"package-lock.json", "config.json", "test_identity.py", "check.config.json"}

OLD = re.compile(r"floola", re.IGNORECASE)


def _files():
    for d in SCAN_DIRS:
        for p in (ROOT / d).rglob("*"):
            if p.is_file() and p.suffix in SUFFIXES and not (SKIP_PARTS & set(p.parts)):
                yield p
    for pattern in SCAN_ROOT_GLOBS:
        yield from ROOT.glob(pattern)


def test_no_old_identifiers_in_code_or_ui():
    hits = []
    for p in _files():
        if p.name in SKIP_FILES:
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if OLD.search(line):
                hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()[:80]}")
    assert not hits, "\n".join(hits)


def test_readme_mentions_origin_only_in_credits():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    head, _, credits = text.partition("\n## Credits")
    assert credits, "README cần mục ## Credits ghi công bản gốc (GPL)"
    assert not OLD.search(head), "README chỉ nhắc Floola trong mục Credits"
    assert "github.com/k-s-b/floola-next" in credits


def test_package_identity_is_new():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "kl-music-manager"
    assert not OLD.search(pkg["build"]["appId"])
    for key in ("author", "homepage", "repository"):
        assert key in pkg, key
    assert "copyright" in pkg["build"]


def test_original_credit_kept_and_license_verbatim():
    # LICENSE là toàn văn GPLv3 (không được sửa) -> ghi công bản gốc nằm ở NOTICES.
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Floola-Next" in notices and "github.com/k-s-b/floola-next" in notices
    lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert lic.lstrip().startswith("GNU GENERAL PUBLIC LICENSE") and len(lic.splitlines()) == 674
