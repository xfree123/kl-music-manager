// Trang Manage: chọn nhiều bài (checkbox, Shift-click, cả album / nghệ sĩ / thể loại / playlist),
// export hàng loạt với 1 định dạng cho cả danh sách (hàng đợi; thư viện thư mục chạy song song),
// danh sách thư viện có nút gỡ (gỡ chỉ có ở đây, không có ở sidebar).
// Dùng state / fillSelect / formatItems / formatById / sampleRateItems / flacLevelItems / setStatus /
// errorText / showModal / closeModal / fetchSettings (app.js), postJson / fetchLibraries /
// openDefaultLibrary / addLibraryQuick / formatBytes (libraries.js), applySource / reloadLibrary
// (library-ui.js), showView (player.js), KlmmSelection / KlmmSearch / KlmmTrackInfo.

const manageState = {
    by: localStorage.getItem('manageBy') || 'album',
    selected: new Set(),
    anchor: null, // id bài bấm gần nhất (cho Shift-click)
    query: '',
    groupQuery: '',
    shownIds: [],
    lastGroup: null, // {label, ids}: nhóm vừa chọn (gợi ý tên thư mục con)
};
const batchState = { running: false, cancel: null, lastPath: '', root: '' };

const $m = id => document.getElementById(id);

function manageVisible() {
    return !$m('manage-view').hidden;
}

function knownIds() {
    return new Set(state.tracks.map(t => t.id));
}

// Bỏ id không còn (đổi thư viện, xoá bài)
function pruneSelection() {
    const known = knownIds();
    for (const id of [...manageState.selected]) if (!known.has(id)) manageState.selected.delete(id);
}

function renderManage() {
    if (!manageVisible()) return;
    pruneSelection();
    renderManageLibraries();
    renderManageGroups();
    renderManageTracks();
}

// ---------------------------------------------------------------- thư viện
function libItem({ name, detail, icon, active, unavailable, actions }) {
    const li = document.createElement('li');
    li.classList.toggle('active', Boolean(active));
    li.classList.toggle('unavailable', Boolean(unavailable));
    const text = document.createElement('div');
    text.className = 'manage-lib-text';
    const title = document.createElement('div');
    title.className = 'manage-lib-name';
    title.append(sidebarIcon(icon), document.createTextNode(` ${name}`));
    if (active) {
        const badge = document.createElement('span');
        badge.className = 'lib-badge';
        badge.textContent = 'Open';
        title.append(badge);
    }
    const sub = document.createElement('div');
    sub.className = 'manage-lib-detail';
    sub.textContent = detail;
    sub.title = detail;
    text.append(title, sub);
    const btns = document.createElement('div');
    btns.className = 'manage-lib-actions';
    btns.append(...actions);
    li.append(text, btns);
    return li;
}

function renderManageLibraries() {
    const info = state.sourceInfo || {};
    const defaultActive = defaultLibraryActive();
    const items = [];
    items.push(libItem({
        name: 'Default library',
        detail: 'Virtual iPod on this computer · cannot be removed',
        icon: 'hard-drive',
        active: defaultActive,
        actions: defaultActive ? [] : [actionButton('Open', 'folder-open', () => manageOpen(openDefaultLibrary), 'primary')],
    }));
    if (physicalIpodShown()) {
        const ipodActive = info.source === 'ipod' && !defaultActive;
        items.push(libItem({
            name: 'iPod',
            detail: (info.connected_ipods || []).join(', ') || info.mountpoint || '',
            icon: 'smartphone',
            active: ipodActive,
            actions: ipodActive ? [] : [actionButton('Open', 'folder-open', () => manageOpen(() => applySource('ipod', '')), 'primary')],
        }));
    }
    for (const lib of state.libraries) {
        const actions = [];
        if (!lib.active && lib.available) {
            actions.push(actionButton('Open', 'folder-open', () => manageOpen(async () => {
                await postJson(`/api/libraries/${lib.id}/open`);
                await reloadLibrary();
            }), 'primary'));
        }
        actions.push(actionButton('Remove', 'trash-2', () => removeLibraryFromApp(lib), 'danger'));
        items.push(libItem({
            name: lib.name,
            detail: `${lib.root} · ${lib.track_count} tracks${lib.available ? '' : ' · folder missing'}`,
            icon: lib.available ? 'folder' : 'folder-open',
            active: lib.active,
            unavailable: !lib.available,
            actions,
        }));
    }
    $m('manage-libs').replaceChildren(...items);
}

