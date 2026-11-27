"""Kiểm tra toàn bộ project: lint + format + type + build + test.

Exit 0 = pass. Đây là định nghĩa "xong" của project.

    python scripts/check.py              # chạy theo cấu hình, output gọn
    python scripts/check.py --failed     # chỉ chạy lại các bước fail lần trước (khi đang sửa)
    python scripts/check.py --only rust-test,cpp-tidy   # chỉ chạy bước chỉ định
    python scripts/check.py --all        # lint toàn bộ file, bỏ qua lint_scope
    python scripts/check.py --list       # in các bước sẽ chạy, không chạy
    python scripts/check.py -v           # in toàn bộ output công cụ (cho người đọc)

Tiết kiệm token (mặc định):
- Bước PASS chỉ in 1 dòng. Bước FAIL chỉ in các dòng lỗi (tối đa output_lines dòng),
  bỏ trùng lặp, bỏ mã màu, rút gọn đường dẫn tuyệt đối. Log đầy đủ ghi vào .check/<bước>.log.
- Công cụ được gọi ở chế độ output ngắn: ruff concise, pytest --tb=short, clippy short,
  rustfmt chỉ liệt kê file, dotnet không in summary trùng lặp.
- --failed / --only: chạy lại đúng bước đang sửa (tự kèm bước configure/build cần thiết).
  Kết quả cuối cùng PHẢI là một lần chạy đầy đủ không có --failed/--only.

Cấu hình (tùy chọn): scripts/check.config.json
{
  "lint_scope": "all" | "changed",   # changed = chỉ lint/format file đã đổi so với base_ref
  "base_ref": "origin/main",         # mặc định: tự tìm origin/main, main, master
  "output_lines": 40,                # số dòng tối đa in ra cho mỗi bước fail
  "dotnet_target": "src/App.sln",    # khi có nhiều .sln
  "dotnet_warnaserror": false,
  "rust_deny_warnings": true,        # clippy -D warnings (repo cũ nhiều warning: false)
  "cmake_build_dir": "build",        # thư mục build C++
  "cmake_build_type": "Debug",
  "cmake_preset": "dev",             # dùng CMakePresets.json thay vì -S/-B
  "cmake_args": ["-DENABLE_SANITIZERS=ON"],
  "cpp_exclude": ["third_party/"],   # thư mục không format/tidy (code vendored)
  "skip": ["py-type", "cpp-tidy"],   # bỏ bước theo tên
  "steps": [ {"name": "...", "cmd": ["..."]} ],        # có -> THAY toàn bộ tự nhận diện
  "extra_steps": [ {"name": "smoke", "cmd": ["..."]} ] # chạy thêm sau tự nhận diện
}
Mã thoát: 0 pass, 1 fail, 3 không có bước nào chạy (unresolved).
"""

from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except AttributeError:
        pass

CONFIG: dict = {}
cfg_file = ROOT / "scripts" / "check.config.json"
if cfg_file.exists():
    CONFIG = json.loads(cfg_file.read_text(encoding="utf-8"))


def _arg_value(flag: str) -> str | None:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    for a in sys.argv:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return None


ARGS = set(sys.argv[1:])
VERBOSE = "-v" in ARGS or "--verbose" in ARGS
LINT_SCOPE = "all" if "--all" in ARGS else CONFIG.get("lint_scope", "all")
SKIP = set(CONFIG.get("skip", []))
MAX_LINES = int(CONFIG.get("output_lines", 40))
LOG_DIR = ROOT / ".check"
STATE_FILE = LOG_DIR / "last.json"

# Môi trường cho công cụ con: tắt màu, tắt logo/telemetry, ép thông báo tiếng Anh để lọc lỗi.
TOOL_ENV = {
    **os.environ,
    "NO_COLOR": "1",
    "CLICOLOR": "0",
    "CARGO_TERM_COLOR": "never",
    "DOTNET_NOLOGO": "1",
    "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
    "DOTNET_CLI_UI_LANGUAGE": "en",
    "PYTHONIOENCODING": "utf-8",
    "RUST_BACKTRACE": "0",  # backtrace dài, hiếm khi cần để sửa test
}


# ---------------------------------------------------------------- tiện ích
def which(name: str) -> str | None:
    return shutil.which(name)


def git(*args: str) -> str:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
        return r.stdout.strip() if r.returncode == 0 else ""
    except OSError:
        return ""


