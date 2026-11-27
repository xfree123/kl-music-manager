"""Checksum iTunesDB khi DB có cả hash58 lẫn hash72 (iTunes / Winamp ghi cả hai cho iPod Classic).

Lỗi gặp trên iPod Classic 6G (hash58): update_checksums thấy chữ ký hash72 (byte 0x72 = 0x01) thì
chỉ tính lại hash72 và để nguyên hash58 cũ -> iPod thấy hash58 sai, coi DB rỗng (không bài, không
playlist) sau khi rút khỏi máy.
"""

import os

from pygpod.device.models import ChecksumType
from pygpod.hash import hash58, hash72
from pygpod.hash.checksum import update_checksums

GUID = "000A27001301297E"


def fake_db(content: bytes = b"tracks v1", with_hash72: bool = True) -> bytes:
    """Header mhbd đủ dài (0xF4) + nội dung; chữ ký hash58 + hash72 hợp lệ cho nội dung."""
    buf = bytearray(b"mhbd" + (0xF4).to_bytes(4, "little") + bytes(0xF4 - 8))
    buf[0x30:0x32] = (1).to_bytes(2, "little")  # hashing_scheme = hash58
    data = bytes(buf) + content
    if with_hash72:
        data = hash72.compute_hash72(data, iv=os.urandom(16), random_bytes=os.urandom(12))
    return hash58.compute_hash58(data, GUID)


def hash58_valid(data: bytes) -> bool:
    return hash58.compute_hash58(data, GUID)[0x58:0x6C] == data[0x58:0x6C]


def changed(data: bytes, content: bytes) -> bytes:
    """Như khi lưu: nội dung DB đổi, chữ ký còn là của nội dung cũ."""
    return data[:0xF4] + content


def test_hash58_device_updates_hash58_even_when_hash72_present():
    old = fake_db()
    assert old[0x72] == 0x01 and hash58_valid(old)
    data = changed(old, b"tracks v2 (one more)")
    assert not hash58_valid(data)

    out = update_checksums(data, GUID, ChecksumType.HASH58)

    assert hash58_valid(out)  # iPod Classic 6G kiểm hash58
    # hash72 vẫn được cập nhật (tính trước hash58 vì HMAC hash58 bao gồm vùng hash72)
    assert out[0x72] == 0x01
    assert hash72.compute_hash72(out)[0x72 : 0x72 + 46] == out[0x72 : 0x72 + 46]


def test_hash58_device_without_hash72():
    data = changed(fake_db(with_hash72=False), b"tracks v2")
    out = update_checksums(data, GUID, ChecksumType.HASH58)
    assert hash58_valid(out) and out[0x72] == 0x00


def test_hash72_device_only_touches_hash72():
    data = changed(fake_db(), b"tracks v2")
    out = update_checksums(data, GUID, ChecksumType.HASH72)
    assert hash72.compute_hash72(out)[0x72 : 0x72 + 46] == out[0x72 : 0x72 + 46]
    assert out[0x58:0x6C] == data[0x58:0x6C]  # thiết bị hash72 không cần hash58


def test_unknown_scheme_keeps_both_valid():
    """Không biết loại thiết bị (gọi kiểu cũ): có GUID thì hash58 luôn hợp lệ."""
    data = changed(fake_db(), b"tracks v2")
    out = update_checksums(data, GUID)
    assert hash58_valid(out)


def test_database_save_passes_device_checksum_type(tmp_path, monkeypatch):
    """Database.save truyền loại checksum của thiết bị vào update_checksums."""
    from pygpod.device.mountpoint import init_ipod
    from pygpod.model import database as dbmod

    init_ipod(str(tmp_path), model="classic_6g", music_dirs=2)
    sysinfo = tmp_path / "iPod_Control" / "Device" / "SysInfo"
    sysinfo.write_text(f"ModelNumStr: MB029\nFirewireGuid: 0x{GUID}\n", encoding="utf-8")
    db = dbmod.Database(str(tmp_path))
    seen = {}

    def spy(data, guid=None, scheme=None):
        seen.update(guid=guid, scheme=scheme)
        return data

    monkeypatch.setattr(dbmod, "update_checksums", spy)
    db.save()
    assert seen["guid"] and seen["scheme"] == db._device.checksum_type
