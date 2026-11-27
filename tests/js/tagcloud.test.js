// Tag cloud: gom nhóm theo genre / artist / album / year / playlist, trọng số theo số bài, lọc bài.
const test = require('node:test');
const assert = require('node:assert/strict');

const C = require('../../static/js/tagcloud.js');

const TRACKS = [
    { id: 1, title: 'a', artist: 'Hồng Nhung', album: 'Nghe Mưa', genre: 'Nhạc Việt', year: 2001 },
    { id: 2, title: 'b', artist: 'hong nhung', album: 'Nghe Mưa', genre: 'nhạc việt', year: 2001 },
    { id: 3, title: 'c', artist: 'Hồng Nhung', album: 'Đường xa', genre: 'Nhạc Việt', year: 0 },
    { id: 4, title: 'd', artist: 'Thanh Lam', album: '', genre: 'Jazz', year: 1999 },
    { id: 5, title: 'e', artist: '', album: 'Unknown Album', genre: '', year: 1999 },
];

test('groups merge case and diacritics, keep most common spelling, skip empty', () => {
    const g = C.groups(TRACKS, 'artist');
    assert.deepEqual(g.map(x => [x.label, x.count]), [['Hồng Nhung', 3], ['Thanh Lam', 1]]);
});

test('placeholders and year 0 are skipped', () => {
    assert.deepEqual(C.groups(TRACKS, 'album').map(x => x.label), ['Đường xa', 'Nghe Mưa']);
    assert.deepEqual(C.groups(TRACKS, 'year').map(x => [x.label, x.count]), [['1999', 2], ['2001', 2]]);
});

test('genre counts and alphabetical order (Vietnamese-aware)', () => {
    assert.deepEqual(C.groups(TRACKS, 'genre').map(x => [x.label, x.count]), [['Jazz', 1], ['Nhạc Việt', 3]]);
});

test('weights scale 1..6 by log count; equal counts get 3', () => {
    const many = [];
    for (let i = 0; i < 100; i++) many.push({ id: i, genre: 'Pop' });
    for (let i = 0; i < 10; i++) many.push({ id: 100 + i, genre: 'Rock' });
    many.push({ id: 999, genre: 'Jazz' });
    const w = Object.fromEntries(C.groups(many, 'genre').map(x => [x.label, x.weight]));
    assert.deepEqual(w, { Jazz: 1, Pop: 6, Rock: 4 });
    assert.ok(C.groups(TRACKS, 'year').every(x => x.weight === 3));
});

test('limit keeps the biggest groups', () => {
    assert.deepEqual(C.groups(TRACKS, 'artist', { limit: 1 }).map(x => x.label), ['Hồng Nhung']);
});

test('playlist groups come from playlists (not the master)', () => {
    const pls = [
        { name: 'Library', is_master: true, track_ids: [1, 2, 3] },
        { name: 'Yêu thích', is_master: false, track_ids: [1, 4] },
        { name: 'Trống', is_master: false, track_ids: [] },
    ];
    const g = C.groups(TRACKS, 'playlist', { playlists: pls });
    assert.deepEqual(g.map(x => [x.label, x.count]), [['Yêu thích', 2]]);
});

test('matches filters tracks by group key', () => {
    const key = C.groups(TRACKS, 'artist')[0].key;
    assert.deepEqual(TRACKS.filter(t => C.matches(t, 'artist', key)).map(t => t.id), [1, 2, 3]);
    assert.deepEqual(TRACKS.filter(t => C.matches(t, 'year', '1999')).map(t => t.id), [4, 5]);
});