_changed_cache: list[str] | None = None


def changed_files() -> list[str]:
    """File đã thêm/sửa so với base_ref, cộng file chưa commit và chưa track."""
    global _changed_cache
    if _changed_cache is not None:
        return _changed_cache
    base = CONFIG.get("base_ref")
    if not base:
        for ref in ("origin/main", "origin/master", "main", "master"):
            if git("rev-parse", "--verify", "--quiet", ref):
                base = ref
                break
    files: set[str] = set()
    if base:
        mb = git("merge-base", "HEAD", base) or base
        files.update(git("diff", "--name-only", "--diff-filter=ACMR", mb).splitlines())
    files.update(git("diff", "--name-only", "--diff-filter=ACMR", "HEAD").splitlines())
    files.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    _changed_cache = sorted(f for f in files if f and Path(f).is_file())
    return _changed_cache


def python_exe() -> str:
    """Ưu tiên Python trong .venv của project."""
    for p in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return sys.executable


def has_module(py: str, mod: str) -> bool:
    if py == sys.executable:
        return importlib.util.find_spec(mod) is not None
    r = subprocess.run([py, "-c", f"import {mod}"], capture_output=True)
    return r.returncode == 0


# ---------------------------------------------------------------- Python
def python_steps() -> list[dict]:
    if not any((ROOT / f).exists() for f in ("pyproject.toml", "requirements.txt", "setup.py")):
        return []
    py = python_exe()
    steps: list[dict] = []
    if LINT_SCOPE == "changed":
        targets = [f for f in changed_files() if f.endswith((".py", ".pyi"))]
        note = f"{len(targets)} file đã đổi"
    else:
        targets, note = ["."], ""
    ruff = (
        [py, "-m", "ruff"] if has_module(py, "ruff") else ([which("ruff")] if which("ruff") else [])
    )
    if ruff:
        if targets:
            lint = [*ruff, "check", *targets]
            check_help = subprocess.run([*ruff, "check", "--help"], capture_output=True, text=True)
            if "concise" in check_help.stdout:  # ruff < 0.2 không có định dạng concise
                lint.insert(len(ruff) + 1, "--output-format=concise")
            steps.append({"name": "py-lint", "cmd": lint, "note": note, "fix": "ruff check --fix"})
            fmt = [*ruff, "format", "--check", *targets]
            # ruff mới in cả diff khi --check; concise = 1 dòng/file. Bản cũ không có tùy chọn này.
            help_text = subprocess.run([*ruff, "format", "--help"], capture_output=True, text=True)
            if "--output-format" in help_text.stdout:
                fmt.insert(len(ruff) + 2, "--output-format=concise")
            steps.append(
                {
                    "name": "py-format",
                    "cmd": fmt,
                    "note": note,
                    "summarize": "files",
                    "fix": "ruff format",
                }
            )
    else:
        print("  (bỏ qua py-lint/py-format: chưa cài ruff — pip install ruff)")
    if has_module(py, "mypy") and list((ROOT / "src").rglob("*.py")):
        mypy = [py, "-m", "mypy", "src", "--no-pretty", "--no-error-summary"]
        steps.append({"name": "py-type", "cmd": mypy})
    tests = [
        p
        for pat in ("test_*.py", "*_test.py")
        for p in ROOT.rglob(pat)
        if ".venv" not in p.parts and "node_modules" not in p.parts
    ]
    if tests:
        if has_module(py, "pytest"):
            pytest = [py, "-m", "pytest", "-q", "--no-header", "--color=no"]
            pytest += ["--tb=short", "-rfE"] if not VERBOSE else []
            steps.append({"name": "py-test", "cmd": pytest, "summarize": "pytest"})
        else:
            print("  (bỏ qua py-test: có file test nhưng chưa cài pytest)")
    return steps


# ---------------------------------------------------------------- .NET
def dotnet_target() -> str | None:
    if CONFIG.get("dotnet_target"):
        return CONFIG["dotnet_target"]
    for pattern in ("*.sln", "*.slnx", "*.csproj", "src/*.sln", "src/*.slnx"):
        found = sorted(glob.glob(pattern))
        if found:
            if len(found) > 1:
                print(f"  (nhiều {pattern}: dùng {found[0]}; sai thì đặt dotnet_target)")
            return found[0]
    return None


