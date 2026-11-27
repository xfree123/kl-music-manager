"""Cơ sở dữ liệu thư viện (SQLite, module sqlite3 có sẵn): danh sách thư viện + metadata bài.

- `libraries`: mỗi thư viện là một thư mục người dùng đặt tên.
- `tracks`: tag + thông số file theo (library_id, relpath); size + mtime_ns để biết file đổi chưa.
  Trường chuẩn là cột (có index cho artist/album/genre/year); trường phụ (comment, bpm, total_discs…)
  nằm trong cột `extra` (JSON) -> thêm trường không cần đổi schema.
- 1 kết nối dùng chung giữa các luồng Flask, khoá bằng RLock; WAL để đọc không chặn ghi.
- `PRAGMA user_version` = SCHEMA_VERSION (nâng schema sau này thì migrate theo số này).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DB_FILENAME = "library.db"

# Cột tag chuẩn: tên -> kiểu (text/int/real). Key khác trong tags đi vào `extra`.
TAG_COLUMNS = {
    "title": "TEXT",
    "artist": "TEXT",
    "album": "TEXT",
    "album_artist": "TEXT",
    "genre": "TEXT",
    "composer": "TEXT",
    "year": "INTEGER",
    "track_number": "INTEGER",
    "total_tracks": "INTEGER",
    "disc_number": "INTEGER",
    "duration_s": "REAL",
    "bitrate_kbps": "INTEGER",
    "sample_rate": "INTEGER",
    "channels": "INTEGER",
    "bits_per_sample": "INTEGER",
    "codec": "TEXT",
}
_DEFAULTS = {"TEXT": "", "INTEGER": 0, "REAL": 0.0}

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS libraries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    root TEXT NOT NULL,
    root_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_scan TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tracks (
    library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    relpath TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    {", ".join(f"{name} {kind} NOT NULL DEFAULT {_DEFAULTS[kind]!r}" for name, kind in TAG_COLUMNS.items())},
    extra TEXT NOT NULL DEFAULT '{{}}',
    PRIMARY KEY (library_id, relpath)
);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(library_id, artist COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(library_id, album COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(library_id, genre COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_year ON tracks(library_id, year);
"""

_TRACK_FIELDS = ["relpath", "size", "mtime_ns", *TAG_COLUMNS, "extra"]
_UPSERT = (
    f"INSERT OR REPLACE INTO tracks (library_id, {', '.join(_TRACK_FIELDS)}) "
    f"VALUES ({', '.join('?' * (len(_TRACK_FIELDS) + 1))})"
)

Entry = Dict[str, Any]  # {"size": int, "mtime_ns": int, "tags": {...}}


def root_key(root: Union[str, Path]) -> str:
    """Khoá so trùng thư mục (không phân biệt hoa thường trên Windows, bỏ dấu / cuối)."""
    return os.path.normcase(os.path.abspath(str(root)))


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _row_values(library_id: int, relpath: str, entry: Entry) -> tuple:
    tags = entry.get("tags", {})
    columns = []
    for name, kind in TAG_COLUMNS.items():
        value = tags.get(name)
        columns.append(_DEFAULTS[kind] if value in (None, "") else value)
    extra = {k: v for k, v in tags.items() if k not in TAG_COLUMNS}
    return (
        library_id,
        relpath,
        int(entry["size"]),
        int(entry["mtime_ns"]),
        *columns,
        json.dumps(extra, ensure_ascii=False),
    )