async function manageOpen(fn) {
    const status = $m('manage-lib-status');
    setStatus(status, 'Opening…');
    try {
        await fn();
        setStatus(status, '');
    } catch (e) {
        setStatus(status, `Cannot open: ${e.message || e}`, 'error');
    }
    await fetchLibraries();
}

async function removeLibraryFromApp(lib) {
    const extra = lib.active ? '\n\nIt is open now: the app switches to the Default library.' : '';
    if (!confirm(`Remove the library "${lib.name}" from the app?\n\nIts entry and indexed metadata are deleted. The folder and its music files are NOT deleted.${extra}`)) return;
    const status = $m('manage-lib-status');
    try {
        const r = await postJson(`/api/libraries/${lib.id}`, undefined, 'DELETE');
        if (r.switched) {
            manageState.selected.clear();
            await reloadLibrary();
        }
        setStatus(status, `Removed "${lib.name}". Music files were kept.`, 'ok');
    } catch (e) {
        setStatus(status, `Cannot remove: ${e.message}`, 'error');
    }
    await fetchLibraries();
}

// ---------------------------------------------------------------- nhóm (album / artist / genre / playlist)
function renderManageGroups() {
    const by = manageState.by;
    document.querySelectorAll('#manage-group-tabs .browse-tab').forEach(b => b.classList.toggle('active', b.dataset.by === by));
    const q = KlmmTagCloud.normalize(manageState.groupQuery);
    const groups = KlmmSelection.groupMembers(state.tracks, by, state.playlists)
        .filter(g => !q || KlmmTagCloud.normalize(g.label).includes(q));
    const list = $m('manage-groups');
    if (!groups.length) {
        const li = document.createElement('li');
        li.className = 'empty';
        li.textContent = q ? 'No match.' : by === 'playlist' ? 'No playlists with tracks.' : 'Nothing to group by.';
        list.replaceChildren(li);
        return;
    }
    list.replaceChildren(...groups.map(g => {
        const li = document.createElement('li');
        const box = document.createElement('input');
        box.type = 'checkbox';
        const st = KlmmSelection.groupState(g.ids, manageState.selected);
        box.checked = st === 'all';
        box.indeterminate = st === 'some';
        const label = document.createElement('span');
        label.className = 'manage-group-label';
        label.textContent = g.label;
        label.title = g.label;
        const count = document.createElement('span');
        count.className = 'library-count';
        count.textContent = g.ids.length;
        li.append(box, label, count);
        li.addEventListener('click', () => {
            KlmmSelection.toggleGroup(manageState.selected, g.ids);
            manageState.lastGroup = KlmmSelection.groupState(g.ids, manageState.selected) === 'all' ? g : null;
            renderManageGroups();
            renderManageTracks();
        });
        return li;
    }));
}

// ---------------------------------------------------------------- bảng bài
function shownTracks() {
    const q = manageState.query.trim();
    return q ? KlmmSearch.search(state.tracks, q) : state.tracks;
}

function extOf(track) {
    const m = /\.([a-z0-9]+)$/i.exec(track.file_path || '');
    return m ? m[1].toUpperCase() : '';
}

function durationText(s) {
    const sec = Math.max(0, Math.round(s || 0));
    return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}

function renderManageTracks() {
    const tracks = shownTracks();
    manageState.shownIds = tracks.map(t => t.id);
    const body = $m('manage-tbody');
    if (!tracks.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 6;
        td.className = 'loading-cell';
        td.textContent = state.tracks.length ? 'No tracks match the filter.' : 'This library has no tracks.';
        tr.appendChild(td);
        body.replaceChildren(tr);
    } else {
        body.replaceChildren(...tracks.map(t => {
            const tr = document.createElement('tr');
            tr.dataset.id = t.id;
            const on = manageState.selected.has(t.id);
            tr.classList.toggle('checked', on);
            const check = document.createElement('td');
            check.className = 'col-check';
            const box = document.createElement('input');
            box.type = 'checkbox';
            box.checked = on;
            box.tabIndex = -1;
            check.appendChild(box);
            tr.appendChild(check);
            for (const text of [t.title, t.artist, t.album, durationText(t.duration), extOf(t)]) {
                const td = document.createElement('td');
                td.textContent = text || '';
                td.title = text || '';
                tr.appendChild(td);
            }
            return tr;
        }));
    }
    updateManageCount();
}

