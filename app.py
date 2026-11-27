import datetime
import logging
import os
import platform
import shutil
import sys
import tempfile
import webbrowser
from pathlib import Path
from flask import Flask, Response, request, jsonify, send_from_directory, send_file
from ipod_manager import IPodManager, ScanBusy
import converter
import library_export
import os_integration
import settings
import version

logger = logging.getLogger("app")

# Bản đóng gói PyInstaller giải nén dữ liệu (static/) vào sys._MEIPASS
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
# Không dựa vào mimetypes của OS (Windows đoán .flac thành audio/x-flac, tùy registry)
AUDIO_MIMETYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
}

app = Flask(__name__, static_folder=str(BASE_DIR / "static"), static_url_path="")
manager = IPodManager()

# Request ghi được phép khi read-only: không sửa iPod (chỉ đọc iPod / sửa cài đặt app)
READ_ONLY_ALLOWED = [
    ("POST", "/api/device/redetect"),
    ("POST", "/api/tracks/reveal/"),
    ("POST", "/api/tracks/play-system/"),
    ("POST", "/api/tracks/export/"),
    ("PUT", "/api/settings"),  # phải được phép để tắt read-only
    ("POST", "/api/library/source"),  # chỉ đổi nguồn đang xem, không ghi thư viện
    # Danh sách thư viện / quét / dọn cache: chỉ ghi DB + cache của app, không ghi file nhạc
    ("POST", "/api/libraries"),
    ("PUT", "/api/libraries/"),
    ("DELETE", "/api/libraries/"),
    ("POST", "/api/maintenance/"),
]


LOCAL_HOSTNAMES = ("127.0.0.1", "localhost", "[::1]")
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _host_name(host: str) -> str:
    """'127.0.0.1:5055' -> '127.0.0.1', '[::1]:5055' -> '[::1]'."""
    if host.startswith("["):
        return host.split("]", 1)[0] + "]"
    return host.rsplit(":", 1)[0] if ":" in host else host


@app.before_request
def reject_foreign_requests():
    """Backend chỉ phục vụ chính app trên máy này.

    - Host phải là 127.0.0.1 / localhost: chặn DNS rebinding (tên miền lạ trỏ về 127.0.0.1
      sẽ thành cùng origin với backend và gọi được mọi API).
    - Request ghi có Origin phải cùng origin: chặn CSRF (form / fetch no-cors từ trang khác).
    """
    host = request.host.lower()
    if _host_name(host) not in LOCAL_HOSTNAMES:
        return jsonify({"success": False, "error": "Forbidden host"}), 403
    origin = request.headers.get("Origin")
    if request.method not in SAFE_METHODS and origin is not None:
        if origin.lower() != f"http://{host}":
            return jsonify({"success": False, "error": "Cross-origin request refused"}), 403


@app.before_request
def restrict_write_operations():
    # Block modifying requests in Read-Only mode, except the READ_ONLY_ALLOWED list
    if manager.read_only and request.method in ["POST", "DELETE", "PUT"]:
        if any(
            request.method == method and request.path.startswith(prefix)
            for method, prefix in READ_ONLY_ALLOWED
        ):
            return
        return jsonify(
            {
                "success": False,
                "error": "KL Music Manager is running in safe Read-Only mode to protect your external disk.",
            }
        ), 403


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/device", methods=["GET"])
def get_device():
    info = manager.get_device_info()
    return jsonify(info)


@app.route("/api/device/redetect", methods=["POST"])
def redetect_device():
    path = manager.detect_device()
    info = manager.get_device_info()
    return jsonify({"success": True, "mountpoint": path, "device": info})


@app.route("/api/tracks", methods=["GET"])
def get_tracks():
    tracks = manager.get_tracks()
    return jsonify(tracks)


