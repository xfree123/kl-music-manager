// Nhiều thư viện (mỗi thư viện = 1 thư mục, metadata trong SQLite) + hộp Libraries & Maintenance.
// Dùng state / showModal / closeModal / setStatus / errorText (app.js), reloadLibrary (library-ui.js).

state.libraries = [];

function formatBytes(bytes) {
    return KlmmTrackInfo.formatSize(bytes) || '0 KB';
}

function formatWhen(iso) {
    if (!iso) return 'never';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

async function fetchLibraries() {
    try {
        const [libsRes, srcRes] = await Promise.all([fetch('/api/libraries'), fetch('/api/library/source')]);
        state.libraries = libsRes.ok ? await libsRes.json() : [];
        state.sourceInfo = srcRes.ok ? await srcRes.json() : null;
    } catch (e) {
        console.warn('Cannot load libraries', e);
        state.libraries = [];
    }
    renderLibrarySidebar();
    if (typeof onLibrariesChanged === 'function') onLibrariesChanged(); // js/manage.js
    return state.libraries;
}

// Thư viện mặc định (iPod ảo) đang mở?
function defaultLibraryActive() {
    return Boolean(state.sourceInfo && state.sourceInfo.is_default);
}

// Có iPod thật để hiện mục "iPod": đang cắm, hoặc đang mở (đường dẫn cấu hình)
function physicalIpodShown() {
    const info = state.sourceInfo || {};
    return (info.connected_ipods || []).length > 0 || (info.source === 'ipod' && !info.is_default);
}

function openDefaultLibrary() {
    return applySource('default', '');
}

// Danh sách bài/playlist của thư viện đang mở được tải lại mà không dừng nhạc
async function refreshLibraryData() {
    await Promise.all([fetchDevice(), fetchTracks(), fetchPlaylists(), fetchLibraries()]);
}

function renderLibrarySidebar() {
    const list = document.getElementById('library-list');
    if (!list) return;
    const info = state.sourceInfo || {};
    const defaultActive = defaultLibraryActive();
    const ipodActive = info.source === 'ipod' && !defaultActive;
    const items = [];
    // Không có nút gỡ ở sidebar (tránh bấm nhầm): gỡ thư viện ở trang Manage
    const def = document.createElement('li');
    def.className = defaultActive ? 'active' : '';
    def.title = 'Default library: an empty virtual iPod on this computer, always available';
    def.append(sidebarIcon('hard-drive'), labelSpan('Default library'));
    def.addEventListener('click', () => {
        if (!defaultActive) openDefaultLibrary();
    });
    items.push(def);
    if (physicalIpodShown()) {
        const ipod = document.createElement('li');
        ipod.className = ipodActive ? 'active' : '';
        ipod.title = `iPod${(info.connected_ipods || []).length ? `: ${info.connected_ipods.join(', ')}` : ''}`;
        ipod.append(sidebarIcon('smartphone'), labelSpan('iPod'));
        ipod.addEventListener('click', () => {
            if (!ipodActive) applySource('ipod', '');
        });
        items.push(ipod);
    }
    for (const lib of state.libraries) {
        const li = document.createElement('li');
        li.classList.toggle('active', lib.active);
        li.classList.toggle('unavailable', !lib.available);
        li.title = lib.available ? `${lib.root}\n${lib.track_count} tracks` : `${lib.root}\nFolder not found`;
        const count = document.createElement('span');
        count.className = 'library-count';
        count.textContent = lib.track_count;
        li.append(sidebarIcon(lib.available ? 'folder' : 'folder-open'), labelSpan(lib.name), count);
        li.addEventListener('click', () => {
            if (!lib.active && lib.available) openLibrary(lib.id);
        });
        items.push(li);
    }
    list.replaceChildren(...items);
}

function sidebarIcon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'icon sidebar-icon');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    svg.appendChild(use);
    setIcon(svg, name);
    return svg;
}

function labelSpan(text) {
    const span = document.createElement('span');
    span.className = 'library-name';
    span.textContent = text;
    return span;
}

async function postJson(url, body, method = 'POST') {
    const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await errorText(res));
    return res.json();
}

async function openLibrary(id) {
    try {
        await postJson(`/api/libraries/${id}/open`);
        await reloadLibrary();
    } catch (e) {
        alert(`Cannot open library: ${e.message}`);
    }
    await fetchLibraries();
}

