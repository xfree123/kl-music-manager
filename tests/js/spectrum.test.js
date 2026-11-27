// Spectrum: chia dải tần log, mức từng dải, đỉnh rơi chậm.
const test = require('node:test');
const assert = require('node:assert/strict');

const Sp = require('../../static/js/spectrum.js');

test('logBands covers 20 Hz..20 kHz with monotonic non-empty bands', () => {
    const bins = 2048; // fftSize 4096
    const bands = Sp.logBands(bins, 44100, 64);
    assert.equal(bands.length, 64);
    const hzPerBin = 44100 / 2 / bins;
    assert.ok(bands[0][0] * hzPerBin <= 25, 'starts near 20 Hz');
    assert.ok(bands[63][1] * hzPerBin >= 19000, 'ends near 20 kHz');
    for (let i = 0; i < bands.length; i++) {
        const [s, e] = bands[i];
        assert.ok(e > s, `band ${i} non-empty`);
        if (i > 0) assert.ok(s >= bands[i - 1][0], 'monotonic');
        assert.ok(e <= bins);
    }
    // log: dải thấp hẹp hơn dải cao
    assert.ok(bands[5][1] - bands[5][0] < bands[60][1] - bands[60][0]);
});

test('bandLevels takes the max in each band, scaled 0..1', () => {
    const data = new Uint8Array(8);
    data.set([0, 255, 10, 20, 128, 0, 0, 64]);
    const levels = Sp.bandLevels(data, [[0, 2], [2, 5], [5, 8]]);
    assert.deepEqual(levels.map(v => Math.round(v * 255)), [255, 128, 64]);
});

test('updatePeaks holds the max then decays', () => {
    let peaks = Sp.updatePeaks([0.8, 0.2], null, 0.1);
    assert.deepEqual(peaks, [0.8, 0.2]);
    peaks = Sp.updatePeaks([0.1, 0.5], peaks, 0.1);
    assert.equal(peaks[1], 0.5);
    assert.ok(Math.abs(peaks[0] - 0.7) < 1e-9);
    peaks = Sp.updatePeaks([0, 0], [0.05, 0], 0.1);
    assert.deepEqual(peaks, [0, 0]);
});