function onTrackRowClick(e) {
    const tr = e.target.closest('tr[data-id]');
    if (!tr) return;
    const id = Number(tr.dataset.id);
    if (e.shiftKey && manageState.anchor !== null) {
        const ids = KlmmSelection.rangeIds(manageState.shownIds, manageState.anchor, id);
        const add = !manageState.selected.has(id) || manageState.selected.has(manageState.anchor);
        for (const x of ids) add ? manageState.selected.add(x) : manageState.selected.delete(x);
    } else if (manageState.selected.has(id)) {
        manageState.selected.delete(id);
    } else {
        manageState.selected.add(id);
    }
    manageState.anchor = id;
    manageState.lastGroup = null;
    renderManageTracks();
    renderManageGroups();
}

function updateManageCount() {
    const sel = manageState.selected;
    let bytes = 0;
    for (const t of state.tracks) if (sel.has(t.id)) bytes += t.file_size || 0;
    $m('manage-count').textContent = sel.size
        ? `${sel.size} selected${bytes ? ` · ${KlmmTrackInfo.formatSize(bytes)}` : ''}`
        : '0 selected';
    $m('manage-export').disabled = sel.size === 0;
    const shown = manageState.shownIds;
    const n = shown.filter(id => sel.has(id)).length;
    const all = $m('manage-check-all');
    all.checked = shown.length > 0 && n === shown.length;
    all.indeterminate = n > 0 && n < shown.length;
}

function selectShown(on) {
    for (const id of manageState.shownIds) on ? manageState.selected.add(id) : manageState.selected.delete(id);
    manageState.lastGroup = null;
    renderManageTracks();
    renderManageGroups();
}

// ---------------------------------------------------------------- hộp export hàng loạt
function batchTracks() {
    return KlmmSelection.exportOrder(state.tracks, manageState.selected);
}

function isFolderSource() {
    return Boolean(state.device && state.device.source === 'folder');
}

async function openBatchExport() {
    if (!manageState.selected.size) return;
    await fetchSettings();
    const s = state.settings;
    if (!s) return;
    const tracks = batchTracks();
    $m('bx-title').textContent = `Export ${tracks.length} Track${tracks.length === 1 ? '' : 's'}`;
    $m('bx-summary').textContent = `${tracks.length} track${tracks.length === 1 ? '' : 's'} · one format for the whole list`;
    fillSelect($m('bx-format'), formatItems(), s.export_format);
    fillSelect($m('bx-sample-rate'), sampleRateItems(), s.export_options.sample_rate);
    fillSelect($m('bx-flac-level'), flacLevelItems(), s.export_options.flac_level);
    $m('bx-dest').value = s.export_dir;
    $m('bx-browse').hidden = !(window.klmm && window.klmm.selectFolder);
    const group = manageState.lastGroup;
    const exact = group && group.ids.length === manageState.selected.size;
    $m('bx-subfolder').value = exact && manageState.by === 'playlist' ? group.label : '';
    const folder = isFolderSource();
    const auto = KlmmSelection.workerCount('folder', 0, navigator.hardwareConcurrency);
    fillSelect($m('bx-workers'), [
        { value: 0, label: `Auto (${auto})` },
        ...[1, 2, 3, 4].map(n => ({ value: n, label: String(n) })),
    ], folder ? Number(localStorage.getItem('batchWorkers') || 0) : 1);
    $m('bx-workers').disabled = !folder;
    $m('bx-workers-hint').textContent = folder
        ? 'Music folders can export several tracks at the same time.'
        : 'iPod: one track at a time (reading in parallel from the iPod is slower).';
    updateBatchOptions();
    resetBatchProgress();
    setStatus($m('bx-status'), '');
    setBatchRunning(false);
    $m('bx-start').textContent = 'Export';
    $m('bx-show').hidden = true;
    showModal('batch-export-modal');
}