def dotnet_steps() -> list[dict]:
    target = dotnet_target()
    if not target:
        return []
    if not which("dotnet"):
        print("  (bỏ qua .NET: không tìm thấy lệnh dotnet)")
        return []
    steps: list[dict] = []
    fmt = ["dotnet", "format", target, "--verify-no-changes"]
    if LINT_SCOPE == "changed":
        cs = [f for f in changed_files() if f.endswith(".cs")]
        if cs:
            steps.append(
                {
                    "name": "dotnet-format",
                    "cmd": [*fmt, "--include", *cs],
                    "note": f"{len(cs)} file đã đổi",
                    "summarize": "files",
                    "fix": "dotnet format " + target,
                }
            )
    else:
        steps.append(
            {
                "name": "dotnet-format",
                "cmd": fmt,
                "summarize": "files",
                "fix": "dotnet format " + target,
            }
        )
    # NoSummary: không in lại toàn bộ lỗi lần thứ hai ở cuối
    build = ["dotnet", "build", target, "--nologo", "-v", "q", "-clp:NoSummary"]
    if CONFIG.get("dotnet_warnaserror"):
        build.append("-warnaserror")
    steps.append({"name": "dotnet-build", "cmd": build, "gate": True})
    test = ["dotnet", "test", target, "--nologo", "--no-build", "-v", "q"]
    test += ["--logger", "console;verbosity=minimal"]
    steps.append({"name": "dotnet-test", "cmd": test})
    return steps


# ---------------------------------------------------------------- Rust
def rust_edition() -> str:
    """Edition trong Cargo.toml (kể cả [workspace.package]); mặc định 2021."""
    text = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    m = re.search(r'^\s*edition\s*=\s*"(\d{4})"', text, re.M)
    return m.group(1) if m else "2021"


def rust_steps() -> list[dict]:
    if not (ROOT / "Cargo.toml").exists():
        return []
    if not which("cargo"):
        print("  (bỏ qua Rust: không tìm thấy cargo — cài qua https://rustup.rs)")
        return []
    steps: list[dict] = []
    if which("rustfmt"):
        # -l: chỉ liệt kê file sai format thay vì in cả diff
        if LINT_SCOPE == "changed":
            rs = [f for f in changed_files() if f.endswith(".rs")]
            if rs:
                cmd = ["rustfmt", "--check", "-l", "--edition", rust_edition(), *rs]
                note = f"{len(rs)} file đã đổi"
                steps.append({"name": "rust-fmt", "cmd": cmd, "note": note, "fix": "cargo fmt"})
        else:
            cmd = ["cargo", "fmt", "--all", "--", "--check", "-l"]
            steps.append({"name": "rust-fmt", "cmd": cmd, "fix": "cargo fmt --all"})
    else:
        print("  (bỏ qua rust-fmt: rustup component add rustfmt)")
    short = [] if VERBOSE else ["--message-format=short"]
    if which("cargo-clippy"):
        clippy = ["cargo", "clippy", "--workspace", "--all-targets", "--quiet", *short]
        if CONFIG.get("rust_deny_warnings", True):
            clippy += ["--", "-D", "warnings"]
        # Chỉ SKIP test khi có lỗi compile (error[E...]); fail vì lint thì test vẫn chạy
        steps.append({"name": "rust-clippy", "cmd": clippy, "gate_if": r"error\[E\d+\]"})
    else:
        print("  (bỏ qua rust-clippy: rustup component add clippy)")
        build = ["cargo", "build", "--workspace", "--quiet", *short]
        steps.append({"name": "rust-build", "cmd": build, "gate": True})
    test = ["cargo", "test", "--workspace", "--quiet"]
    steps.append({"name": "rust-test", "cmd": test, "summarize": "cargo-test"})
    return steps


# ---------------------------------------------------------------- C++
CPP_EXT = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".ipp")
CPP_SRC_EXT = (".c", ".cc", ".cpp", ".cxx")


def cpp_build_dir() -> Path:
    return ROOT / CONFIG.get("cmake_build_dir", "build")


def cpp_excluded(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    build = CONFIG.get("cmake_build_dir", "build").rstrip("/") + "/"
    prefixes = [build, "cmake-build-", "out/", *CONFIG.get("cpp_exclude", ["third_party/"])]
    return any(rel.startswith(p) for p in prefixes)


def cpp_files(ext: tuple[str, ...]) -> list[str]:
    if LINT_SCOPE == "changed":
        files = changed_files()
    else:
        files = git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
        if not files:  # chưa phải git repo
            files = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()]
    return sorted(f for f in files if f.lower().endswith(ext) and not cpp_excluded(f))


