// Tag cloud (trang Browse): gom bài theo genre / artist / album / year / playlist, trọng số 1–6
// theo log số bài. Gộp không phân biệt hoa thường / dấu; nhãn = cách viết gặp nhiều nhất.
// UMD: trình duyệt -> window.KlmmTagCloud; node (test) -> module.exports.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.KlmmTagCloud = factory();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const GROUPS = ['genre', 'artist', 'album', 'year', 'playlist'];
    // Giá trị giữ chỗ của iPod (ipod_manager.get_tracks) không phải nhóm thật
    const PLACEHOLDERS = new Set(['unknown artist', 'unknown album', 'unknown genre', 'unknown title']);
    const collator = typeof Intl !== 'undefined' ? new Intl.Collator('vi', { sensitivity: 'base', numeric: true }) : null;

    function normalize(text) {
        if (text === null || text === undefined) return '';
        return String(text)
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')
            .replace(/[đĐ]/g, 'd')
            .toLowerCase()
            .replace(/\s+/g, ' ')
            .trim();
    }

    /** Khoá nhóm của bài ('' = không thuộc nhóm nào). */
    function keyOf(track, by) {
        if (by === 'year') return track.year ? String(track.year) : '';
        const key = normalize(track[by]);
        return PLACEHOLDERS.has(key) ? '' : key;
    }

    function compareLabels(a, b) {
        return collator ? collator.compare(a, b) : a.localeCompare(b);
    }

    function weigh(groups) {
        if (!groups.length) return groups;
        const logs = groups.map(g => Math.log(g.count));
        const lo = Math.min(...logs);
        const hi = Math.max(...logs);
        for (let i = 0; i < groups.length; i++) {
            groups[i].weight = hi === lo ? 3 : 1 + Math.round((5 * (logs[i] - lo)) / (hi - lo));
        }
        return groups;
    }

    /**
     * @param tracks danh sách bài (state.tracks)
     * @param by 'genre' | 'artist' | 'album' | 'year' | 'playlist'
     * @param opts.playlists danh sách playlist (cho by='playlist'); opts.limit: giữ N nhóm lớn nhất
     * @returns [{key, label, count, weight}] theo thứ tự chữ cái
     */
    function groups(tracks, by, opts = {}) {
        let result;
        if (by === 'playlist') {
            result = (opts.playlists || [])
                .filter(p => !p.is_master && p.track_ids && p.track_ids.length)
                .map(p => ({ key: p.name, label: p.name, count: p.track_ids.length }));
        } else {
            const map = new Map();
            for (const t of tracks) {
                const key = keyOf(t, by);
                if (!key) continue;
                let g = map.get(key);
                if (!g) {
                    g = { key, count: 0, spellings: new Map() };
                    map.set(key, g);
                }
                g.count++;
                const label = by === 'year' ? key : String(t[by]).trim();
                g.spellings.set(label, (g.spellings.get(label) || 0) + 1);
            }
            result = [...map.values()].map(g => {
                let label = '';
                let best = -1;
                for (const [spelling, n] of g.spellings) {
                    if (n > best) {
                        best = n;
                        label = spelling;
                    }
                }
                return { key: g.key, label, count: g.count };
            });
        }
        if (opts.limit && result.length > opts.limit) {
            result.sort((a, b) => b.count - a.count || compareLabels(a.label, b.label));
            result = result.slice(0, opts.limit);
        }
        result.sort((a, b) => compareLabels(a.label, b.label));
        return weigh(result);
    }

    /** Bài có thuộc nhóm `key` không (không dùng cho playlist: lọc theo track_ids). */
    function matches(track, by, key) {
        return keyOf(track, by) === key;
    }

    return { GROUPS, normalize, keyOf, groups, matches };
});
