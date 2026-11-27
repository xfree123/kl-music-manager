// Hàng đợi phát: next/prev, shuffle không lặp, repeat off/all/one, play next / add to queue.
const test = require('node:test');
const assert = require('node:assert/strict');

const { PlayQueue } = require('../../static/js/queue.js');

// RNG cố định để shuffle có thể kiểm
function seeded(seed) {
    let s = seed;
    return () => {
        s = (s * 1103515245 + 12345) % 2147483648;
        return s / 2147483648;
    };
}

test('plays through the list then stops (repeat off)', () => {
    const q = new PlayQueue();
    q.setList([1, 2, 3], 2);
    assert.equal(q.current(), 2);
    assert.equal(q.next(), 3);
    assert.equal(q.next(), null);
    assert.equal(q.current(), 3);
});

test('repeat all wraps around', () => {
    const q = new PlayQueue();
    q.setRepeat('all');
    q.setList([1, 2, 3], 3);
    assert.equal(q.next(), 1);
});

test('repeat one replays only on auto-advance', () => {
    const q = new PlayQueue();
    q.setRepeat('one');
    q.setList([1, 2, 3], 1);
    assert.equal(q.next({ auto: true }), 1);
    assert.equal(q.next(), 2); // bấm Next vẫn sang bài
});

test('cycleRepeat goes off -> all -> one -> off', () => {
    const q = new PlayQueue();
    assert.deepEqual([q.cycleRepeat(), q.cycleRepeat(), q.cycleRepeat()], ['all', 'one', 'off']);
});

test('prev goes back; at the start stays on first', () => {
    const q = new PlayQueue();
    q.setList([1, 2, 3], 3);
    assert.equal(q.prev(), 2);
    assert.equal(q.prev(), 1);
    assert.equal(q.prev(), 1);
});

test('shuffle visits every track exactly once, starting with the current one', () => {
    const q = new PlayQueue(seeded(7));
    q.setShuffle(true);
    q.setList([1, 2, 3, 4, 5, 6], 4);
    const seen = [q.current()];
    let id;
    while ((id = q.next()) !== null) seen.push(id);
    assert.equal(seen[0], 4);
    assert.deepEqual([...seen].sort(), [1, 2, 3, 4, 5, 6]);
    assert.notDeepEqual(seen, [4, 5, 6, 1, 2, 3]);
});

test('turning shuffle off resumes list order after the current track', () => {
    const q = new PlayQueue(seeded(3));
    q.setShuffle(true);
    q.setList([1, 2, 3, 4], 2);
    q.setShuffle(false);
    assert.equal(q.current(), 2);
    assert.equal(q.next(), 3);
});

test('play next and add to queue take priority, then the list continues', () => {
    const q = new PlayQueue();
    q.setList([1, 2, 3], 1);
    q.addToQueue(9);
    q.playNext(8);
    assert.deepEqual(q.upcoming(5), [8, 9, 2, 3]);
    assert.equal(q.next(), 8);
    assert.equal(q.next(), 9);
    assert.equal(q.next(), 2);
});

test('upcoming with repeat all wraps and is limited', () => {
    const q = new PlayQueue();
    q.setRepeat('all');
    q.setList([1, 2, 3], 2);
    assert.deepEqual(q.upcoming(4), [3, 1, 2, 3]);
});

test('removeFromQueue and jumpTo', () => {
    const q = new PlayQueue();
    q.setList([1, 2, 3, 4], 1);
    q.addToQueue(7);
    q.removeFromQueue(7);
    assert.deepEqual(q.upcoming(2), [2, 3]);
    assert.equal(q.jumpTo(3), 3);
    assert.equal(q.next(), 4);
});

test('empty list', () => {
    const q = new PlayQueue();
    assert.equal(q.current(), null);
    assert.equal(q.next(), null);
    assert.equal(q.prev(), null);
});