// ---------------------------------------------------------------- hộp Libraries & Maintenance
const maintStatus = () => document.getElementById('maintenance-status');

async function openLibrariesModal(section = 'libraries') {
    setStatus(maintStatus(), '');
    document.getElementById('lib-new-name').value = '';
    document.getElementById('lib-new-root').value = '';
    showModal('libraries-modal');
    await renderMaintenance();
    document.getElementById(`${section}-section`).scrollIntoView({ block: 'start' });
}

async function renderMaintenance() {
    let info;
    try {
        const res = await fetch('/api/maintenance');
        info = await res.json();
    } catch (e) {
        setStatus(maintStatus(), `Cannot load: ${e}`, 'error');
        return;
    }
    state.libraries = info.libraries;
    renderLibrarySidebar();
    const stats = document.getElementById('maintenance-stats');
    const rows = [
        ['Library database', `${formatBytes(info.db_bytes)} · ${info.libraries.reduce((n, l) => n + l.track_count, 0)} indexed tracks`],
        ['Album art cache', `${info.artwork_cache_items} images in memory`],
        ['Streaming cache', formatBytes(info.stream_cache_bytes)],
    ];
    stats.replaceChildren(...rows.map(([k, v]) => {
        const div = document.createElement('div');
        const b = document.createElement('b');
        b.textContent = k;
        const span = document.createElement('span');
        span.textContent = v;
        div.append(b, span);
        return div;
    }));
    renderLibraryManageList(info.libraries);
}