class LibraryDB:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._con.row_factory = sqlite3.Row
        with self._lock:
            self._con.execute("PRAGMA journal_mode=WAL")
            self._con.execute("PRAGMA foreign_keys=ON")
            self._migrate()

    def _migrate(self) -> None:
        version = self._con.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"{self.path} has a newer schema ({version}); update the app")
        self._con.executescript(_SCHEMA)
        self._con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._con.close()

    def schema_version(self) -> int:
        with self._lock:
            return self._con.execute("PRAGMA user_version").fetchone()[0]

    def file_size(self) -> int:
        """Dung lượng DB trên đĩa (kể cả file -wal)."""
        total = 0
        for suffix in ("", "-wal"):
            p = Path(str(self.path) + suffix)
            if p.exists():
                total += p.stat().st_size
        return total

    # ------------------------------------------------------------ thư viện
    def _library_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "root": row["root"],
            "created_at": row["created_at"],
            "last_scan": row["last_scan"],
            "track_count": row["track_count"],
        }

    _LIB_SELECT = (
        "SELECT l.*, (SELECT COUNT(*) FROM tracks t WHERE t.library_id = l.id) AS track_count "
        "FROM libraries l"
    )

    def libraries(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._con.execute(f"{self._LIB_SELECT} ORDER BY l.name COLLATE NOCASE, l.id")
            return [self._library_dict(r) for r in rows]

    def get_library(self, library_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._con.execute(f"{self._LIB_SELECT} WHERE l.id = ?", (library_id,)).fetchone()
            return self._library_dict(row) if row else None

    def library_for_root(self, root: Union[str, Path]) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._con.execute(
                f"{self._LIB_SELECT} WHERE l.root_key = ?", (root_key(root),)
            ).fetchone()
            return self._library_dict(row) if row else None

    def add_library(self, name: str, root: Union[str, Path]) -> Dict[str, Any]:
        """Raises: ValueError nếu tên rỗng hoặc thư mục đã là một thư viện."""
        clean = (name or "").strip()
        if not clean:
            raise ValueError("Library name is required")
        with self._lock:
            try:
                cur = self._con.execute(
                    "INSERT INTO libraries (name, root, root_key, created_at) VALUES (?, ?, ?, ?)",
                    (clean, str(root), root_key(root), _now()),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"This folder is already a library: {root}") from None
            return self.get_library(cur.lastrowid)

    def rename_library(self, library_id: int, name: str) -> bool:
        """Raises: ValueError nếu tên rỗng."""
        clean = (name or "").strip()
        if not clean:
            raise ValueError("Library name is required")
        with self._lock:
            cur = self._con.execute(
                "UPDATE libraries SET name = ? WHERE id = ?", (clean, library_id)
            )
            return cur.rowcount > 0

    def remove_library(self, library_id: int) -> bool:
        """Gỡ thư viện và metadata của nó (không đụng file nhạc)."""
        with self._lock:
            cur = self._con.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
            return cur.rowcount > 0

    def set_last_scan(self, library_id: int, when: Optional[str] = None) -> None:
        with self._lock:
            self._con.execute(
                "UPDATE libraries SET last_scan = ? WHERE id = ?", (when or _now(), library_id)
            )

    # ------------------------------------------------------------ bài
    def load_tracks(self, library_id: int) -> Dict[str, Entry]:
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM tracks WHERE library_id = ?", (library_id,)
            ).fetchall()
        result: Dict[str, Entry] = {}
        for row in rows:
            tags = {name: row[name] for name in TAG_COLUMNS}
            try:
                tags.update(json.loads(row["extra"] or "{}"))
            except ValueError:
                logger.warning("Bad extra JSON for %s", row["relpath"])
            result[row["relpath"]] = {
                "size": row["size"],
                "mtime_ns": row["mtime_ns"],
                "tags": tags,
            }
        return result

    def replace_tracks(self, library_id: int, entries: Dict[str, Entry]) -> None:
        """Đồng bộ toàn bộ bài của thư viện trong 1 transaction (bài không còn thì xoá)."""
        with self._lock:
            self._con.execute("BEGIN")
            try:
                self._con.execute("DELETE FROM tracks WHERE library_id = ?", (library_id,))
                self._con.executemany(
                    _UPSERT, [_row_values(library_id, rel, e) for rel, e in entries.items()]
                )
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise
            # Gộp WAL vào file chính sau lần ghi lớn (file -wal không phình mãi)
            self._con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def upsert_track(self, library_id: int, relpath: str, entry: Entry) -> None:
        with self._lock:
            self._con.execute(_UPSERT, _row_values(library_id, relpath, entry))

    def delete_track(self, library_id: int, relpath: str) -> None:
        with self._lock:
            self._con.execute(
                "DELETE FROM tracks WHERE library_id = ? AND relpath = ?", (library_id, relpath)
            )

    def clear_tracks(self, library_id: int) -> None:
        with self._lock:
            self._con.execute("DELETE FROM tracks WHERE library_id = ?", (library_id,))

    def track_count(self, library_id: int) -> int:
        with self._lock:
            return self._con.execute(
                "SELECT COUNT(*) FROM tracks WHERE library_id = ?", (library_id,)
            ).fetchone()[0]
