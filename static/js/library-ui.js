// Thư viện: tìm kiếm toàn thư viện, chọn nguồn (iPod / thư mục nhạc), dialog import nhiều file.
// Dùng state / fetchTracks / fetchPlaylists / fetchDevice / showModal ... của app.js.

// ---------------------------------------------------------------- tìm kiếm
let _searchTimer = null;

function clearSearch() {
    const input = document.getElementById('search-input');
    input.value = '';
    state.searchQuery = '';
}

function updateSearchStatus(count) {
    const el = document.getElementById('search-status');
    el.textContent = '';
    if (state.searchQuery) {
        const text = document.createElement('span');
        text.textContent = `${count} result${count === 1 ? '' : 's'} for “${state.searchQuery}” in the whole library`;
        const clear = document.createElement('button');
        clear.className = 'search-clear';
        clear.textContent = 'Clear';
        clear.addEventListener('click', () => {
            clearSearch();
            renderTracks();
        });
        el.append(text, clear);
    } else {
        const where = state.currentPlaylistName ? `Playlist “${state.currentPlaylistName}”` : 'Library';
        el.textContent = `${where} · ${count} track${count === 1 ? '' : 's'}`;
    }
}

function setupSearch() {
    const input = document.getElementById('search-input');
    input.addEventListener('input', () => {
        clearTimeout(_searchTimer);
        _searchTimer = setTimeout(() => {
            state.searchQuery = input.value.trim();
            if (state.searchQuery) showView('library');
            renderTracks();
        }, 120);
    });
    input.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            clearSearch();
            renderTracks();
            input.blur();
        } else if (e.key === 'Enter') {
            // Enter: phát kết quả đầu tiên
            const first = (state.visibleTrackIds || [])[0];
            if (first !== undefined) Player.playFromList(first);
        }
    });
    // "/" hoặc Ctrl+F: tới ô tìm kiếm
    document.addEventListener('keydown', e => {
        const tag = (e.target && e.target.tagName) || '';
        const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
        if ((e.key === '/' && !typing) || ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F'))) {
            e.preventDefault();
            showView('library');
            input.focus();
            input.select();
        }
    });
}

// ---------------------------------------------------------------- nguồn thư viện
function updateSourceCard(device) {
    const folder = device.source === 'folder';
    const virtual = !folder && device.is_virtual;
    setIcon(document.getElementById('source-icon'), folder ? 'folder' : virtual ? 'hard-drive' : 'smartphone');
    document.getElementById('source-name').textContent = folder ? 'Music Folder' : virtual ? 'Default library' : 'iPod';
    document.getElementById('source-path').textContent = device.mountpoint || '';
    document.getElementById('source-path').title = device.mountpoint || '';
    const repair = document.getElementById('tool-repair');
    if (repair && repair.lastChild && repair.lastChild.nodeType === Node.TEXT_NODE) {
        repair.lastChild.textContent = folder ? ' Rescan Folder' : ' Repair Checksums';
    }
    const dropText = document.querySelector('.drop-overlay h3');
    if (dropText) {
        dropText.textContent = folder
            ? 'Drop audio files here to copy them into the music folder'
            : 'Drop audio files here to import them into the iPod';
    }
}

async function reloadLibrary() {
    Player.audio.pause();
    state.currentPlayingTrackId = null;
    state.currentPlaylistName = null;
    state.currentCategory = 'all';
    if (typeof setBrowseFilter === 'function') setBrowseFilter(null, false);
    clearSearch();
    await Promise.all([fetchDevice(), fetchTracks(), fetchPlaylists()]);
    if (typeof fetchLibraries === 'function') await fetchLibraries();
}

async function openSourceDialog() {
    const status = document.getElementById('source-status');
    setStatus(status, '');
    let info = { source: 'ipod', folder: '', recent_folders: [] };
    try {
        info = await (await fetch('/api/library/source')).json();
    } catch (e) {
        console.error(e);
    }
    document.querySelector(`input[name="src-kind"][value="${info.source}"]`).checked = true;
    document.getElementById('src-folder').value = info.folder || '';
    const recent = document.getElementById('recent-folders');
    recent.innerHTML = '';
    (info.recent_folders || []).forEach(path => {
        const li = document.createElement('li');
        li.textContent = path;
        li.title = 'Use this folder';
        li.addEventListener('click', () => {
            document.getElementById('src-folder').value = path;
            document.querySelector('input[name="src-kind"][value="folder"]').checked = true;
            updateSourceForm();
        });
        recent.appendChild(li);
    });
    updateSourceForm();
    showModal('source-modal');
}

function updateSourceForm() {
    const folder = document.querySelector('input[name="src-kind"]:checked').value === 'folder';
    document.getElementById('src-folder-group').style.display = folder ? '' : 'none';
}