function updateBatchOptions() {
    const id = $m('bx-format').value;
    const fmt = formatById(id);
    const ffmpeg = state.formats && state.formats.ffmpeg_available;
    const converting = id !== 'original';
    $m('bx-bitrate-group').style.display = fmt && fmt.lossy ? '' : 'none';
    $m('bx-flac-group').style.display = id === 'flac' ? '' : 'none';
    $m('bx-sample-rate-group').style.display = converting ? '' : 'none';
    if (fmt && fmt.lossy) {
        const preferred = state.settings.export_options.bitrate_kbps;
        const selected = fmt.bitrates.includes(preferred) ? preferred : fmt.default_bitrate;
        fillSelect($m('bx-bitrate'), fmt.bitrates.map(b => ({ value: b, label: `${b} kbps` })), selected);
    }
    $m('bx-ffmpeg-hint').textContent = converting && !ffmpeg ? 'ffmpeg not found: set its path in Settings.' : '';
    $m('bx-start').disabled = converting && !ffmpeg;
}

function resetBatchProgress() {
    $m('bx-progress-box').hidden = true;
    $m('bx-progress').value = 0;
    $m('bx-progress-text').textContent = '';
    $m('bx-log').replaceChildren();
}

function setBatchRunning(running) {
    batchState.running = running;
    $m('bx-settings').classList.toggle('disabled', running);
    $m('bx-settings').querySelectorAll('input, select, button').forEach(el => {
        if (el.id === 'bx-workers' && !isFolderSource()) return;
        el.disabled = running;
    });
    $m('bx-start').hidden = running;
    $m('bx-cancel').hidden = !running;
    $m('bx-cancel').disabled = false;
    $m('bx-close').disabled = running;
    $m('bx-close-x').disabled = running;
}

function closeBatchExport() {
    if (batchState.running) return;
    closeModal('batch-export-modal');
}

function batchLog(text, kind) {
    const li = document.createElement('li');
    li.className = kind;
    li.textContent = text;
    $m('bx-log').appendChild(li);
    li.scrollIntoView({ block: 'nearest' });
}