@app.route("/api/tracks/add", methods=["POST"])
def add_track():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    # Chỉ lấy tên file (bỏ thư mục, cả "\" lẫn "/"): tên do client gửi có thể chứa "../"
    filename = os.path.basename((file.filename or "").replace("\\", "/"))
    if filename in ("", ".", ".."):
        return jsonify({"success": False, "error": "Empty filename"}), 400

    # Save to a private temporary folder (giữ tên gốc: pygpod/import dùng đuôi + tên file)
    temp_dir = tempfile.mkdtemp(prefix="klmm_upload_")
    temp_path = os.path.join(temp_dir, filename)
    file.save(temp_path)

    # Extract optional metadata overrides from form fields
    metadata = {
        "title": request.form.get("title"),
        "artist": request.form.get("artist"),
        "album": request.form.get("album"),
        "genre": request.form.get("genre"),
        "year": request.form.get("year"),
        "track_number": request.form.get("track_number"),
        "rating": request.form.get("rating"),
    }

    try:
        result = manager.add_track_detailed(
            temp_path, metadata, playlist=request.form.get("playlist") or None
        )
    finally:
        # Clean up temp file + folder
        shutil.rmtree(temp_dir, ignore_errors=True)

    if result["track_id"] is not None:
        return jsonify(
            {"success": True, "track_id": result["track_id"], "converted": result["converted"]}
        )
    return jsonify(
        {"success": False, "error": result["error"] or "Failed to add track to the library"}
    )


@app.route("/api/tracks/import-paths", methods=["POST"])
def import_paths():
    """Desktop: import theo đường dẫn trên máy (file hoặc thư mục, quét đệ quy).
    Body: {"paths": [...], "playlist": "<tên>"}"""
    data = request.get_json(silent=True) or {}
    paths = data.get("paths")
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths) or not paths:
        return jsonify({"success": False, "error": "paths must be a non-empty list"}), 400
    results = manager.import_paths(paths, playlist=data.get("playlist") or None)
    return jsonify({"success": any(r["ok"] for r in results), "results": results})


@app.route("/api/tracks/<int:track_id>", methods=["DELETE"])
def remove_track(track_id):
    success = manager.remove_track(track_id)
    return jsonify({"success": success})


@app.route("/api/tracks/export/<int:track_id>", methods=["GET"])
def export_track(track_id):
    # Create an export directory in downloads or a temp folder
    export_dir = os.path.join(tempfile.gettempdir(), "klmm_export")
    os.makedirs(export_dir, exist_ok=True)

    exported_path = manager.export_track(track_id, export_dir)
    if exported_path and os.path.exists(exported_path):
        # Serve the file for download
        filename = os.path.basename(exported_path)

        # We want to delete the file after sending it, but since Flask send_file runs asynchronously,
        # we can't delete it immediately. Let's just return it. The temp dir gets cleared by OS anyway.
        return send_file(exported_path, as_attachment=True, download_name=filename)
    else:
        return jsonify(
            {"success": False, "error": "Failed to export file. It may be missing on the iPod."}
        ), 404


@app.route("/api/tracks/reveal/<int:track_id>", methods=["POST"])
def reveal_track(track_id):
    src_path = manager.track_file(track_id)
    if not src_path:
        return jsonify({"success": False, "error": "Track or its file not found"}), 404
    try:
        os_integration.reveal_in_file_manager(src_path)
    except OSError as e:
        logger.error(f"Failed to reveal {src_path}: {e}")
        return jsonify({"success": False, "error": f"Cannot open file manager: {e}"}), 500
    return jsonify({"success": True})


@app.route("/api/tracks/play-system/<int:track_id>", methods=["POST"])
def play_system_track(track_id):
    src_path = manager.track_file(track_id)
    if not src_path:
        return jsonify({"success": False, "error": "Track or its file not found"}), 404
    try:
        os_integration.open_with_default_app(src_path)
    except OSError as e:
        logger.error(f"Failed to open {src_path} with default app: {e}")
        return jsonify({"success": False, "error": f"Cannot open system player: {e}"}), 500
    return jsonify({"success": True})


@app.route("/api/tracks/update/<int:track_id>", methods=["POST"])
def update_track(track_id):
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    success = manager.update_track_metadata(track_id, data)
    return jsonify({"success": success})


