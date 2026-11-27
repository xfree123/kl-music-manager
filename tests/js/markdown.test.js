// Markdown tối giản cho trang Help: an toàn (escape HTML), đủ cú pháp cho hướng dẫn.
const test = require('node:test');
const assert = require('node:assert/strict');

const { render, slug } = require('../../static/js/markdown.js');

test('headings get ids for the table of contents', () => {
    const { html, toc } = render('# Title\n\n## Bắt đầu nhanh\n\n### Sub');
    assert.match(html, /<h1 id="title">Title<\/h1>/);
    assert.match(html, /<h2 id="bat-dau-nhanh">Bắt đầu nhanh<\/h2>/);
    assert.deepEqual(toc, [{ id: 'bat-dau-nhanh', text: 'Bắt đầu nhanh' }]);
});

test('explicit anchors {#id}', () => {
    const { html, toc } = render('## Phím tắt {#shortcuts}');
    assert.match(html, /<h2 id="shortcuts">Phím tắt<\/h2>/);
    assert.equal(toc[0].id, 'shortcuts');
});

test('escapes HTML everywhere', () => {
    const { html } = render('Hello <script>alert(1)</script> & **<b>x</b>**');
    assert.ok(!html.includes('<script>'));
    assert.match(html, /&lt;script&gt;/);
    assert.match(html, /<strong>&lt;b&gt;x&lt;\/b&gt;<\/strong>/);
});

test('inline code, bold, italic, links', () => {
    const { html } = render('Use `npm start`, **bold**, *it* and [docs](https://example.com) or [x](javascript:alert(1)).');
    assert.match(html, /<code>npm start<\/code>/);
    assert.match(html, /<strong>bold<\/strong>/);
    assert.match(html, /<em>it<\/em>/);
    assert.match(html, /<a href="https:\/\/example.com" target="_blank" rel="noopener">docs<\/a>/);
    assert.ok(!html.includes('javascript:'), 'unsafe link dropped');
});

test('lists (bulleted and numbered)', () => {
    const { html } = render('- a\n- b\n\n1. one\n2. two');
    assert.match(html, /<ul><li>a<\/li><li>b<\/li><\/ul>/);
    assert.match(html, /<ol><li>one<\/li><li>two<\/li><\/ol>/);
});

test('tables', () => {
    const { html } = render('| Key | Action |\n|---|---|\n| Space | Play `x` |');
    assert.match(html, /<table><thead><tr><th>Key<\/th><th>Action<\/th><\/tr><\/thead><tbody><tr><td>Space<\/td><td>Play <code>x<\/code><\/td><\/tr><\/tbody><\/table>/);
});

test('code block is not formatted', () => {
    const { html } = render('```\n**not bold** <x>\n```');
    assert.match(html, /<pre><code>\*\*not bold\*\* &lt;x&gt;<\/code><\/pre>/);
});

test('blockquote and paragraphs', () => {
    const { html } = render('> Lưu ý: backup iPod\n\nĐoạn một\ndòng hai\n\nĐoạn hai');
    assert.match(html, /<blockquote><p>Lưu ý: backup iPod<\/p><\/blockquote>/);
    assert.match(html, /<p>Đoạn một dòng hai<\/p>/);
    assert.match(html, /<p>Đoạn hai<\/p>/);
});

test('slug strips Vietnamese accents', () => {
    assert.equal(slug('Nhập nhạc & Playlist'), 'nhap-nhac-playlist');
});
