// Thông tin file đang phát: định dạng codec / bitrate / sample rate / bit depth / kênh / dung lượng.
const test = require('node:test');
const assert = require('node:assert/strict');

const T = require('../../static/js/trackinfo.js');

test('sample rate in kHz', () => {
    assert.equal(T.formatSampleRate(44100), '44.1 kHz');
    assert.equal(T.formatSampleRate(48000), '48 kHz');
    assert.equal(T.formatSampleRate(96000), '96 kHz');
    assert.equal(T.formatSampleRate(0), '');
});

test('channels', () => {
    assert.equal(T.formatChannels(1), 'Mono');
    assert.equal(T.formatChannels(2), 'Stereo');
    assert.equal(T.formatChannels(6), '5.1');
    assert.equal(T.formatChannels(4), '4 ch');
    assert.equal(T.formatChannels(0), '');
});

test('file size', () => {
    assert.equal(T.formatSize(980 * 1024), '980 KB');
    assert.equal(T.formatSize(24.3 * 1024 * 1024), '24.3 MB');
    assert.equal(T.formatSize(1.2 * 1024 ** 3), '1.20 GB');
    assert.equal(T.formatSize(0), '');
});

test('summary of a lossless file', () => {
    const d = { codec: 'FLAC', bitrate_kbps: 1411, sample_rate: 44100, bits_per_sample: 16, channels: 2, file_size: 24.3 * 1024 * 1024 };
    assert.deepEqual(T.parts(d), ['FLAC', '1411 kbps', '44.1 kHz', '16-bit', 'Stereo', '24.3 MB']);
    assert.equal(T.summary(d), 'FLAC · 1411 kbps · 44.1 kHz · 16-bit · Stereo · 24.3 MB');
});

test('summary skips unknown parts (lossy, no bit depth)', () => {
    const d = { codec: 'MP3', bitrate_kbps: 320, sample_rate: 44100, bits_per_sample: 0, channels: 0, file_size: 0 };
    assert.equal(T.summary(d), 'MP3 · 320 kbps · 44.1 kHz');
    assert.equal(T.summary(null), '');
});

test('short form for the top bar', () => {
    const d = { codec: 'ALAC', bitrate_kbps: 900, sample_rate: 48000, bits_per_sample: 24, channels: 2, file_size: 10 };
    assert.equal(T.short(d), 'ALAC · 900 kbps · 48 kHz');
    assert.equal(T.short(undefined), '');
});