@app.route("/api/playlists", methods=["GET"])
def get_playlists():
    playlists = manager.get_playlists()
    return jsonify(playlists)


@app.route("/api/playlists/create", methods=["POST"])
def create_playlist():
    data = request.json
    if not data or "name" not in data:
        return jsonify({"success": False, "error": "Playlist name is required"}), 400

    success = manager.create_playlist(data["name"])
    return jsonify({"success": success})


@app.route("/api/playlists/<string:name>", methods=["DELETE"])
def delete_playlist(name):
    success = manager.delete_playlist(name)
    return jsonify({"success": success})


@app.route("/api/playlists/<string:name>/add/<int:track_id>", methods=["POST"])
def add_to_playlist(name, track_id):
    success = manager.add_track_to_playlist(name, track_id)
    return jsonify({"success": success})


@app.route("/api/playlists/<string:name>/remove/<int:track_id>", methods=["POST"])
def remove_from_playlist(name, track_id):
    success = manager.remove_track_from_playlist(name, track_id)
    return jsonify({"success": success})


@app.route("/api/device/repair", methods=["POST"])
def repair_device():
    success = manager.repair_db()
    return jsonify({"success": success})


@app.route("/api/tracks/play/<int:track_id>", methods=["GET"])
def play_track(track_id):
    path = manager.stream_path(track_id)
    if path:
        return send_file(path, mimetype=_audio_mimetype(path), conditional=True)
    return jsonify({"success": False, "error": "Track or its audio file not found"}), 404


@app.route("/api/tracks/<int:track_id>/artwork", methods=["GET"])
def track_artwork(track_id):
    data = manager.artwork_jpeg(track_id)
    if data is None:
        return jsonify({"success": False, "error": "No artwork"}), 404
    res = Response(data, mimetype="image/jpeg")
    res.headers["Cache-Control"] = "private, max-age=3600"
    return res


@app.route("/api/tracks/<int:track_id>/artwork", methods=["POST", "DELETE"])
def set_track_artwork(track_id):
    """POST multipart: image=<file>, apply_album=1 (cả album). DELETE: xoá ảnh nhúng."""
    image = None
    apply_album = request.form.get("apply_album") in ("1", "true", "on")
    if request.method == "POST":
        upload = request.files.get("image")
        if upload is None:
            return jsonify({"success": False, "error": "No image uploaded"}), 400
        image = upload.read()
    else:
        apply_album = request.args.get("apply_album") in ("1", "true")
    try:
        updated = manager.set_track_cover(track_id, image, apply_album)
    except LookupError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Cannot write artwork for track {track_id}: {e}")
        return jsonify({"success": False, "error": f"Cannot write artwork: {e}"}), 500
    return jsonify({"success": True, "updated": updated})


@app.route("/api/tracks/<int:track_id>/details", methods=["GET"])
def track_details(track_id):
    details = manager.track_details(track_id)
    if details is None:
        return jsonify({"success": False, "error": "Track or its audio file not found"}), 404
    return jsonify(details)


# ---------------------------------------------------------------- thư viện (nhiều thư mục)
def _library_call(fn, *args):
    """Gọi thao tác thư viện, đổi lỗi thành mã HTTP (404 / 409 / 400)."""
    try:
        return fn(*args), None
    except LookupError as e:
        return None, (jsonify({"success": False, "error": str(e)}), 404)
    except ScanBusy as e:
        return None, (jsonify({"success": False, "error": str(e)}), 409)
    except (ValueError, OSError) as e:
        return None, (jsonify({"success": False, "error": str(e)}), 400)


@app.route("/api/libraries", methods=["GET"])
def list_libraries():
    return jsonify(manager.list_libraries())


@app.route("/api/libraries", methods=["POST"])
def create_library():
    data = request.get_json(silent=True) or {}
    lib, err = _library_call(manager.create_library, data.get("name", ""), data.get("root", ""))
    return err or jsonify({"success": True, "library": lib})


