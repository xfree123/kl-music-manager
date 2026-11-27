// Markdown tối giản cho trang Help (static/help/guide.*.md). An toàn: mọi văn bản được escape,
// link chỉ cho http(s)/#/đường dẫn tương đối. Hỗ trợ: # tiêu đề (+ {#id}), đoạn, - / 1. danh sách,
// | bảng |, ``` khối code ```, > trích dẫn, `code`, **đậm**, *nghiêng*, [link](url).
// UMD: trình duyệt -> window.KlmmMarkdown; node (test) -> module.exports.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.KlmmMarkdown = factory();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function slug(text) {
        return String(text)
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')
            .replace(/[đĐ]/g, 'd')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '');
    }

    function safeUrl(url) {
        return /^(https?:\/\/|#|\.{0,2}\/|[a-z0-9_.-]+(\.[a-z0-9]+)?(#.*)?$)/i.test(url) && !/^\s*javascript:/i.test(url);
    }

    // Inline: escape trước, rồi thay cú pháp (code được tách riêng để không bị định dạng)
    function inline(text) {
        const codes = [];
        let s = String(text).replace(/`([^`]+)`/g, (_, c) => {
            codes.push(`<code>${escapeHtml(c)}</code>`);
            return `\u0000${codes.length - 1}\u0000`;
        });
        s = escapeHtml(s);
        s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
            const raw = url.replace(/&amp;/g, '&');
            if (!safeUrl(raw)) return label;
            const external = /^https?:\/\//i.test(raw);
            return `<a href="${url}"${external ? ' target="_blank" rel="noopener"' : ''}>${label}</a>`;
        });
        s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
        return s.replace(/\u0000(\d+)\u0000/g, (_, i) => codes[Number(i)]);
    }

    function cells(line) {
        return line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
    }

    function render(markdown) {
        const lines = String(markdown).replace(/\r\n?/g, '\n').split('\n');
        const out = [];
        const toc = [];
        let i = 0;
        while (i < lines.length) {
            const line = lines[i];
            if (!line.trim()) {
                i++;
                continue;
            }
            if (line.startsWith('```')) {
                const code = [];
                i++;
                while (i < lines.length && !lines[i].startsWith('```')) code.push(lines[i++]);
                i++;
                out.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`);
                continue;
            }
            const h = /^(#{1,4})\s+(.*?)(?:\s+\{#([a-z0-9-]+)\})?\s*$/.exec(line);
            if (h) {
                const level = h[1].length;
                const id = h[3] || slug(h[2]);
                if (level === 2) toc.push({ id, text: h[2] });
                out.push(`<h${level} id="${id}">${inline(h[2])}</h${level}>`);
                i++;
                continue;
            }
            if (line.trim().startsWith('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
                const head = cells(line);
                i += 2;
                const rows = [];
                while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(cells(lines[i++]));
                out.push(
                    '<table><thead><tr>' + head.map(c => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>' +
                        rows.map(r => '<tr>' + r.map(c => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') +
                        '</tbody></table>',
                );
                continue;
            }
            const listType = /^\s*[-*]\s+/.test(line) ? 'ul' : /^\s*\d+\.\s+/.test(line) ? 'ol' : null;
            if (listType) {
                const pattern = listType === 'ul' ? /^\s*[-*]\s+/ : /^\s*\d+\.\s+/;
                const items = [];
                while (i < lines.length && pattern.test(lines[i])) items.push(lines[i++].replace(pattern, ''));
                out.push(`<${listType}>` + items.map(t => `<li>${inline(t)}</li>`).join('') + `</${listType}>`);
                continue;
            }
            if (line.startsWith('>')) {
                const quote = [];
                while (i < lines.length && lines[i].startsWith('>')) quote.push(lines[i++].replace(/^>\s?/, ''));
                out.push(`<blockquote><p>${inline(quote.join(' '))}</p></blockquote>`);
                continue;
            }
            const para = [];
            while (
                i < lines.length &&
                lines[i].trim() &&
                !/^(#{1,4}\s|```|>|\s*[-*]\s+|\s*\d+\.\s+|\s*\|)/.test(lines[i])
            ) {
                para.push(lines[i++].trim());
            }
            if (para.length) out.push(`<p>${inline(para.join(' '))}</p>`);
            else i++;
        }
        return { html: out.join('\n'), toc };
    }

    return { render, slug, escapeHtml };
});
