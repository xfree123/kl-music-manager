// Tìm kiếm thư viện: không phân biệt dấu tiếng Việt, nhiều từ = AND, nhiều trường.
const test = require('node:test');
const assert = require('node:assert/strict');

const S = require('../../static/js/search.js');

const TRACKS = [
    { id: 1, title: 'Tình thôi xót xa', artist: 'Hồng Nhung', album: 'Nghe Mưa', genre: 'Nhạc Việt', album_artist: '', composer: 'Trịnh Công Sơn' },
    { id: 2, title: 'Without you', artist: 'Mariah Carey', album: 'Hotel California Disk 2', genre: 'Ballad', album_artist: '', composer: '' },
    { id: 3, title: 'Đêm đông', artist: 'Thanh Lam', album: 'Đường xa', genre: 'Nhạc Việt', album_artist: 'Various', composer: 'Nguyễn Văn Thương' },
];

test('normalize strips Vietnamese diacritics and đ', () => {
    assert.equal(S.normalize('Hồng Nhung'), 'hong nhung');
    assert.equal(S.normalize('ĐÊM ĐÔNG'), 'dem dong');
    assert.equal(S.normalize('  Tình   thôi  '), 'tinh thoi');
    assert.equal(S.normalize(null), '');
});

test('query without accents matches accented text', () => {
    assert.deepEqual(S.search(TRACKS, 'hong nhung').map(t => t.id), [1]);
    assert.deepEqual(S.search(TRACKS, 'dem dong').map(t => t.id), [3]);
});

test('accented query matches too', () => {
    assert.deepEqual(S.search(TRACKS, 'Đường').map(t => t.id), [3]);
});

test('multiple words are AND across fields', () => {
    assert.deepEqual(S.search(TRACKS, 'nhac viet thanh').map(t => t.id), [3]);
    assert.deepEqual(S.search(TRACKS, 'carey ballad').map(t => t.id), [2]);
    assert.deepEqual(S.search(TRACKS, 'carey viet').map(t => t.id), []);
});

test('searches composer and album artist', () => {
    assert.deepEqual(S.search(TRACKS, 'trinh cong son').map(t => t.id), [1]);
    assert.deepEqual(S.search(TRACKS, 'various').map(t => t.id), [3]);
});

test('empty query returns everything (same order)', () => {
    assert.deepEqual(S.search(TRACKS, '   ').map(t => t.id), [1, 2, 3]);
});

test('prebuilt index gives the same result and is reused', () => {
    const index = S.buildIndex(TRACKS);
    assert.equal(index.size, 3);
    assert.deepEqual(S.search(TRACKS, 'mua', index).map(t => t.id), [1]);
});
