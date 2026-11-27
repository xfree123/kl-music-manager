// Icon SVG sprite: đổi icon qua <use href>, icon loa theo âm lượng.
const test = require('node:test');
const assert = require('node:assert/strict');

const I = require('../../static/js/icons.js');

function fakeSvg() {
    const attrs = {};
    const use = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
    return {
        use,
        attrs,
        querySelector: sel => (sel === 'use' ? use : null),
        setAttribute(k, v) { attrs[k] = v; },
    };
}

test('href points into the sprite', () => {
    assert.equal(I.href('play'), 'icons/sprite.svg#play');
});

test('set swaps the <use> target and records the name', () => {
    const svg = fakeSvg();
    I.set(svg, 'pause');
    assert.equal(svg.use.attrs.href, 'icons/sprite.svg#pause');
    assert.equal(svg.attrs['data-icon'], 'pause');
});

test('set ignores a missing element', () => {
    assert.doesNotThrow(() => I.set(null, 'play'));
});

test('volumeIcon thresholds', () => {
    assert.equal(I.volumeIcon(0), 'volume-x');
    assert.equal(I.volumeIcon(0.2), 'volume');
    assert.equal(I.volumeIcon(0.5), 'volume-1');
    assert.equal(I.volumeIcon(1), 'volume-2');
});
