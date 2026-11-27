// Thông tin file đang phát: "FLAC · 1411 kbps · 44.1 kHz · 16-bit · Stereo · 24.3 MB".
// UMD: trình duyệt -> window.KlmmTrackInfo; node (test) -> module.exports.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.KlmmTrackInfo = factory();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    function formatSampleRate(hz) {
        if (!hz) return '';
        const khz = hz / 1000;
        return `${Number.isInteger(khz) ? khz : khz.toFixed(1)} kHz`;
    }

    function formatChannels(n) {
        if (!n) return '';
        if (n === 1) return 'Mono';
        if (n === 2) return 'Stereo';
        if (n === 6) return '5.1';
        if (n === 8) return '7.1';
        return `${n} ch`;
    }

    function formatSize(bytes) {
        if (!bytes) return '';
        const kb = bytes / 1024;
        if (kb < 1024) return `${Math.round(kb)} KB`;
        const mb = kb / 1024;
        if (mb < 1024) return `${mb.toFixed(1)} MB`;
        return `${(mb / 1024).toFixed(2)} GB`;
    }

    /** Các phần thông tin có giá trị, theo thứ tự hiển thị. */
    function parts(d) {
        if (!d) return [];
        return [
            d.codec || '',
            d.bitrate_kbps ? `${d.bitrate_kbps} kbps` : '',
            formatSampleRate(d.sample_rate),
            d.bits_per_sample ? `${d.bits_per_sample}-bit` : '',
            formatChannels(d.channels),
            formatSize(d.file_size),
        ].filter(Boolean);
    }

    function summary(d) {
        return parts(d).join(' · ');
    }

    /** Bản ngắn cho thanh trên: codec · bitrate · sample rate. */
    function short(d) {
        if (!d) return '';
        return [d.codec || '', d.bitrate_kbps ? `${d.bitrate_kbps} kbps` : '', formatSampleRate(d.sample_rate)]
            .filter(Boolean)
            .join(' · ');
    }

    return { formatSampleRate, formatChannels, formatSize, parts, summary, short };
});