def cpp_tidy_cmd() -> list[str] | None:
    """Quyết định lúc chạy (sau configure) vì cần compile_commands.json."""
    db = cpp_build_dir() / "compile_commands.json"
    if not db.exists():
        print("    (không có compile_commands.json: generator Visual Studio không sinh file này.")
        print('     Dùng Ninja, hoặc đặt "skip": ["cpp-tidy"] trong check.config.json)')
        return None
    in_db = set()
    for entry in json.loads(db.read_text(encoding="utf-8")):
        p = Path(entry["directory"], entry["file"]).resolve()
        try:
            in_db.add(p.relative_to(ROOT).as_posix())
        except ValueError:
            continue  # file ngoài project (thư viện FetchContent...)
    files = [f for f in cpp_files(CPP_SRC_EXT) if f in in_db]
    if not files:
        print("    (không có file .cpp nào cần kiểm tra)")
        return None
    return ["clang-tidy", "-p", str(cpp_build_dir()), "--quiet", *files]


def cpp_steps() -> list[dict]:
    if not (ROOT / "CMakeLists.txt").exists():
        return []
    if not which("cmake"):
        print("  (bỏ qua C++: không tìm thấy cmake)")
        return []
    bdir = str(cpp_build_dir())
    btype = CONFIG.get("cmake_build_type", "Debug")
    preset = CONFIG.get("cmake_preset")
    steps: list[dict] = []

    if preset:
        configure = ["cmake", "--preset", preset]
        build = ["cmake", "--build", "--preset", preset]
        test = {"name": "cpp-test", "cmd": ["ctest", "--preset", preset, "--output-on-failure"]}
    else:
        configure = ["cmake", "-S", ".", "-B", bdir, f"-DCMAKE_BUILD_TYPE={btype}"]
        configure.append("-DCMAKE_EXPORT_COMPILE_COMMANDS=ON")
        # Chỉ chọn generator khi chưa configure, tránh lỗi "generator does not match"
        if which("ninja") and not (cpp_build_dir() / "CMakeCache.txt").exists():
            configure += ["-G", "Ninja"]
        build = ["cmake", "--build", bdir, "--config", btype, "--parallel"]
        test = {
            "name": "cpp-test",
            "cmd": ["ctest", "-C", btype, "--output-on-failure"],
            "cwd": bdir,
        }
    configure += CONFIG.get("cmake_args", [])

    steps.append({"name": "cpp-configure", "cmd": configure, "gate": True})
    if (ROOT / ".clang-format").exists():
        if which("clang-format"):
            files = cpp_files(CPP_EXT)
            if files:
                note = f"{len(files)} file" + (" đã đổi" if LINT_SCOPE == "changed" else "")
                cmd = ["clang-format", "--dry-run", "--Werror", *files]
                steps.append(
                    {
                        "name": "cpp-format",
                        "cmd": cmd,
                        "note": note,
                        "summarize": "files",
                        "fix": "clang-format -i <các file trên>",
                    }
                )
        else:
            print("  (bỏ qua cpp-format: có .clang-format nhưng chưa cài clang-format)")
    steps.append({"name": "cpp-build", "cmd": build, "gate": True})
    if (ROOT / ".clang-tidy").exists():
        if which("clang-tidy"):
            steps.append({"name": "cpp-tidy", "lazy": cpp_tidy_cmd})
        else:
            print("  (bỏ qua cpp-tidy: có .clang-tidy nhưng chưa cài clang-tidy)")
    steps.append(test)
    return steps


# ---------------------------------------------------------------- Node / Go
def node_steps() -> list[dict]:
    pkg = ROOT / "package.json"
    if not pkg.exists():
        return []
    if (ROOT / "pnpm-lock.yaml").exists():
        pm = "pnpm"
    elif (ROOT / "yarn.lock").exists():
        pm = "yarn"
    else:
        pm = "npm"
    exe = which(pm)
    if not exe:
        return []
    scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
    return [
        {"name": f"js-{s}", "cmd": [exe, "run", s]}
        for s in ("lint", "typecheck", "test", "build")
        if s in scripts
    ]