async function applySource(kind, folder) {
    const status = document.getElementById('source-status');
    const btn = document.getElementById('source-apply-btn');
    btn.disabled = true;
    setStatus(status, kind === 'folder' ? 'Scanning folder…' : 'Opening iPod…');
    try {
        const res = await fetch('/api/library/source', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: kind, folder }),
        });
        if (!res.ok) {
            setStatus(status, await errorText(res), 'error');
            return false;
        }
        closeModal('source-modal');
        await reloadLibrary();
        return true;
    } catch (e) {
        setStatus(status, `Cannot change library: ${e}`, 'error');
        return false;
    } finally {
        btn.disabled = false;
    }
}

async function submitSourceDialog() {
    const kind = document.querySelector('input[name="src-kind"]:checked').value;
    const folder = document.getElementById('src-folder').value.trim();
    if (kind === 'folder' && !folder) {
        setStatus(document.getElementById('source-status'), 'Choose a folder first.', 'error');
        return;
    }
    await applySource(kind, folder);
}

async function openFolderNative() {
    if (!window.klmm) return openSourceDialog();
    const folder = await window.klmm.selectFolder();
    if (folder) await applySource('folder', folder);
}

// ---------------------------------------------------------------- import
const importState = { files: [], paths: [] };

function fillImportPlaylists(selected) {
    const select = document.getElementById('import-playlist');
    select.innerHTML = '';
    const add = (value, label) => {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        select.appendChild(opt);
    };
    add('', '— None —');
    state.playlists
        .filter(p => !p.is_master)
        .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
        .forEach(p => add(p.name, p.name));
    add('__new__', '+ New playlist…');
    select.value = selected || state.currentPlaylistName || '';
    updateImportPlaylistInput();
}

function updateImportPlaylistInput() {
    const isNew = document.getElementById('import-playlist').value === '__new__';
    const input = document.getElementById('import-new-playlist');
    input.hidden = !isNew;
    if (isNew) input.focus();
}

function chosenPlaylist() {
    const value = document.getElementById('import-playlist').value;
    if (value === '__new__') return document.getElementById('import-new-playlist').value.trim() || null;
    return value || null;
}

function updateImportSelection() {
    const n = importState.paths.length ? importState.paths.length : importState.files.length;
    const what = importState.paths.length ? importState.paths.join(', ') : `${n} file${n === 1 ? '' : 's'}`;
    document.getElementById('import-selection').textContent = n
        ? `Selected: ${what}`
        : 'No files selected. You can also drag files onto the track list.';
    document.querySelector('.import-tags').style.display = importState.files.length === 1 ? '' : 'none';
}

function openImportDialog({ files = [], paths = [] } = {}) {
    document.getElementById('add-music-form').reset();
    importState.files = files;
    importState.paths = paths;
    document.getElementById('import-progress').innerHTML = '';
    const folderSource = state.device && state.device.source === 'folder';
    document.getElementById('import-title').textContent = folderSource ? 'Import into Music Folder' : 'Import into iPod';
    fillImportPlaylists();
    updateImportSelection();
    showModal('add-music-modal');
}

function progressRow(name) {
    const li = document.createElement('li');
    const label = document.createElement('span');
    label.className = 'ip-name';
    label.textContent = name;
    const st = document.createElement('span');
    st.className = 'ip-status';
    st.textContent = 'waiting';
    li.append(label, st);
    document.getElementById('import-progress').appendChild(li);
    return {
        set(text, kind) {
            st.textContent = text;
            li.className = kind || '';
        },
    };
}

async function uploadOne(file, playlist, overrides) {
    const form = new FormData();
    form.append('file', file);
    if (playlist) form.append('playlist', playlist);
    if (overrides) for (const [k, v] of Object.entries(overrides)) if (v) form.append(k, v);
    const res = await fetch('/api/tracks/add', { method: 'POST', body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.success) throw new Error(body.error || `HTTP ${res.status}`);
    return body;
}

// "imported" / "imported (converted FLAC → ALAC)" (iPod: file iPod không phát được được chuyển)
function importedText(result) {
    return result && result.converted ? `imported (converted ${result.converted})` : 'imported';
}

async function submitImport() {
    const btn = document.getElementById('add-track-submit');
    const playlist = chosenPlaylist();
    if (!importState.files.length && !importState.paths.length) {
        document.getElementById('import-selection').textContent = 'Choose files or a folder first.';
        return;
    }
    btn.disabled = true;
    document.getElementById('import-progress').innerHTML = '';
    let ok = 0;
    let failed = 0;
    try {
        if (importState.paths.length) {
            const row = progressRow('Importing from disk…');
            row.set('working…', 'busy');
            const res = await fetch('/api/tracks/import-paths', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paths: importState.paths, playlist }),
            });
            const body = await res.json().catch(() => ({}));
            document.getElementById('import-progress').innerHTML = '';
            if (!res.ok) {
                progressRow('Import').set(body.error || `HTTP ${res.status}`, 'error');
                failed += 1;
            } else {
                for (const r of body.results || []) {
                    const name = r.path.split(/[\\/]/).pop();
                    progressRow(name).set(r.ok ? importedText(r) : r.error || 'failed', r.ok ? 'ok' : 'error');
                    r.ok ? ok++ : failed++;
                }
            }
        } else {
            const overrides =
                importState.files.length === 1
                    ? {
                          title: document.getElementById('add-title').value,
                          artist: document.getElementById('add-artist').value,
                          album: document.getElementById('add-album').value,
                          genre: document.getElementById('add-genre').value,
                          year: document.getElementById('add-year').value,
                          track_number: document.getElementById('add-track-number').value,
                          rating: document.getElementById('add-rating').value,
                      }
                    : null;
            const rows = importState.files.map(f => progressRow(f.name));
            for (let i = 0; i < importState.files.length; i++) {
                rows[i].set('uploading…', 'busy');
                try {
                    const result = await uploadOne(importState.files[i], playlist, overrides);
                    rows[i].set(importedText(result), 'ok');
                    ok++;
                } catch (e) {
                    rows[i].set(String(e.message || e), 'error');
                    failed++;
                }
            }
        }
    } finally {
        btn.disabled = false;
        document.getElementById('import-selection').textContent =
            `Done: ${ok} imported${failed ? `, ${failed} failed` : ''}${playlist ? ` (playlist “${playlist}”)` : ''}.`;
        importState.files = [];
        importState.paths = [];
        await Promise.all([fetchTracks(), fetchPlaylists(), fetchDevice()]);
    }
}

