"""WAV chứa luồng DTS (DTS-CD / DTS-WAV): header khai PCM nhưng dữ liệu là DTS.

Trình duyệt phát như PCM -> chỉ nghe nhiễu trắng; phải nhận diện để chuyển mã qua ffmpeg.
"""

import struct

import pytest

import converter
import tag_editor

SYNC_BITS = "01111111111111101000000000000001"  # 0x7FFE8001


def dts_header_bits(amode=9, lfe=True, xch=True):
    """Header frame lõi DTS (đủ tới LFF), dạng chuỗi bit."""
    bits = SYNC_BITS
    bits += "1" + "11111" + "0"  # FTYPE, SHORT, CPF
    bits += format(15, "07b")  # NBLKS
    bits += format(2012, "014b")  # FSIZE
    bits += format(amode, "06b")  # AMODE
    bits += format(13, "04b")  # SFREQ
    bits += format(24, "05b")  # RATE
    bits += "00000"  # MIX, DYNF, TIMEF, AUXF, HDCD
    bits += format(0, "03b")  # EXT_AUDIO_ID = XCh
    bits += "1" if xch else "0"  # EXT_AUDIO
    bits += "1"  # ASPF
    bits += "01" if lfe else "00"  # LFF
    return bits


def pack(bits, width, order):
    """Đóng gói chuỗi bit thành word 14 hoặc 16 bit (little / big endian)."""
    bits += "0" * (-len(bits) % width)
    words = [int(bits[i : i + width], 2) for i in range(0, len(bits), width)]
    if width == 14:  # word 14 bit được mở rộng dấu lên 16 bit (0x2800 -> 0xE800)
        words = [w | 0xC000 if w & 0x2000 else w for w in words]
    fmt = "<H" if order == "le" else ">H"
    return b"".join(struct.pack(fmt, w) for w in words)


def make_wav(path, data, channels=2, rate=44100):
    data = data + b"\x00" * (-len(data) % 4)
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 2, channels * 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def make_dts_wav(path, width=14, order="le", leading_zeros=0, **header):
    frame = pack(dts_header_bits(**header), width, order)
    return make_wav(path, b"\x00" * leading_zeros + frame + b"\x00" * 8192)


@pytest.mark.parametrize("width,order", [(14, "le"), (14, "be"), (16, "le"), (16, "be")])
def test_detects_every_dts_packing(tmp_path, width, order):
    f = make_dts_wav(tmp_path / "a.wav", width, order)
    assert tag_editor.wav_dts_info(str(f)) == {"channels": 7}  # 5 kênh + LFE + XCh (6.1)


def test_channels_from_header(tmp_path):
    f = make_dts_wav(tmp_path / "a.wav", amode=9, lfe=True, xch=False)
    assert tag_editor.wav_dts_info(str(f)) == {"channels": 6}  # 5.1
    f = make_dts_wav(tmp_path / "b.wav", amode=2, lfe=False, xch=False)
    assert tag_editor.wav_dts_info(str(f)) == {"channels": 2}


def test_dts_after_leading_silence(tmp_path):
    f = make_dts_wav(tmp_path / "a.wav", leading_zeros=4096)
    assert tag_editor.wav_dts_info(str(f)) == {"channels": 7}


def test_plain_pcm_is_not_dts(tmp_path):
    pcm = b"".join(
        struct.pack("<hh", (i * 37) % 2000 - 1000, (i * 53) % 2000 - 1000) for i in range(4000)
    )
    f = make_wav(tmp_path / "pcm.wav", pcm)
    assert tag_editor.wav_dts_info(str(f)) is None
    silent = make_wav(tmp_path / "silent.wav", b"\x00" * 8000)
    assert tag_editor.wav_dts_info(str(silent)) is None


def test_not_a_wav(tmp_path):
    f = tmp_path / "x.wav"
    f.write_bytes(b"ID3" + b"\x00" * 100)
    assert tag_editor.wav_dts_info(str(f)) is None
    assert tag_editor.wav_dts_info(str(tmp_path / "missing.wav")) is None


def test_read_file_reports_dts(tmp_path):
    info = tag_editor.read_file(str(make_dts_wav(tmp_path / "a.wav")))
    assert info["codec"] == "DTS"
    assert info["channels"] == 7
    assert info["bits_per_sample"] == 0  # DTS nén mất dữ liệu: 16 bit chỉ là vỏ PCM
    pcm = make_wav(tmp_path / "pcm.wav", b"\x01\x02" * 4000)
    assert tag_editor.read_file(str(pcm))["codec"] == "PCM"


def test_dts_wav_is_browser_unsupported(tmp_path):
    dts = make_dts_wav(tmp_path / "a.wav")
    pcm = make_wav(tmp_path / "pcm.wav", b"\x01\x02" * 4000)
    assert converter.is_browser_unsupported(str(dts), "WAV audio file") is True
    assert converter.is_browser_unsupported(str(pcm), "WAV audio file") is False


def test_stream_transcode_downmixes_to_stereo():
    cmd = converter.build_command("ffmpeg", "in.wav", "out.flac", "flac", {"channels": 2}, {})
    assert cmd[cmd.index("-ac") + 1] == "2"
    assert "-ac" not in converter.build_command("ffmpeg", "in.wav", "o.flac", "flac", {}, {})
