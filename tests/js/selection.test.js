// Chọn nhiều bài (trang Manage): nhóm kèm id, trạng thái nhóm, chọn dải, thứ tự export, hàng đợi.
const test = require('node:test');
const assert = require('node:assert/strict');

const S = require('../../static/js/selection.js');

const TRACKS = [
    { id: 1, title: 'Mưa', artist: 'Hồng Nhung', album: 'Nghe Mưa', genre: 'Pop', track_number: 2, disc_number: 1 },
    { id: 2, title: 'Gió', artist: 'hong nhung', album: 'nghe mưa', genre: 'Pop', track_number: 1, disc_number: 1 },
    { id: 3, title: 'Nắng', artist: 'Thanh Lam', album: 'Đường xa', genre: 'Jazz', track_number: 1, disc_number: 2 },
    { id: 4, title: 'Sao', artist: 'Thanh Lam', album: 'Đường xa', genre: 'Jazz', track_number: 5, disc_number: 1 },
    { id: 5, title: 'Lẻ', artist: '', album: '', genre: '', track_number: 0, disc_number: 0 },
];
const PLAYLISTS = [
    { name: 'Library', is_master: true, track_ids: [1, 2, 3, 4, 5] },
    { name: 'Yêu thích', is_master: false, track_ids: [4, 1, 99] }, // 99: bài không còn
    { name: 'Trống', is_master: false, track_ids: [] },
];

test('groupMembers merges spellings and lists track ids', () => {
    const g = S.groupMembers(TRACKS, 'album');
    assert.deepEqual(g.map(x => [x.label, x.ids]), [['Đường xa', [3, 4]], ['Nghe Mưa', [1, 2]]]);
    const a = S.groupMembers(TRACKS, 'artist');
    assert.deepEqual(a.map(x => [x.label, x.ids.length]), [['Hồng Nhung', 2], ['Thanh Lam', 2]]);
});

test('playlist groups skip master, empty lists and missing tracks', () => {
    const g = S.groupMembers(TRACKS, 'playlist', PLAYLISTS);
    assert.deepEqual(g, [{ key: 'Yêu thích', label: 'Yêu thích', ids: [4, 1] }]);
});

test('groupState and toggleGroup', () => {
    const sel = new Set([1]);
    assert.equal(S.groupState([1, 2], sel), 'some');
    assert.equal(S.groupState([3, 4], sel), 'none');
    assert.equal(S.groupState([], sel), 'none');
    S.toggleGroup(sel, [1, 2]); // một phần -> chọn hết
    assert.equal(S.groupState([1, 2], sel), 'all');
    S.toggleGroup(sel, [1, 2]); // đủ -> bỏ hết
    assert.deepEqual([...sel], []);
});

test('rangeIds selects between anchor and target in display order', () => {
    const order = [5, 3, 1, 4, 2];
    assert.deepEqual(S.rangeIds(order, 3, 4), [3, 1, 4]);
    assert.deepEqual(S.rangeIds(order, 2, 1), [1, 4, 2]);
    assert.deepEqual(S.rangeIds(order, 42, 4), [4]); // anchor không còn hiển thị
});

test('exportOrder sorts by artist, album, disc, track', () => {
    const sel = new Set([5, 4, 3, 2, 1]);
    assert.deepEqual(S.exportOrder(TRACKS, sel).map(t => t.id), [5, 2, 1, 4, 3]);
    assert.deepEqual(S.exportOrder(TRACKS, new Set([3, 1])).map(t => t.id), [1, 3]);
});

test('workerCount: iPod always 1, folders 1-4', () => {
    assert.equal(S.workerCount('ipod', 4, 16), 1);
    assert.equal(S.workerCount('folder', 0, 16), 4); // 0 = tự động
    assert.equal(S.workerCount('folder', 0, 2), 2);
    assert.equal(S.workerCount('folder', 0, undefined), 2);
    assert.equal(S.workerCount('folder', 9, 16), 4);
    assert.equal(S.workerCount('folder', 3, 1), 3); // người dùng chọn thì theo người dùng
});

test('summarize counts results', () => {
    const r = [{ status: 'done' }, { status: 'skipped' }, { status: 'failed' }, { status: 'done' }];
    assert.deepEqual(S.summarize(r), { done: 2, skipped: 1, failed: 1, total: 4 });
});

test('runQueue runs with limited concurrency, keeps order of results, stops on cancel', async () => {
    let running = 0;
    let peak = 0;
    const seen = [];
    const job = async item => {
        running++;
        peak = Math.max(peak, running);
        await new Promise(r => setTimeout(r, item === 2 ? 15 : 5));
        running--;
        seen.push(item);
        if (item === 3) throw new Error('boom');
        return item * 10;
    };
    const progress = [];
    const results = await S.runQueue([1, 2, 3, 4, 5], job, { concurrency: 2, onProgress: p => progress.push(p.finished) });
    assert.equal(peak, 2);
    assert.deepEqual(results.map(r => r.status), ['done', 'done', 'failed', 'done', 'done']);
    assert.equal(results[2].error.message, 'boom');
    assert.equal(results[4].value, 50);
    assert.deepEqual(progress, [1, 2, 3, 4, 5]);

    const token = { cancelled: false };
    const started = [];
    const res2 = await S.runQueue([1, 2, 3, 4, 5, 6], async item => {
        started.push(item);
        if (item === 2) token.cancelled = true;
        return item;
    }, { concurrency: 1, cancel: token });
    assert.deepEqual(started, [1, 2]);
    assert.deepEqual(res2.map(r => r.status), ['done', 'done', 'cancelled', 'cancelled', 'cancelled', 'cancelled']);
});