async function pickNative(kind) {
    if (!window.klmm) return;
    if (kind === 'folder') {
        const folder = await window.klmm.selectFolder();
        if (folder) importState.paths = [folder];
    } else {
        const files = await window.klmm.selectFiles();
        if (files && files.length) importState.paths = files;
    }
    importState.files = [];
    updateImportSelection();
}

// Kéo-thả vào bảng bài hát -> mở dialog import với file đã chọn
function importUploadedFiles(files) {
    if (state.device && state.device.is_read_only) return;
    openImportDialog({ files });
}

// ---------------------------------------------------------------- Help / About
function openHelp(section) {
    const frame = document.getElementById('help-frame');
    const url = `help/index.html${section ? `#${section}` : ''}`;
    // Gán lại src mỗi lần để nhảy tới mục được yêu cầu
    frame.src = 'about:blank';
    frame.src = url;
    showModal('help-modal');
}

async function openAbout() {
    const table = document.getElementById('about-table');
    table.innerHTML = '';
    try {
        const a = await (await fetch('/api/about')).json();
        const rows = [
            ['Version', `${a.name} ${a.version}`],
            ['License', a.license],
            ['Author', a.author],
            ['Homepage', a.homepage],
            ['Platform', a.platform],
            ['Python', a.python],
            ['ffmpeg', a.ffmpeg || 'not found'],
            ['Data folder', a.data_dir],
        ];
        for (const [k, v] of rows) {
            const tr = document.createElement('tr');
            const th = document.createElement('th');
            const td = document.createElement('td');
            th.textContent = k;
            td.textContent = v;
            tr.append(th, td);
            table.appendChild(tr);
        }
    } catch (e) {
        table.textContent = `Cannot load app information: ${e}`;
    }
    showModal('about-modal');
}

// ---------------------------------------------------------------- khởi tạo
function setupLibraryUI() {
    setupSearch();
    const onClick = (id, fn) =>
        document.getElementById(id).addEventListener('click', e => {
            e.preventDefault();
            fn();
        });
    onClick('tool-help', () => openHelp());
    onClick('tool-about', openAbout);
    document.addEventListener('keydown', e => {
        if (e.key === 'F1') {
            e.preventDefault();
            openHelp();
        }
    });
    onClick('add-track-btn', () => openImportDialog());
    onClick('add-track-submit', submitImport);
    onClick('import-files-native', () => pickNative('files'));
    onClick('import-folder-native', () => pickNative('folder'));
    onClick('source-card', openSourceDialog);
    onClick('tool-library-source', openSourceDialog);
    onClick('source-apply-btn', submitSourceDialog);
    onClick('src-folder-browse', async () => {
        const folder = window.klmm ? await window.klmm.selectFolder() : '';
        if (folder) {
            document.getElementById('src-folder').value = folder;
            document.querySelector('input[name="src-kind"][value="folder"]').checked = true;
            updateSourceForm();
        }
    });
    document.querySelectorAll('input[name="src-kind"]').forEach(r => r.addEventListener('change', updateSourceForm));
    document.getElementById('import-playlist').addEventListener('change', updateImportPlaylistInput);
    document.getElementById('add-file-input').addEventListener('change', e => {
        importState.files = Array.from(e.target.files);
        importState.paths = [];
        updateImportSelection();
    });
}

window.klmmUI = Object.assign(window.klmmUI || {}, {
    openHelp,
    openAbout,
    openSourceDialog,
    openFolder: openFolderNative,
    useIpod: () => applySource('ipod', ''),
    openImport: () => openImportDialog(),
    importFiles: async () => {
        openImportDialog();
        await pickNative('files');
    },
    importFolder: async () => {
        openImportDialog();
        await pickNative('folder');
    },
});
