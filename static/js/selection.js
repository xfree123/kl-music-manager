// Chọn nhiều bài (trang Manage): nhóm kèm id bài (album / artist / genre / year / playlist, gộp
// giống trang Browse), trạng thái nhóm, chọn dải (Shift), thứ tự export, hàng đợi có giới hạn
// số việc chạy song song + Cancel.
// UMD: trình duyệt -> window.KlmmSelection (cần KlmmTagCloud nạp trước); node -> module.exports.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory(require('./tagcloud.js'));
    else root.KlmmSelection = factory(root.KlmmTagCloud);
})(typeof self !== 'undefined' ? self : this, function (TagCloud) {
    'use strict';

    const MAX_WORKERS = 4;
    const collator = typeof Intl !== 'undefined' ? new Intl.Collator('vi', { sensitivity: 'base', numeric: true }) : null;

    function compareText(a, b) {
        return collator ? collator.compare(a, b) : a.localeCompare(b);
    }

    /**
     * @returns [{key, label, ids}] theo thứ tự chữ cái; playlist giữ thứ tự bài của playlist,
     * bỏ playlist gốc (master), playlist rỗng và id không còn trong `tracks`.
     */
    function groupMembers(tracks, by, playlists) {
        if (by === 'playlist') {
            const known = new Set(tracks.map(t => t.id));
            return (playlists || [])
                .filter(p => !p.is_master)
                .map(p => ({ key: p.name, label: p.name, ids: (p.track_ids || []).filter(id => known.has(id)) }))
                .filter(g => g.ids.length)
                .sort((a, b) => compareText(a.label, b.label));
        }
        const ids = new Map();
        for (const t of tracks) {
            const key = TagCloud.keyOf(t, by);
            if (!key) continue;
            if (!ids.has(key)) ids.set(key, []);
            ids.get(key).push(t.id);
        }
        // Nhãn = cách viết gặp nhiều nhất (cùng quy tắc với trang Browse)
        return TagCloud.groups(tracks, by).map(g => ({ key: g.key, label: g.label, ids: ids.get(g.key) || [] }));
    }

    /** 'none' | 'some' | 'all' — trạng thái checkbox của một nhóm. */
    function groupState(ids, selected) {
        let n = 0;
        for (const id of ids) if (selected.has(id)) n++;
        if (!n) return 'none';
        return n === ids.length ? 'all' : 'some';
    }

    /** Nhóm đã chọn đủ -> bỏ hết; ngược lại -> chọn hết. Sửa trực tiếp `selected`. */
    function toggleGroup(selected, ids) {
        const all = groupState(ids, selected) === 'all';
        for (const id of ids) {
            if (all) selected.delete(id);
            else selected.add(id);
        }
        return selected;
    }

    /** Các id từ anchor tới target (gồm cả 2 đầu) theo thứ tự đang hiển thị. */
    function rangeIds(order, anchorId, targetId) {
        const a = order.indexOf(anchorId);
        const b = order.indexOf(targetId);
        if (b < 0) return [];
        if (a < 0) return [targetId];
        return order.slice(Math.min(a, b), Math.max(a, b) + 1);
    }

    function sortKey(t) {
        return TagCloud.normalize(t.album_artist || t.artist);
    }

    /** Bài đã chọn, sắp theo nghệ sĩ -> album -> đĩa -> số bài -> tên (thứ tự export). */
    function exportOrder(tracks, selected) {
        return tracks
            .filter(t => selected.has(t.id))
            .sort((a, b) =>
                compareText(sortKey(a), sortKey(b)) ||
                compareText(TagCloud.normalize(a.album), TagCloud.normalize(b.album)) ||
                (a.disc_number || 0) - (b.disc_number || 0) ||
                (a.track_number || 0) - (b.track_number || 0) ||
                compareText(String(a.title || ''), String(b.title || '')));
    }

    /**
     * Số bài export cùng lúc. iPod: luôn 1 (ổ USB chậm, đọc song song chỉ làm chậm thêm).
     * Thư mục: số người dùng chọn (1–4), 0 = tự động = min(4, số nhân CPU; không biết thì 2).
     */
    function workerCount(source, requested, hardware) {
        if (source !== 'folder') return 1;
        const n = requested > 0 ? requested : Math.min(MAX_WORKERS, hardware || 2);
        return Math.max(1, Math.min(MAX_WORKERS, Math.floor(n)));
    }

    function summarize(results) {
        const out = { done: 0, skipped: 0, failed: 0, total: results.length };
        for (const r of results) if (r.status in out) out[r.status]++;
        return out;
    }

    /**
     * Chạy `job(item, index)` cho từng item, tối đa `concurrency` việc cùng lúc.
     * Kết quả giữ thứ tự item: {status: 'done' | 'failed' | 'cancelled', value?, error?};
     * `job` có thể trả {skipped: true} -> status 'skipped'.
     * opts.cancel = {cancelled: bool}: đặt true -> không bắt đầu item mới (item đang chạy vẫn xong).
     * opts.onProgress({finished, total, index, result}) sau mỗi item.
     */
    async function runQueue(items, job, opts = {}) {
        const total = items.length;
        const results = new Array(total);
        const cancel = opts.cancel || { cancelled: false };
        let next = 0;
        let finished = 0;
        async function worker() {
            while (next < total && !cancel.cancelled) {
                const index = next++;
                let result;
                try {
                    const value = await job(items[index], index);
                    result = { status: value && value.skipped ? 'skipped' : 'done', value };
                } catch (error) {
                    result = { status: 'failed', error };
                }
                results[index] = result;
                finished++;
                if (opts.onProgress) opts.onProgress({ finished, total, index, result });
            }
        }
        const n = Math.max(1, Math.min(opts.concurrency || 1, total || 1));
        await Promise.all(Array.from({ length: n }, worker));
        for (let i = 0; i < total; i++) if (!results[i]) results[i] = { status: 'cancelled' };
        return results;
    }

    return { MAX_WORKERS, groupMembers, groupState, toggleGroup, rangeIds, exportOrder, workerCount, summarize, runQueue };
});
