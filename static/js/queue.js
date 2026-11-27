// Hàng đợi phát: danh sách ngữ cảnh (view hiện tại) + hàng đợi tay ("Play next" / "Add to queue"),
// shuffle (hoán vị, không lặp), repeat off/all/one.
// UMD: trình duyệt -> window.KlmmQueue; node (test) -> module.exports.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.KlmmQueue = factory();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const REPEAT_MODES = ['off', 'all', 'one'];

    class PlayQueue {
        constructor(random = Math.random) {
            this.random = random;
            this.list = []; // id theo thứ tự view
            this.order = []; // thứ tự phát (= list, hoặc hoán vị khi shuffle)
            this.pos = -1; // vị trí trong order
            this.manual = []; // hàng đợi tay, ưu tiên trước order
            this.playingManual = null; // id đang phát lấy từ hàng đợi tay
            this.shuffle = false;
            this.repeat = 'off';
        }

        _shuffled(ids, first) {
            const rest = ids.filter(id => id !== first);
            for (let i = rest.length - 1; i > 0; i--) {
                const j = Math.floor(this.random() * (i + 1));
                [rest[i], rest[j]] = [rest[j], rest[i]];
            }
            return first === undefined || first === null ? rest : [first, ...rest];
        }

        /** Đặt danh sách ngữ cảnh và bài bắt đầu. */
        setList(ids, startId) {
            this.list = ids.slice();
            const start = ids.includes(startId) ? startId : ids[0];
            this.order = this.shuffle ? this._shuffled(this.list, start) : this.list.slice();
            this.pos = this.order.indexOf(start);
            this.playingManual = null;
            return this.current();
        }

        current() {
            if (this.playingManual !== null) return this.playingManual;
            return this.pos >= 0 && this.pos < this.order.length ? this.order[this.pos] : null;
        }

        _orderCurrent() {
            return this.pos >= 0 && this.pos < this.order.length ? this.order[this.pos] : null;
        }

        setShuffle(on) {
            this.shuffle = !!on;
            const cur = this._orderCurrent();
            this.order = this.shuffle ? this._shuffled(this.list, cur) : this.list.slice();
            this.pos = cur === null ? -1 : this.order.indexOf(cur);
            return this.shuffle;
        }

        setRepeat(mode) {
            if (REPEAT_MODES.includes(mode)) this.repeat = mode;
            return this.repeat;
        }

        cycleRepeat() {
            return this.setRepeat(REPEAT_MODES[(REPEAT_MODES.indexOf(this.repeat) + 1) % REPEAT_MODES.length]);
        }

        /** Bài kế. auto=true: tự chuyển khi hết bài (repeat one phát lại). null = hết danh sách. */
        next({ auto = false } = {}) {
            if (auto && this.repeat === 'one' && this.current() !== null) return this.current();
            if (this.manual.length) {
                this.playingManual = this.manual.shift();
                return this.playingManual;
            }
            this.playingManual = null;
            if (!this.order.length) return null;
            if (this.pos + 1 < this.order.length) {
                this.pos += 1;
                return this.order[this.pos];
            }
            if (this.repeat === 'all') {
                if (this.shuffle) this.order = this._shuffled(this.list, null);
                this.pos = 0;
                return this.order[0];
            }
            return null;
        }

        prev() {
            if (this.playingManual !== null) {
                this.playingManual = null;
                return this.current();
            }
            if (!this.order.length) return null;
            if (this.pos > 0) this.pos -= 1;
            else if (this.repeat === 'all') this.pos = this.order.length - 1;
            return this.order[this.pos];
        }

        /** Nhảy tới một bài trong danh sách (vd chọn từ Up Next). */
        jumpTo(id) {
            const i = this.order.indexOf(id);
            if (i < 0) return null;
            this.pos = i;
            this.playingManual = null;
            return id;
        }

        playNext(id) {
            this.manual.unshift(id);
        }

        addToQueue(id) {
            this.manual.push(id);
        }

        removeFromQueue(id) {
            const i = this.manual.indexOf(id);
            if (i >= 0) this.manual.splice(i, 1);
        }

        /** n bài sắp phát (hàng đợi tay rồi tới danh sách; repeat all thì quay vòng). */
        upcoming(n) {
            const out = this.manual.slice(0, n);
            let p = this.pos;
            while (out.length < n && this.order.length) {
                p += 1;
                if (p >= this.order.length) {
                    if (this.repeat !== 'all') break;
                    p = 0;
                }
                out.push(this.order[p]);
            }
            return out;
        }
    }

    return { PlayQueue, REPEAT_MODES };
});
