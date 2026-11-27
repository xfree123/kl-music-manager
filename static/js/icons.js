// Icon giao diện: <svg class="icon"><use href="icons/sprite.svg#NAME"></use></svg> (Lucide, ISC).
// UMD: trình duyệt -> window.KlmmIcons + hàm global setIcon(svg, name); node (test) -> module.exports.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else {
        root.KlmmIcons = factory();
        root.setIcon = root.KlmmIcons.set;
    }
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const SPRITE = 'icons/sprite.svg';

    function href(name) {
        return `${SPRITE}#${name}`;
    }

    /** Đổi icon của một phần tử <svg class="icon"> đã có sẵn <use>. */
    function set(svg, name) {
        if (!svg) return;
        const use = svg.querySelector('use');
        if (use) use.setAttribute('href', href(name));
        svg.setAttribute('data-icon', name);
    }

    /** Icon loa theo âm lượng 0..1 (0 = tắt tiếng). */
    function volumeIcon(v) {
        if (v <= 0) return 'volume-x';
        if (v < 0.34) return 'volume';
        if (v < 0.67) return 'volume-1';
        return 'volume-2';
    }

    return { SPRITE, href, set, volumeIcon };
});