def go_steps() -> list[dict]:
    if not (ROOT / "go.mod").exists() or not which("go"):
        return []
    return [
        {"name": "go-vet", "cmd": ["go", "vet", "./..."], "gate": True},
        {"name": "go-test", "cmd": ["go", "test", "./..."]},
    ]


# ---------------------------------------------------------------- rút gọn output
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# Dòng đáng giữ khi bước fail: chẩn đoán dạng file:dòng, lỗi, test fail, panic, traceback...
KEEP = re.compile(
    r"^\S[^:\s]*\.\w+[:(]\d+"  # file.ext:12: / file.ext(12,5): (gcc, clang, mypy, ruff, msbuild)
    r"|\berror\b|\bfailed\b|\bfailure|\bfatal\b|panicked|assert|traceback|exception"
    r"|^E\s|would reformat|^diff in|^FAIL|^---- |^thread '|undefined reference"
    r"|^\s*-->\s",  # vị trí lỗi của rustc
    re.IGNORECASE,
)
# Dòng nhiễu dù có chứa chữ "error"/"failed"
NOISE = re.compile(
    r"^\s*\d+ (error|warning)s? generated|^ninja: build stopped|^Build FAILED\.?$"
    r"|^\s*(Time Elapsed|\d+ Warning\(s\)|\d+ Error\(s\))|^error: could not compile"
    r"|^\s*\|\s*$|^\s*= (note|help):|:\s*note:|^\s*note:",
    re.IGNORECASE,
)
ABS = re.compile(r"^\s*(/|[A-Za-z]:[\\/])")  # đường dẫn tuyệt đối = ngoài project (header hệ thống)
SYS_CHAIN = re.compile(r"required from|in instantiation of|in file included from", re.IGNORECASE)
# Tách "vị trí" và "nội dung" của một dòng chẩn đoán để gộp lỗi giống nhau
LOC = re.compile(
    r"^(?P<loc>[^\s:(][^:(]*?\.\w+(?::\d+){1,2}|[^\s(][^(]*?\.\w+\(\d+,\d+\)):\s*(?P<msg>.+)$"
)
FILE_OF = re.compile(r"^(.+?)(?::\d+:\d+:|\(\d+,\d+\):)")
WOULD_REFORMAT = re.compile(r"^Would reformat:\s*(.+)$")
PYTEST_BLOCK = re.compile(r"^_{3,} .+ _{3,}$")


def shorten_paths(text: str) -> str:
    for prefix in {str(ROOT) + os.sep, ROOT.as_posix() + "/", str(ROOT) + "/"}:
        text = text.replace(prefix, "")
    return text


def clip(ln: str, n: int = 240) -> str:
    return ln if len(ln) <= n else ln[:n] + " …"


def group_diagnostics(lines: list[str]) -> list[str]:
    """Gộp các dòng cùng nội dung lỗi ở nhiều vị trí: in 1 lần kèm danh sách vị trí."""
    order: list[str] = []
    groups: dict[str, list[str]] = {}
    first_line: dict[str, str] = {}
    counts: dict[str, int] = {}
    for ln in lines:
        m = LOC.match(ln.strip())
        key = m.group("msg") if m else ln.strip()
        if key not in groups:
            order.append(key)
            groups[key] = []
            first_line[key] = ln
        if m:
            groups[key].append(m.group("loc"))
            counts[key] = counts.get(key, 0) + 1
    out = []
    for key in order:
        locs = list(dict.fromkeys(groups[key]))  # bỏ vị trí trùng, giữ thứ tự
        ln = clip(first_line[key])
        if counts.get(key, 0) > 1:
            others = locs[1:5]
            more = ", ".join(others) + (f", +{len(locs) - 5}" if len(locs) > 5 else "")
            ln += f"   [x{counts[key]}" + (f": {more}]" if others else "]")
        out.append(ln)
    return out