@app.route("/api/libraries/<int:library_id>", methods=["PUT"])
def rename_library(library_id):
    data = request.get_json(silent=True) or {}
    lib, err = _library_call(manager.rename_library, library_id, data.get("name", ""))
    return err or jsonify({"success": True, "library": lib})


@app.route("/api/libraries/<int:library_id>", methods=["DELETE"])
def remove_library(library_id):
    switched, err = _library_call(manager.remove_library, library_id)
    return err or jsonify({"success": True, "switched": bool(switched)})


@app.route("/api/libraries/<int:library_id>/open", methods=["POST"])
def open_library(library_id):
    _, err = _library_call(manager.open_library, library_id)
    return err or jsonify({"success": True, "device": manager.get_device_info()})


@app.route("/api/libraries/<int:library_id>/<string:action>", methods=["POST"])
def library_action(library_id, action):
    """scan (quét tăng dần), rebuild (đọc lại tag mọi file), clear (xoá metadata đã lập chỉ mục)."""
    calls = {
        "scan": lambda: manager.scan_library(library_id),
        "rebuild": lambda: manager.scan_library(library_id, force=True),
        "clear": lambda: manager.clear_library(library_id),
    }
    if action not in calls:
        return jsonify({"success": False, "error": f"Unknown action: {action}"}), 404
    stats, err = _library_call(calls[action])
    return err or jsonify({"success": True, **stats})


@app.route("/api/libraries/rescan", methods=["POST"])
def rescan_libraries():
    """Quét mọi thư viện. {"only_if_due": true} = gọi tự động khi máy rảnh (theo cài đặt)."""
    data = request.get_json(silent=True) or {}
    result, err = _library_call(manager.rescan_all, bool(data.get("only_if_due")))
    return err or jsonify(result)


# ---------------------------------------------------------------- dọn dẹp
@app.route("/api/maintenance", methods=["GET"])
def maintenance_info():
    return jsonify(manager.maintenance_info())


@app.route("/api/maintenance/clear-cache", methods=["POST"])
def clear_cache():
    return jsonify({"success": True, "freed_bytes": manager.clear_cache()})


# ---------------------------------------------------------------- library source
@app.route("/api/library/source", methods=["GET"])
def get_library_source():
    return jsonify(manager.source_info())


@app.route("/api/library/source", methods=["POST"])
def set_library_source():
    """Body: {"source": "ipod"} | {"source": "folder", "folder": "<đường dẫn>"}"""
    data = request.get_json(silent=True) or {}
    try:
        manager.set_source(data.get("source", ""), data.get("folder", ""))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **manager.source_info(), "device": manager.get_device_info()})


# ---------------------------------------------------------------- settings
@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(manager.config)


@app.route("/api/settings", methods=["PUT"])
def put_settings():
    try:
        updated = settings.update_settings(request.get_json(silent=True))
    except settings.SettingsError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    manager.apply_settings(updated)
    return jsonify(updated)


@app.route("/api/about", methods=["GET"])
def about():
    return jsonify(
        {
            "name": version.APP_NAME,
            "version": version.VERSION,
            "license": version.LICENSE,
            "author": version.AUTHOR,
            "homepage": version.HOMEPAGE,
            "python": sys.version.split()[0],
            "platform": f"{platform.system()} {platform.release()}",
            "ffmpeg": manager.ffmpeg_path() or "",
            "data_dir": str(settings.data_dir()),
        }
    )


@app.route("/api/formats", methods=["GET"])
def get_formats():
    ffmpeg = manager.ffmpeg_path()
    return jsonify(
        {
            "formats": converter.list_formats(),
            "ffmpeg_available": bool(ffmpeg),
            "ffmpeg_path": ffmpeg,
        }
    )


# ---------------------------------------------------------------- export
def _audio_mimetype(path: str) -> str:
    return AUDIO_MIMETYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