function actionButton(label, icon, handler, cls = 'secondary') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn ${cls} small`;
    btn.append(sidebarIcon(icon), document.createTextNode(` ${label}`));
    btn.querySelector('svg').setAttribute('class', 'icon');
    btn.addEventListener('click', handler);
    return btn;
}

function renderLibraryManageList(libs) {
    const list = document.getElementById('library-manage-list');
    if (!libs.length) {
        const li = document.createElement('li');
        li.className = 'empty';
        li.textContent = 'No libraries yet. Add a music folder above.';
        list.replaceChildren(li);
        return;
    }
    list.replaceChildren(...libs.map(lib => {
        const li = document.createElement('li');
        li.classList.toggle('active', lib.active);
        const head = document.createElement('div');
        head.className = 'lib-head';
        const name = document.createElement('input');
        name.type = 'text';
        name.value = lib.name;
        name.title = 'Rename: edit and press Enter';
        name.addEventListener('keydown', e => {
            if (e.key === 'Enter') renameLibrary(lib.id, name.value);
        });
        name.addEventListener('change', () => renameLibrary(lib.id, name.value));
        const badge = document.createElement('span');
        badge.className = 'lib-badge';
        badge.textContent = lib.active ? 'Open' : lib.available ? '' : 'Folder missing';
        head.append(name, badge);
        const meta = document.createElement('div');
        meta.className = 'lib-meta';
        meta.textContent = `${lib.root} · ${lib.track_count} tracks · last scan: ${formatWhen(lib.last_scan)}`;
        const actions = document.createElement('div');
        actions.className = 'lib-actions';
        if (!lib.active && lib.available) actions.append(actionButton('Open', 'folder-open', () => openLibraryFromModal(lib.id), 'primary'));
        if (lib.available) {
            actions.append(
                actionButton('Rescan', 'refresh-cw', () => runLibraryAction(lib, 'scan')),
                actionButton('Rebuild', 'rotate-cw', () => runLibraryAction(lib, 'rebuild')),
            );
        }
        actions.append(actionButton('Clear', 'eraser', () => runLibraryAction(lib, 'clear')));
        // Gỡ thư viện chỉ có ở trang Manage (tránh bấm nhầm)
        li.append(head, meta, actions);
        return li;
    }));
}

function statsText(r) {
    return `${r.total} tracks (${r.added} added, ${r.changed} updated, ${r.removed} removed)`;
}

async function withBusy(message, fn) {
    const modal = document.getElementById('libraries-modal');
    modal.classList.add('busy');
    modal.querySelectorAll('button').forEach(b => { b.disabled = true; });
    setStatus(maintStatus(), message);
    try {
        return await fn();
    } catch (e) {
        setStatus(maintStatus(), e.message, 'error');
        return null;
    } finally {
        modal.classList.remove('busy');
        modal.querySelectorAll('button').forEach(b => { b.disabled = false; });
    }
}

async function runLibraryAction(lib, action) {
    if (action === 'clear' && !confirm(`Delete the indexed metadata of "${lib.name}"? Your music files are not changed; the folder is read again on the next scan.`)) return;
    if (action === 'rebuild' && !confirm(`Re-read the tags of every file in "${lib.name}"? This can take a while for large folders.`)) return;
    const verb = { scan: 'Rescanning', rebuild: 'Rebuilding', clear: 'Clearing' }[action];
    const r = await withBusy(`${verb} "${lib.name}"…`, () => postJson(`/api/libraries/${lib.id}/${action}`));
    if (!r) return;
    setStatus(maintStatus(), action === 'clear' && !r.active ? `Cleared "${lib.name}".` : `${lib.name}: ${statsText(r)}`, 'ok');
    if (r.active) await refreshLibraryData();
    await renderMaintenance();
}

async function renameLibrary(id, name) {
    try {
        await postJson(`/api/libraries/${id}`, { name: name.trim() }, 'PUT');
        await fetchLibraries();
    } catch (e) {
        setStatus(maintStatus(), e.message, 'error');
    }
}

async function openLibraryFromModal(id) {
    await withBusy('Opening…', async () => {
        await postJson(`/api/libraries/${id}/open`);
        await reloadLibrary();
    });
    await renderMaintenance();
}

async function addLibrary() {
    const nameEl = document.getElementById('lib-new-name');
    const root = document.getElementById('lib-new-root').value.trim();
    const name = nameEl.value.trim() || root.split(/[\\/]/).filter(Boolean).pop() || '';
    if (!root) {
        setStatus(maintStatus(), 'Choose a folder first.', 'error');
        return;
    }
    const r = await withBusy(`Scanning "${root}"…`, () => postJson('/api/libraries', { name, root }));
    if (!r) return;
    setStatus(maintStatus(), `Added "${r.library.name}": ${r.library.track_count} tracks.`, 'ok');
    document.getElementById('lib-new-name').value = '';
    document.getElementById('lib-new-root').value = '';
    await renderMaintenance();
}

async function rescanAll() {
    const r = await withBusy('Rescanning all libraries…', () => postJson('/api/libraries/rescan', {}));
    if (!r) return;
    setStatus(maintStatus(), `${r.libraries} libraries: ${statsText(r)}`, 'ok');
    if (r.active_changed) await refreshLibraryData();
    await renderMaintenance();
}

async function clearCache() {
    const r = await withBusy('Clearing cache…', () => postJson('/api/maintenance/clear-cache'));
    if (!r) return;
    state.artVersion = (state.artVersion || 0) + 1;
    setStatus(maintStatus(), `Freed ${formatBytes(r.freed_bytes)}.`, 'ok');
    await renderMaintenance();
}

async function addLibraryQuick() {
    if (window.klmm) {
        const folder = await window.klmm.selectFolder();
        if (!folder) return;
        await openLibrariesModal('libraries');
        document.getElementById('lib-new-root').value = folder;
        await addLibrary();
    } else {
        await openLibrariesModal('libraries');
        document.getElementById('lib-new-root').focus();
    }
}

function setupLibraries() {
    const onClick = (id, fn) =>
        document.getElementById(id).addEventListener('click', e => {
            e.preventDefault();
            fn();
        });
    onClick('manage-libraries-btn', () => openLibrariesModal('libraries'));
    onClick('add-library-btn', addLibraryQuick);
    onClick('tool-libraries', () => openLibrariesModal('libraries'));
    onClick('tool-maintenance', () => openLibrariesModal('maintenance'));
    onClick('lib-new-add', addLibrary);
    onClick('maint-rescan-all', rescanAll);
    onClick('maint-clear-cache', clearCache);
    onClick('lib-new-browse', async () => {
        const folder = window.klmm ? await window.klmm.selectFolder() : '';
        if (folder) document.getElementById('lib-new-root').value = folder;
    });
    document.getElementById('lib-new-root').addEventListener('keydown', e => {
        if (e.key === 'Enter') addLibrary();
    });
    fetchLibraries();
}

window.klmmUI = Object.assign(window.klmmUI || {}, {
    openLibraries: () => openLibrariesModal('libraries'),
    openMaintenance: () => openLibrariesModal('maintenance'),
    // Electron gọi khi quét lúc máy rảnh làm đổi thư viện đang mở
    onLibraryRescanned: refreshLibraryData,
});