def summarize_pytest(lines: list[str], limit: int) -> list[str]:
    """Chi tiết 3 test fail đầu + danh sách mọi test fail (1 dòng/test) + dòng tổng kết."""
    blocks: list[list[str]] = []
    summary: list[str] = []
    in_summary = False
    for ln in lines:
        if "short test summary info" in ln:
            in_summary = True
            continue
        if in_summary:
            if ln.startswith(("FAILED", "ERROR")):
                summary.append(clip(ln, 200))
            continue
        if PYTEST_BLOCK.match(ln):
            blocks.append([ln.strip("_ ")])
        elif blocks and not ln.startswith("="):
            blocks[-1].append(ln)
    out: list[str] = []
    for b in blocks[:3]:
        out.append(f"--- {b[0]}")
        out += [clip(x) for x in b[1:13]]
    if len(blocks) > 3:
        out.append(f"... chi tiết {len(blocks) - 3} test fail khác trong log")
    if len(summary) > limit:
        out += summary[:limit] + [f"... và {len(summary) - limit} test fail khác"]
    else:
        out += summary
    out += [x for x in lines[-1:] if "failed" in x or "error" in x]
    return out


def summarize_cargo_test(lines: list[str], limit: int) -> list[str]:
    """Giữ nguyên khối '---- test stdout ----' (có left/right của assert), 5 khối đầu."""
    blocks: list[list[str]] = []
    cur: list[str] | None = None
    for ln in lines:
        m = re.match(r"^---- (.+?) stdout ----$", ln.strip())
        if m:
            cur = [m.group(1)]
            blocks.append(cur)
        elif ln.strip() == "failures:" or ln.startswith("test result:"):
            cur = None
        elif cur is not None and not re.match(r"^\s*note: run with", ln):
            cur.append(ln)
    if not blocks:
        return []
    out: list[str] = []
    for b in blocks[:5]:
        out.append(f"--- {b[0]}")
        out += [clip(x) for x in b[1:9]]
    if len(blocks) > 5:
        out.append(f"... {len(blocks) - 5} test fail khác trong log")
    return out + [ln for ln in lines if ln.startswith("test result:")]