@app.route("/api/tracks/export/<int:track_id>", methods=["POST"])
def export_track_converted(track_id):
    """Body: {"format": "mp3", "options": {...}, "destination": "folder" | "download",
    "dest_dir": "<thư mục, mặc định export_dir>", "layout": "flat" | "artist_album",
    "subfolder": "<tên>", "skip_existing": bool}. 4 trường sau dùng cho export nhiều bài."""
    data = request.get_json(silent=True) or {}
    fmt = data.get("format") or manager.config["export_format"]
    options = {**manager.config["export_options"], **(data.get("options") or {})}
    to_folder = data.get("destination", "folder") == "folder"
    if to_folder:
        dest_dir = str(data.get("dest_dir") or "").strip() or manager.config["export_dir"]
    else:
        dest_dir = tempfile.mkdtemp(prefix="klmm_")
    try:
        result = manager.export_track_to(
            track_id,
            fmt,
            options,
            dest_dir,
            layout=str(data.get("layout") or "flat"),
            subfolder=str(data.get("subfolder") or "") if to_folder else "",
            skip_existing=bool(data.get("skip_existing")) and to_folder,
        )
        path = result["path"]
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except KeyError:
        return jsonify({"success": False, "error": "Track or its file not found on iPod"}), 404
    except converter.ConversionError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except OSError as e:
        return jsonify({"success": False, "error": f"Cannot write export file: {e}"}), 500
    if to_folder:
        return jsonify(
            {"success": True, "path": path, "skipped": result["skipped"], "root": result["root"]}
        )
    return send_file(
        path,
        mimetype=_audio_mimetype(path),
        as_attachment=True,
        download_name=os.path.basename(path),
    )


def _library_response(content: str, fmt: str, basename: str):
    """Trả nội dung (JSON/HTML) hoặc ghi vào thư mục export nếu ?destination=folder."""
    ext, mimetype = (".html", "text/html") if fmt == "html" else (".json", "application/json")
    if request.args.get("destination") == "folder":
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = converter.output_filename({"artist": "KL Music Manager", "title": basename}, "")
        target = Path(manager.config["export_dir"]) / f"{safe} {stamp}{ext}"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as e:
            return jsonify({"success": False, "error": f"Cannot write export file: {e}"}), 500
        return jsonify({"success": True, "path": str(target)})
    return Response(content, mimetype=mimetype)


@app.route("/api/library/tracks", methods=["GET"])
def export_library_tracks():
    """?format=json|html&playlist=<name>&destination=folder"""
    fmt = request.args.get("format", "json")
    if fmt not in ("json", "html"):
        return jsonify({"success": False, "error": "format must be json or html"}), 400
    playlist = request.args.get("playlist") or None
    try:
        records = manager.get_track_records(playlist)
    except KeyError:
        return jsonify({"success": False, "error": f"Playlist not found: {playlist}"}), 404
    title = f"Playlist: {playlist}" if playlist else "All tracks"
    content = (
        library_export.tracks_html(records, title)
        if fmt == "html"
        else library_export.tracks_json(records, title)
    )
    return _library_response(content, fmt, f"Tracks - {playlist or 'All'}")


@app.route("/api/library/info", methods=["GET"])
def export_library_info():
    """?format=json|html&destination=folder"""
    fmt = request.args.get("format", "json")
    if fmt not in ("json", "html"):
        return jsonify({"success": False, "error": "format must be json or html"}), 400
    info = library_export.library_info(
        manager.get_device_info(), manager.get_track_records(), manager.get_playlists()
    )
    content = (
        library_export.library_info_html(info)
        if fmt == "html"
        else library_export.library_info_json(info)
    )
    return _library_response(content, fmt, "Library info")


# Fallback to serve static files
@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(app.static_folder, path)


def main() -> None:
    """KLMM_PORT: cổng (mặc định 5055). KLMM_NO_BROWSER=1: không mở trình duyệt (Electron)."""
    port = int(os.environ.get("KLMM_PORT", "5055"))
    if not os.environ.get("KLMM_NO_BROWSER"):
        webbrowser.open(f"http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