async function startBatchExport() {
    const tracks = batchTracks();
    const dest = $m('bx-dest').value.trim();
    if (!tracks.length) return;
    if (!dest) {
        setStatus($m('bx-status'), 'Choose a destination folder.', 'error');
        return;
    }
    const format = $m('bx-format').value;
    const fmt = formatById(format);
    const options = {
        sample_rate: parseInt($m('bx-sample-rate').value, 10) || 0,
        flac_level: parseInt($m('bx-flac-level').value, 10),
    };
    if (fmt && fmt.lossy) options.bitrate_kbps = parseInt($m('bx-bitrate').value, 10);
    const requested = parseInt($m('bx-workers').value, 10) || 0;
    if (isFolderSource()) localStorage.setItem('batchWorkers', String(requested));
    const workers = KlmmSelection.workerCount(isFolderSource() ? 'folder' : 'ipod', requested, navigator.hardwareConcurrency);
    const body = {
        format,
        options,
        destination: 'folder',
        dest_dir: dest,
        layout: $m('bx-layout').value,
        subfolder: $m('bx-subfolder').value.trim(),
        skip_existing: $m('bx-skip').checked,
    };

    resetBatchProgress();
    $m('bx-progress-box').hidden = false;
    $m('bx-progress').max = tracks.length;
    $m('bx-show').hidden = true;
    batchState.lastPath = '';
    batchState.root = '';
    batchState.cancel = { cancelled: false };
    setBatchRunning(true);
    let running = 0;
    const progressText = finished => {
        $m('bx-progress-text').textContent = `${finished} / ${tracks.length}` +
            (running ? ` · ${running} running` : '') + (workers > 1 ? ` · up to ${workers} at once` : '');
    };
    progressText(0);
    setStatus($m('bx-status'), format === 'original' ? 'Copying…' : 'Converting…');

    const results = await KlmmSelection.runQueue(tracks, async track => {
        running++;
        progressText(Number($m('bx-progress').value));
        try {
            const res = await fetch(`/api/tracks/export/${track.id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error(await errorText(res));
            return await res.json();
        } finally {
            running--;
        }
    }, {
        concurrency: workers,
        cancel: batchState.cancel,
        onProgress: ({ finished, index, result }) => {
            const t = tracks[index];
            $m('bx-progress').value = finished;
            progressText(finished);
            if (result.value && result.value.path) batchState.lastPath = result.value.path;
            if (result.value && result.value.root) batchState.root = result.value.root;
            if (result.status === 'failed') batchLog(`✗ ${t.artist} - ${t.title}: ${result.error.message || result.error}`, 'error');
            else if (result.status === 'skipped') batchLog(`↷ ${t.artist} - ${t.title}: already exists`, 'skipped');
        },
    });

    setBatchRunning(false);
    const sum = KlmmSelection.summarize(results);
    const cancelled = results.filter(r => r.status === 'cancelled').length;
    const parts = [`${sum.done} exported`];
    if (sum.skipped) parts.push(`${sum.skipped} skipped`);
    if (sum.failed) parts.push(`${sum.failed} failed`);
    if (cancelled) parts.push(`${cancelled} cancelled`);
    setStatus($m('bx-status'), `${parts.join(', ')}.`, sum.failed ? 'error' : 'ok');
    $m('bx-start').textContent = 'Export Again';
    $m('bx-show').hidden = !(batchState.lastPath && window.klmm && window.klmm.showItemInFolder);
}

function cancelBatchExport() {
    if (!batchState.cancel) return;
    batchState.cancel.cancelled = true;
    $m('bx-cancel').disabled = true;
    setStatus($m('bx-status'), 'Cancelling: finishing the tracks already started…');
}

// ---------------------------------------------------------------- nối sự kiện
// libraries.js gọi sau mỗi lần tải danh sách thư viện (và sau khi đổi thư viện)
function onLibrariesChanged() {
    renderManage();
}

function setupManage() {
    $m('view-manage-btn').addEventListener('click', () => showView('manage'));
    document.querySelectorAll('#manage-group-tabs .browse-tab').forEach(btn =>
        btn.addEventListener('click', () => {
            manageState.by = btn.dataset.by;
            localStorage.setItem('manageBy', manageState.by);
            renderManageGroups();
        }));
    let t1 = null;
    $m('manage-group-filter').addEventListener('input', e => {
        clearTimeout(t1);
        t1 = setTimeout(() => {
            manageState.groupQuery = e.target.value;
            renderManageGroups();
        }, 120);
    });
    let t2 = null;
    $m('manage-search').addEventListener('input', e => {
        clearTimeout(t2);
        t2 = setTimeout(() => {
            manageState.query = e.target.value;
            renderManageTracks();
        }, 120);
    });
    $m('manage-tbody').addEventListener('click', onTrackRowClick);
    $m('manage-tbody').addEventListener('mousedown', e => {
        if (e.shiftKey) e.preventDefault(); // không bôi đen chữ khi Shift-click
    });
    $m('manage-check-all').addEventListener('change', e => selectShown(e.target.checked));
    $m('manage-select-shown').addEventListener('click', () => selectShown(true));
    $m('manage-clear').addEventListener('click', () => {
        manageState.selected.clear();
        manageState.lastGroup = null;
        renderManageTracks();
        renderManageGroups();
    });
    $m('manage-export').addEventListener('click', openBatchExport);
    $m('manage-add-lib').addEventListener('click', addLibraryQuick);

    $m('bx-format').addEventListener('change', updateBatchOptions);
    $m('bx-start').addEventListener('click', startBatchExport);
    $m('bx-cancel').addEventListener('click', cancelBatchExport);
    $m('bx-close').addEventListener('click', closeBatchExport);
    $m('bx-close-x').addEventListener('click', closeBatchExport);
    // Mở thư mục gốc của lần export (thư mục đích + thư mục con), không phải thư mục album
    // của bài xong cuối cùng; bản cũ chưa có openFolder thì chọn file cuối trong Explorer
    $m('bx-show').addEventListener('click', async () => {
        const opened = batchState.root && window.klmm.openFolder && (await window.klmm.openFolder(batchState.root));
        if (!opened && batchState.lastPath) window.klmm.showItemInFolder(batchState.lastPath);
    });
    $m('bx-browse').addEventListener('click', async () => {
        const folder = await window.klmm.selectFolder();
        if (folder) $m('bx-dest').value = folder;
    });
}

document.addEventListener('DOMContentLoaded', setupManage);

window.klmmUI = Object.assign(window.klmmUI || {}, {
    showManage: () => showView('manage'),
});