def summarize(output: str, mode: str | None, limit: int) -> list[str]:
    """Rút output dài thành vài chục dòng có ích nhất."""
    lines = [ANSI.sub("", ln).rstrip() for ln in shorten_paths(output).splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return []

    if mode == "files":  # lỗi format: chỉ cần biết file nào, bao nhiêu chỗ
        counts: dict[str, int] = {}
        for ln in lines:
            m = FILE_OF.match(ln) or WOULD_REFORMAT.match(ln)
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
        if counts:
            items = [f"{f} ({n})" for f, n in counts.items()]
            shown = ", ".join(items[:limit])
            if len(items) > limit:
                shown += f", +{len(items) - limit} file"
            return [f"{len(items)} file sai format (số chỗ): {shown}"]

    if mode == "pytest":
        out = summarize_pytest(lines, limit)
        if out:
            return out
    if mode == "cargo-test":
        out = summarize_cargo_test(lines, limit)
        if out:
            return out

    picked = []
    for ln in lines:
        if NOISE.search(ln):
            continue
        if ABS.match(ln) and SYS_CHAIN.search(ln):
            continue  # chuỗi template trong header hệ thống
        if KEEP.search(ln):
            picked.append(ln)
    if not picked:
        return [clip(x) for x in lines[-limit:]]
    grouped = group_diagnostics(picked)
    if len(grouped) > limit:
        hidden = len(grouped) - limit
        grouped = grouped[:limit] + [f"... và {hidden} lỗi khác (xem log đầy đủ)"]
    return grouped


# ---------------------------------------------------------------- chạy
def select_steps(steps: list[dict]) -> tuple[list[dict], bool]:
    """Lọc theo --only / --failed; tự kèm bước gate (configure/build) cùng stack đứng trước."""
    wanted: set[str] | None = None
    only = _arg_value("--only")
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
    elif "--failed" in ARGS:
        try:
            wanted = set(json.loads(STATE_FILE.read_text(encoding="utf-8")).get("failed", []))
        except (OSError, json.JSONDecodeError):
            wanted = None
        if not wanted:
            print("  (không có bước fail nào từ lần chạy trước → chạy đầy đủ)")
            return steps, False
    if wanted is None:
        return steps, False

    unknown = wanted - {s["name"] for s in steps}
    if unknown:
        print(f"  (không có bước: {', '.join(sorted(unknown))})")
    stacks = {n.split("-", 1)[0] for n in wanted}
    selected = []
    for i, s in enumerate(steps):
        stack = s["name"].split("-", 1)[0]
        later_wanted = any(t["name"] in wanted for t in steps[i + 1 :])
        # chỉ kèm bước gate cứng (configure/build); clippy (gate_if) thì không cần
        if s["name"] in wanted or (s.get("gate") and stack in stacks and later_wanted):
            selected.append(s)
    return selected, True


def main() -> int:
    if "steps" in CONFIG:
        steps = list(CONFIG["steps"])
    else:
        steps = (
            python_steps() + dotnet_steps() + rust_steps() + cpp_steps() + node_steps() + go_steps()
        )
    steps += CONFIG.get("extra_steps", [])
    steps = [s for s in steps if s["name"] not in SKIP]
    steps, partial = select_steps(steps)

    print(f"check.py — lint_scope={LINT_SCOPE}" + (" — CHẠY MỘT PHẦN" if partial else ""))
    if "--list" in ARGS:
        for s in steps:
            if "lazy" in s:
                cmd = "(xác định lúc chạy)"
            else:
                cmd = s["cmd"] if isinstance(s["cmd"], str) else " ".join(s["cmd"])
            print(f"  {s['name']}: {shorten_paths(cmd)}")
        return 0

    LOG_DIR.mkdir(exist_ok=True)
    gi = LOG_DIR / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")  # thư mục log tự loại khỏi git

    failed: list[str] = []
    blocked: set[str] = set()  # stack đã fail ở bước gate (configure/build)
    ran = 0
    for s in steps:
        name = s["name"]
        stack = name.split("-", 1)[0]
        note = f" ({s['note']})" if s.get("note") else ""
        if stack in blocked:
            print(f"SKIP {name} (bước build/configure trước đó fail)")
            continue
        if "lazy" in s:
            cmd = s["lazy"]()
            if cmd is None:
                print(f"SKIP {name}")
                continue
        else:
            cmd = s["cmd"]
        ran += 1
        log = LOG_DIR / f"{name}.log"
        start = time.monotonic()

        if VERBOSE:
            print(f"\n==> {name}{note}", flush=True)
            try:
                rc = subprocess.run(
                    cmd, shell=isinstance(cmd, str), cwd=s.get("cwd") or ROOT, env=TOOL_ENV
                ).returncode
            except OSError as e:
                print(f"    lỗi chạy lệnh: {e}")
                rc = 1
            output = ""
        else:
            try:
                r = subprocess.run(
                    cmd,
                    shell=isinstance(cmd, str),
                    cwd=s.get("cwd") or ROOT,
                    env=TOOL_ENV,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                rc = r.returncode
                output = r.stdout.decode("utf-8", errors="replace")
            except OSError as e:
                rc, output = 1, f"lỗi chạy lệnh: {e}"
            shown = cmd if isinstance(cmd, str) else " ".join(cmd)
            log.write_text(f"$ {shown}\n(exit {rc})\n\n{output}", encoding="utf-8")

        secs = time.monotonic() - start
        if rc == 0:
            print(f"PASS {name}{note} [{secs:.0f}s]", flush=True)
            continue
        failed.append(name)
        if s.get("gate") or (s.get("gate_if") and re.search(s["gate_if"], output)):
            blocked.add(stack)
        if VERBOSE:
            print(f"FAIL {name}", flush=True)
            continue
        total = len(output.splitlines())
        rel_log = log.relative_to(ROOT).as_posix()
        print(f"FAIL {name}{note} [{secs:.0f}s] — log đầy đủ ({total} dòng): {rel_log}")
        for ln in summarize(output, s.get("summarize"), MAX_LINES):
            print(f"  {ln}")
        if s.get("fix"):
            print(f"  → sửa tự động: {s['fix']}")
        print(flush=True)

    try:
        STATE_FILE.write_text(json.dumps({"failed": failed}), encoding="utf-8")
    except OSError:
        pass

    if not ran and not failed:
        print(
            "CHECK: UNRESOLVED — không có bước kiểm tra nào. Cài công cụ hoặc khai báo steps "
            "trong scripts/check.config.json."
        )
        return 3
    tag = " (MỘT PHẦN — chạy lại không có --failed/--only trước khi báo xong)" if partial else ""
    if failed:
        print(f"CHECK: FAIL ({len(failed)}/{ran}): {', '.join(failed)}{tag}")
        if not partial:
            print("Sửa xong chạy: python scripts/check.py --failed")
        return 1
    print(f"CHECK: PASS ({ran} bước){tag}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # output bị cắt bởi `| head`: thoát êm, không in traceback
        try:
            sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        except OSError:
            pass
        sys.exit(1)
