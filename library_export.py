"""Export danh sách nhạc và thông tin thư viện ra JSON / HTML (trang tự chứa, không file ngoài)."""

from __future__ import annotations

import datetime
import json
from html import escape
from typing import Any, Dict, Iterable, List

TRACK_COLUMNS = [
    ("title", "Title"),
    ("artist", "Artist"),
    ("album", "Album"),
    ("genre", "Genre"),
    ("year", "Year"),
    ("duration_s", "Time"),
    ("file_type", "Type"),
    ("bitrate_kbps", "kbps"),
    ("play_count", "Plays"),
]

_STYLE = """
body{font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;margin:24px;color:#222}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px}
.meta{color:#666;font-size:12px;margin-bottom:16px}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{border-bottom:1px solid #e3e3e3;padding:4px 8px;text-align:left;vertical-align:top}
th{background:#f4f4f4;position:sticky;top:0}
td.num,th.num{text-align:right}
@media print{th{position:static}}
"""


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def format_duration(seconds: Any) -> str:
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def format_size(n: Any) -> str:
    size = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def _page(title: str, body: str) -> str:
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{escape(title)}</title>\n<style>{_STYLE}</style>\n</head>\n<body>\n"
        f"<h1>{escape(title)}</h1>\n"
        f'<div class="meta">Exported by KL Music Manager · {escape(_now())}</div>\n'
        f"{body}\n</body>\n</html>\n"
    )


def _cell(key: str, value: Any) -> str:
    if key == "duration_s":
        return f'<td class="num">{escape(format_duration(value))}</td>'
    if key in ("year", "bitrate_kbps", "play_count"):
        return f'<td class="num">{escape(str(value or ""))}</td>'
    return f"<td>{escape(str(value if value is not None else ''))}</td>"


def _tracks_table(records: Iterable[Dict[str, Any]]) -> str:
    head = "".join(
        f'<th class="num">{escape(label)}</th>'
        if key in ("duration_s", "year", "bitrate_kbps", "play_count")
        else f"<th>{escape(label)}</th>"
        for key, label in TRACK_COLUMNS
    )
    rows = "\n".join(
        '<tr><td class="num">{}</td>{}</tr>'.format(
            i, "".join(_cell(key, r.get(key)) for key, _ in TRACK_COLUMNS)
        )
        for i, r in enumerate(records, 1)
    )
    return f'<table>\n<thead><tr><th class="num">#</th>{head}</tr></thead>\n<tbody>\n{rows}\n</tbody>\n</table>'


def tracks_json(records: List[Dict[str, Any]], title: str) -> str:
    return json.dumps(
        {"title": title, "exported_at": _now(), "count": len(records), "tracks": records},
        ensure_ascii=False,
        indent=2,
    )


def tracks_html(records: List[Dict[str, Any]], title: str) -> str:
    total = sum(int(r.get("duration_s") or 0) for r in records)
    summary = f"<p>{len(records)} tracks · {escape(format_duration(total))}</p>"
    return _page(title, summary + _tracks_table(records))


def library_info(
    device: Dict[str, Any], records: List[Dict[str, Any]], playlists: List[Dict[str, Any]]
) -> Dict[str, Any]:
    by_type: Dict[str, int] = {}
    for r in records:
        t = r.get("file_type") or "Unknown"
        by_type[t] = by_type.get(t, 0) + 1
    return {
        "exported_at": _now(),
        "device": device,
        "totals": {
            "tracks": len(records),
            "duration_s": sum(int(r.get("duration_s") or 0) for r in records),
            "size_bytes": sum(int(r.get("file_size") or 0) for r in records),
            "artists": len({r.get("artist") for r in records if r.get("artist")}),
            "albums": len({r.get("album") for r in records if r.get("album")}),
            "playlists": len(playlists),
        },
        "by_file_type": by_type,
        "playlists": [
            {
                "name": p.get("name"),
                "track_count": len(p.get("track_ids") or []),
                "is_master": bool(p.get("is_master")),
            }
            for p in playlists
        ],
    }


def library_info_json(info: Dict[str, Any]) -> str:
    return json.dumps(info, ensure_ascii=False, indent=2)


def _kv_table(rows: List[tuple]) -> str:
    body = "\n".join(
        f"<tr><th>{escape(str(k))}</th><td>{escape(str(v))}</td></tr>" for k, v in rows
    )
    return f"<table>\n{body}\n</table>"


def library_info_html(info: Dict[str, Any]) -> str:
    d, t = info.get("device", {}), info.get("totals", {})
    device_rows = [
        ("Model", d.get("model", "")),
        ("Mount point", d.get("mountpoint", "")),
        ("Capacity", format_size(d.get("total_space"))),
        ("Free", format_size(d.get("free_space"))),
    ]
    total_rows = [
        ("Tracks", t.get("tracks", 0)),
        ("Total time", format_duration(t.get("duration_s"))),
        ("Total size", format_size(t.get("size_bytes"))),
        ("Artists", t.get("artists", 0)),
        ("Albums", t.get("albums", 0)),
        ("Playlists", t.get("playlists", 0)),
    ]
    type_rows = sorted(info.get("by_file_type", {}).items(), key=lambda kv: -kv[1])
    pl_rows = [
        (p["name"] + (" (library)" if p.get("is_master") else ""), p["track_count"])
        for p in info.get("playlists", [])
    ]
    body = (
        "<h2>Device</h2>" + _kv_table(device_rows)
        + "<h2>Library</h2>" + _kv_table(total_rows)
        + "<h2>File types</h2>" + _kv_table(type_rows)
        + "<h2>Playlists</h2>" + _kv_table(pl_rows)
    )  # fmt: skip
    return _page("iPod library information", body)
