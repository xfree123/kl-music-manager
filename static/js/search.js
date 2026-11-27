// Tìm kiếm thư viện: không phân biệt hoa thường / dấu tiếng Việt, nhiều từ = AND.
// UMD: trình duyệt -> window.KlmmSearch; node (test) -> module.exports.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.KlmmSearch = factory();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const FIELDS = ['title', 'artist', 'album', 'album_artist', 'genre', 'composer'];

    /** "Hồng Nhung" -> "hong nhung"; "Đêm" -> "dem". */
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

    function haystack(track) {
        return normalize(FIELDS.map(f => track[f] || '').join(' \u0001 '));
    }

    /** Map id -> chuỗi đã chuẩn hoá (dựng 1 lần mỗi khi danh sách bài đổi). */
    function buildIndex(tracks) {
        const index = new Map();
        for (const t of tracks) index.set(t.id, haystack(t));
        return index;
    }

    function search(tracks, query, index) {
        const terms = normalize(query).split(' ').filter(Boolean);
        if (terms.length === 0) return tracks.slice();
        return tracks.filter(t => {
            const hay = (index && index.get(t.id)) || haystack(t);
            return terms.every(term => hay.includes(term));
        });
    }

    return { normalize, buildIndex, search, FIELDS };
});
