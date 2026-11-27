// KL Music Manager App Logic
let state = {
    tracks: [],
    playlists: [],
    device: {},
    selectedTrackId: null,
    currentPlayingTrackId: null,
    currentCategory: 'all',
    currentPlaylistName: null,
    searchQuery: '',
    sortColumn: null,
    sortDirection: 'asc'
};

// Elements
const tracksListBody = document.getElementById('tracks-list-body');
const playlistListBody = document.getElementById('playlist-list-body');
const playPauseBtn = document.getElementById('play-pause-btn');
const playIcon = document.getElementById('play-icon');
const seekSlider = document.getElementById('seek-slider');
const currentTimeLabel = document.getElementById('current-time');
const totalTimeLabel = document.getElementById('total-time');
const currentTrackTitle = document.getElementById('current-track-title');
const currentTrackArtist = document.getElementById('current-track-artist');
const audioPlayer = document.getElementById('audio-preview-player');

const addTrackBtn = document.getElementById('add-track-btn');
const exportTrackBtn = document.getElementById('export-track-btn');
const deleteTrackBtn = document.getElementById('delete-track-btn');
const toolsBtn = document.getElementById('tools-btn');
const searchInput = document.getElementById('search-input');
const trackContextMenu = document.getElementById('track-context-menu');

// Device Stats Info
const deviceModelLabel = document.getElementById('device-model-label');
const tracksCountLabel = document.getElementById('tracks-count-label');
const mountpointLabel = document.getElementById('mountpoint-label');
const storageLabel = document.getElementById('storage-label');
const storageProgressBar = document.getElementById('storage-progress-bar');
const connectionText = document.getElementById('connection-text');
const connectionIndicator = document.querySelector('.status-indicator');


// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function initApp() {
    if (window.klmm && window.klmm.isElectron) document.body.classList.add('is-electron');
    fetchSettings();
    fetchDevice();
    fetchTracks();
    fetchPlaylists();
    setupEventListeners();
    setupSettingsAndExport();
    Player.setup(); // js/player.js
    setupLibraryUI(); // js/library-ui.js
    setupLibraries(); // js/libraries.js
    makeColumnsResizable();
}

// Setup all listeners
function setupEventListeners() {
    // Actions
    addTrackBtn.addEventListener('click', () => showModal('add-music-modal'));
    exportTrackBtn.addEventListener('click', () => {
        if (state.selectedTrackId) downloadTrack(state.selectedTrackId);
    });
    deleteTrackBtn.addEventListener('click', () => {
        if (state.selectedTrackId) confirmDeleteTrack(state.selectedTrackId);
    });

    // Tools Dropdown
    toolsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        document.querySelector('.dropdown-menu').classList.toggle('show');
    });

    document.getElementById('tool-repair').addEventListener('click', (e) => {
        e.preventDefault();
        repairDatabase();
    });

    document.getElementById('tool-redetect').addEventListener('click', (e) => {
        e.preventDefault();
        redetectDevice();
    });

    // Close menus on click away
    document.addEventListener('click', () => {
        document.querySelector('.dropdown-menu').classList.remove('show');
        hideContextMenu();
    });

    // Search: js/library-ui.js (tìm trên toàn thư viện, không dấu)

    // Sidebar Category Filter
    document.querySelectorAll('.category-list li').forEach(li => {
        li.addEventListener('click', (e) => {
            document.querySelectorAll('.category-list li').forEach(item => item.classList.remove('active'));
            document.querySelectorAll('.playlist-list li').forEach(item => item.classList.remove('active'));
            li.classList.add('active');
            state.currentCategory = li.dataset.category;
            state.currentPlaylistName = null;
            if (typeof setBrowseFilter === 'function') setBrowseFilter(null, false);
            if (typeof clearSearch === 'function') clearSearch();
            if (typeof showView === 'function') showView('library');
            renderTracks();
        });
    });

    // New Playlist
    document.getElementById('new-playlist-btn').addEventListener('click', () => {
        showModal('playlist-modal');
    });

    document.getElementById('create-playlist-submit').addEventListener('click', createPlaylist);

    // Save Metadata Submit
    document.getElementById('save-metadata-btn').addEventListener('click', saveMetadata);
    document.getElementById('edit-cover-file').addEventListener('change', onEditCoverChosen);
    document.getElementById('edit-cover-remove').addEventListener('click', onEditCoverRemove);

    // Import dialog / drag-drop: js/library-ui.js

    // Context Menu Listeners (Play Next / Add to Queue: js/player.js)
    document.getElementById('menu-edit').addEventListener('click', () => {
        if (state.selectedTrackId) openEditModal(state.selectedTrackId);
    });
    document.getElementById('menu-export').addEventListener('click', () => {
        if (state.selectedTrackId) downloadTrack(state.selectedTrackId);
    });
    document.getElementById('menu-reveal-finder').addEventListener('click', () => {
        if (state.selectedTrackId) revealInFinder(state.selectedTrackId);
    });
    document.getElementById('menu-delete').addEventListener('click', () => {
        if (state.selectedTrackId) confirmDeleteTrack(state.selectedTrackId);
    });

    // Drag and drop zone
    const dropZone = document.getElementById('drop-zone');
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            importUploadedFiles(Array.from(files), null);
        }
    }, false);

    // Media player controls, System Player toggle: js/player.js

    // Column Sorting Headers Listeners
    document.querySelectorAll('.tracks-table th').forEach(th => {
        th.addEventListener('click', (e) => {
            // Prevent sorting click when dragging the column divider resizer
            if (e.target.classList.contains('resizer')) return;
            
            const col = th.dataset.sort;
            if (!col) return;
            
            if (state.sortColumn === col) {
                state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                state.sortColumn = col;
                state.sortDirection = 'asc';
            }
            
            updateHeaderArrows();
            renderTracks();
        });
    });
}



// Labels that name the host OS file manager / computer (index.html holds neutral defaults)
const HOST_LABELS = {
    Darwin: { computer: 'Mac', fileManager: 'Finder' },
    Windows: { computer: 'PC', fileManager: 'Explorer' },
};

function setMenuText(id, text) {
    const item = document.getElementById(id);
    // Keep the <img> icon: only replace the trailing text node
    if (item && item.lastChild && item.lastChild.nodeType === Node.TEXT_NODE) {
        item.lastChild.textContent = ' ' + text;
    }
}

function applyHostLabels(hostOs) {
    const labels = HOST_LABELS[hostOs];
    if (!labels) return;
    setMenuText('menu-export', `Export to ${labels.computer}`);
    setMenuText('menu-reveal-finder', `Show in ${labels.fileManager}`);
    exportTrackBtn.title = `Export Selected Track to ${labels.computer}`;
}

// API: Fetch Device info
async function fetchDevice() {
    try {
        const response = await fetch('/api/device');
        const data = await response.json();
        state.device = data;
        applyHostLabels(data.host_os);
        if (typeof updateSourceCard === 'function') updateSourceCard(data);
        if (typeof renderLibrarySidebar === 'function') renderLibrarySidebar();

        // Render device status
        deviceModelLabel.textContent = data.model;
        tracksCountLabel.textContent = `${data.tracks_count} tracks`;
        mountpointLabel.textContent = `Path: ${data.mountpoint}`;
        
        // Connection text
        if (data.is_virtual) {
            connectionText.textContent = "Virtual Mode";
            connectionIndicator.className = "status-indicator online";
        } else {
            connectionText.textContent = "Connected";
            connectionIndicator.className = "status-indicator online";
        }

        // Storage statistics
        const usedGB = (data.used_space / (1024 ** 3)).toFixed(1);
        const totalGB = (data.total_space / (1024 ** 3)).toFixed(1);
        storageLabel.textContent = `Used: ${usedGB} GB / Total: ${totalGB} GB`;
        
        const usagePercent = ((data.used_space / data.total_space) * 100).toFixed(1);
        storageProgressBar.style.width = `${usagePercent}%`;

        // Apply read-only mode UI restrictions
        if (data.is_read_only) {
            connectionText.textContent = "Safe Read-Only Mode";
            connectionIndicator.className = "status-indicator online";
            
            const addBtn = document.getElementById('add-track-btn');
            const delBtn = document.getElementById('delete-track-btn');
            const newPlBtn = document.getElementById('new-playlist-btn');
            const repairLink = document.getElementById('tool-repair');
            const menuEdit = document.getElementById('menu-edit');
            const menuDel = document.getElementById('menu-delete');
            const menuAddPl = document.getElementById('menu-add-playlist');
            const dropOverlay = document.querySelector('.drop-overlay');
            
            if (addBtn) addBtn.style.display = 'none';
            if (delBtn) delBtn.style.display = 'none';
            if (newPlBtn) newPlBtn.style.display = 'none';
            if (repairLink) repairLink.style.display = 'none';
            if (menuEdit) menuEdit.style.display = 'none';
            if (menuDel) menuDel.style.display = 'none';
            if (menuAddPl) menuAddPl.style.display = 'none';
            if (dropOverlay) dropOverlay.style.display = 'none';
        }
    } catch (e) {
        console.error("Failed to load device info", e);
        connectionText.textContent = "Disconnected";
        connectionIndicator.className = "status-indicator offline";
    }
}

// API: Fetch Tracks list
async function fetchTracks() {
    try {
        const response = await fetch('/api/tracks');
        const data = await response.json();
        state.tracks = data;
        state.tracksById = new Map(data.map(t => [t.id, t]));
        state.searchIndex = KlmmSearch.buildIndex(data);
        const browse = document.getElementById('browse-view');
        if (browse && !browse.hidden && typeof renderBrowse === 'function') renderBrowse();
        renderTracks();
    } catch (e) {
        console.error("Failed to fetch tracks", e);
        tracksListBody.innerHTML = `<tr><td colspan="8" class="loading-cell" style="color: var(--color-danger)">Error loading iPod database. Make sure environment is running.</td></tr>`;
    }
}

// API: Fetch Playlists
async function fetchPlaylists() {
    try {
        const response = await fetch('/api/playlists');
        const data = await response.json();
        state.playlists = data;
        renderPlaylists();
    } catch (e) {
        console.error("Failed to fetch playlists", e);
    }
}

// Render playlist sidebar
function renderPlaylists() {
    playlistListBody.innerHTML = '';
    
    // Render playlists in context menu and sidebar
    const contextSubmenu = document.getElementById('context-playlist-submenu');
    contextSubmenu.innerHTML = '';

    // Sort playlists alphabetically by name
    const sortedPlaylists = [...state.playlists].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));

    sortedPlaylists.forEach(pl => {
        // We bypass the Master playlist in user-playlist listing but keep it in backend
        if (pl.is_master) return;
        
        // Sidebar list
        const li = document.createElement('li');
        li.className = 'pl-item';
        if (state.currentPlaylistName === pl.name) li.classList.add('active');
        li.dataset.name = pl.name;
        
        li.innerHTML = `
            <div class="pl-info-wrapper" style="display:flex; align-items:center; gap:12px; cursor:default; flex:1">
                <svg class="icon sidebar-icon" aria-hidden="true"><use href="icons/sprite.svg#list-music"></use></svg>
                <span class="pl-name"></span>
            </div>
        `;
        li.querySelector('.pl-name').textContent = pl.name; // tên playlist là dữ liệu, không phải HTML
        if (!(state.device && state.device.is_read_only)) {
            const del = document.createElement('button');
            del.className = 'delete-pl-btn';
            del.title = 'Delete playlist (music files are kept)';
            del.textContent = '×';
            del.addEventListener('click', (e) => {
                e.stopPropagation();
                confirmDeletePlaylist(pl.name);
            });
            li.appendChild(del);
        }

        // Event for selecting playlist
        li.querySelector('.pl-info-wrapper').addEventListener('click', (e) => {
            document.querySelectorAll('.category-list li').forEach(item => item.classList.remove('active'));
            document.querySelectorAll('.playlist-list li').forEach(item => item.classList.remove('active'));
            li.classList.add('active');
            state.currentPlaylistName = pl.name;
            state.currentCategory = null;
            if (typeof setBrowseFilter === 'function') setBrowseFilter(null, false);
            if (typeof clearSearch === 'function') clearSearch();
            if (typeof showView === 'function') showView('library');
            renderTracks();
        });

        playlistListBody.appendChild(li);

        // Add to Context Submenu list
        const subLi = document.createElement('li');
        subLi.textContent = pl.name;
        subLi.addEventListener('click', () => {
            addTrackToPlaylist(pl.name, state.selectedTrackId);
        });
        contextSubmenu.appendChild(subLi);
    });
}

// Render track list in main grid
function renderTracks() {
    tracksListBody.innerHTML = '';
    
    let filteredTracks = state.tracks;

    // Filter by Category
    if (state.currentCategory) {
        if (state.currentCategory === 'podcasts') {
            // Placeholder: filter podcast tracks (we check name or genre)
            filteredTracks = state.tracks.filter(t => t.genre.toLowerCase() === 'podcast' || t.genre.toLowerCase() === 'system');
        } else if (state.currentCategory === 'videos') {
            // Placeholder: filter videos (ext matching mp4/m4v etc.)
            filteredTracks = state.tracks.filter(t => t.file_path.toLowerCase().endsWith('.mp4') || t.file_path.toLowerCase().endsWith('.m4v'));
        } else if (state.currentCategory === 'photos') {
            filteredTracks = []; // Photos not supported
        }
    }

    // Filter by Playlist
    if (state.currentPlaylistName) {
        const playlist = state.playlists.find(pl => pl.name === state.currentPlaylistName);
        if (playlist) {
            const ids = new Set(playlist.track_ids);
            filteredTracks = state.tracks.filter(t => ids.has(t.id));
        }
    }

    // Lọc theo mục đã chọn ở trang Browse (genre / artist / album / year)
    if (state.browseFilter) {
        const f = state.browseFilter;
        filteredTracks = filteredTracks.filter(t => KlmmTagCloud.matches(t, f.by, f.key));
    }

    // Search: trên toàn thư viện (bỏ qua playlist/category đang chọn), không phân biệt dấu
    if (state.searchQuery) {
        filteredTracks = KlmmSearch.search(state.tracks, state.searchQuery, state.searchIndex);
    }

    // Sorting
    if (state.sortColumn) {
        filteredTracks.sort((a, b) => {
            let valA = a[state.sortColumn];
            let valB = b[state.sortColumn];
            
            if (typeof valA === 'string') {
                valA = valA.toLowerCase();
                valB = (valB || '').toLowerCase();
                return state.sortDirection === 'asc' 
                    ? valA.localeCompare(valB) 
                    : valB.localeCompare(valA);
            }
            
            valA = valA || 0;
            valB = valB || 0;
            return state.sortDirection === 'asc' 
                ? valA - valB 
                : valB - valA;
        });
    }

    // Thứ tự đang hiển thị = danh sách cho hàng đợi phát (js/player.js)
    state.visibleTrackIds = filteredTracks.map(t => t.id);
    if (typeof updateSearchStatus === 'function') updateSearchStatus(filteredTracks.length);

    if (filteredTracks.length === 0) {
        tracksListBody.innerHTML = `<tr><td colspan="7" class="loading-cell">No tracks found matching current selection.</td></tr>`;
        return;
    }

    const fragment = document.createDocumentFragment();
    filteredTracks.forEach((track) => {
        const tr = document.createElement('tr');
        tr.dataset.id = track.id;

        if (state.selectedTrackId === track.id) tr.classList.add('selected');
        if (state.currentPlayingTrackId === track.id) tr.classList.add('playing');

        // Format duration
        const mins = Math.floor(track.duration / 60);
        const secs = String(track.duration % 60).padStart(2, '0');
        const durationStr = `${mins}:${secs}`;

        // Star rating
        let starsStr = '';
        for (let i = 1; i <= 5; i++) {
            starsStr += i <= track.rating ? '★' : '☆';
        }

        // textContent (không innerHTML): tên bài là dữ liệu, không phải HTML
        const cells = [
            [track.title, 'track-title', true],
            [track.artist, '', true],
            [track.album, '', true],
            [track.genre, '', false],
            [durationStr, '', false],
            [starsStr, 'rating-cell', false],
            [String(track.play_count), '', false],
        ];
        for (const [text, cls, withTitle] of cells) {
            const td = document.createElement('td');
            td.textContent = text;
            if (cls) td.className = cls;
            if (withTitle) td.title = text;
            tr.appendChild(td);
        }

        // Selection
        tr.addEventListener('click', (e) => {
            e.stopPropagation();
            selectTrack(track.id);
        });

        // Double click to play (System Player toggle -> OS player, else in-app player + queue)
        tr.addEventListener('dblclick', () => {
            const toggle = document.getElementById('player-toggle');
            if (toggle && toggle.checked) {
                playSystemTrack(track.id);
            } else {
                Player.playFromList(track.id);
            }
        });

        // Right click Context Menu
        tr.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            selectTrack(track.id);
            showContextMenu(e.clientX, e.clientY);
        });

        fragment.appendChild(tr);
    });
    tracksListBody.appendChild(fragment);
}

function selectTrack(trackId) {
    state.selectedTrackId = trackId;
    
    // Highlight in Table
    document.querySelectorAll('.tracks-table tbody tr').forEach(row => {
        if (parseInt(row.dataset.id) === trackId) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });

    // Enable toolbar buttons
    exportTrackBtn.removeAttribute('disabled');
    deleteTrackBtn.removeAttribute('disabled');
}

function formatTime(seconds) {
    if (isNaN(seconds)) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = String(Math.floor(seconds % 60)).padStart(2, '0');
    return `${mins}:${secs}`;
}

// Context Menu visibility
function showContextMenu(x, y) {
    trackContextMenu.style.display = 'block';
    
    // Populate "Show in Playlist" submenu
    const showPlMenu = document.getElementById('menu-show-playlist');
    const showPlSubmenu = document.getElementById('context-show-playlist-submenu');
    showPlSubmenu.innerHTML = '';
    
    const containingPlaylists = state.playlists.filter(pl => !pl.is_master && pl.track_ids.includes(state.selectedTrackId));
    
    if (containingPlaylists.length === 0) {
        showPlMenu.style.display = 'none';
    } else {
        showPlMenu.style.display = 'block';
        // Sort containing playlists alphabetically
        const sortedContainingPlaylists = [...containingPlaylists].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
        
        sortedContainingPlaylists.forEach(pl => {
            const li = document.createElement('li');
            li.textContent = pl.name;
            li.addEventListener('click', () => {
                state.currentPlaylistName = pl.name;
                state.currentCategory = null;
                
                // Update sidebar UI active state
                document.querySelectorAll('.category-list li').forEach(item => item.classList.remove('active'));
                document.querySelectorAll('.playlist-list li').forEach(item => {
                    if (item.dataset.name === pl.name) {
                        item.classList.add('active');
                    } else {
                        item.classList.remove('active');
                    }
                });
                
                renderTracks();
                
                // Highlight and scroll to track
                setTimeout(() => {
                    const row = document.querySelector(`.tracks-table tbody tr[data-id="${state.selectedTrackId}"]`);
                    if (row) {
                        row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        row.classList.add('selected');
                    }
                }, 100);
            });
            showPlSubmenu.appendChild(li);
        });
    }

    // Ensure menu doesn't go offscreen
    const winWidth = window.innerWidth;
    const winHeight = window.innerHeight;
    const menuWidth = trackContextMenu.offsetWidth;
    const menuHeight = trackContextMenu.offsetHeight;

    let left = x;
    let top = y;

    if (x + menuWidth > winWidth) {
        left = winWidth - menuWidth - 10;
    }
    if (y + menuHeight > winHeight) {
        top = winHeight - menuHeight - 10;
    }

    trackContextMenu.style.left = `${left}px`;
    trackContextMenu.style.top = `${top}px`;
}

function hideContextMenu() {
    trackContextMenu.style.display = 'none';
}

// Modals display
function showModal(id) {
    document.getElementById(id).classList.add('show');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('show');
}

// API operations: Edit metadata (thư mục: đủ trường + ảnh bìa; iPod: trường iTunesDB + rating)
const EDIT_FIELDS = {
    title: 'edit-title',
    artist: 'edit-artist',
    album_artist: 'edit-album-artist',
    album: 'edit-album',
    genre: 'edit-genre',
    composer: 'edit-composer',
    year: 'edit-year',
    track_number: 'edit-track-number',
    total_tracks: 'edit-total-tracks',
    disc_number: 'edit-disc-number',
    total_discs: 'edit-total-discs',
    bpm: 'edit-bpm',
    comment: 'edit-comment',
    lyrics: 'edit-lyrics',
};
const IPOD_EDIT_FIELDS = ['title', 'artist', 'album_artist', 'album', 'genre', 'composer', 'year', 'track_number'];
const editState = { trackId: null, folder: false, cover: null }; // cover: null | File | 'remove'

function setEditCoverPreview(url) {
    const img = document.getElementById('edit-cover-img');
    const ph = document.getElementById('edit-cover-placeholder');
    img.hidden = !url;
    ph.hidden = !!url;
    if (url) img.src = url;
    else img.removeAttribute('src');
}

function fillGenreList() {
    const list = document.getElementById('edit-genre-list');
    const genres = [...new Set(state.tracks.map(t => t.genre).filter(g => g && g !== 'Unknown Genre'))];
    list.replaceChildren(...genres.sort((a, b) => a.localeCompare(b)).map(g => {
        const o = document.createElement('option');
        o.value = g;
        return o;
    }));
}

async function openEditModal(trackId) {
    const track = state.tracks.find(t => t.id === trackId);
    if (!track) return;
    const folder = state.device && state.device.source === 'folder';
    Object.assign(editState, { trackId, folder, cover: null });
    document.getElementById('edit-track-id').value = trackId;
    const modal = document.getElementById('metadata-modal');
    modal.querySelectorAll('[data-folder-only]').forEach(el => { el.hidden = !folder; });
    modal.querySelectorAll('[data-ipod-only]').forEach(el => { el.hidden = folder; });
    for (const [field, id] of Object.entries(EDIT_FIELDS)) {
        const v = track[field];
        document.getElementById(id).value = v === undefined || v === 0 ? '' : v;
    }
    document.getElementById('edit-rating').value = track.rating || 0;
    document.getElementById('edit-cover-album').checked = false;
    document.getElementById('edit-cover-file').value = '';
    document.getElementById('edit-cover-status').textContent = 'JPEG or PNG; saved into the file (max 1200 px).';
    document.getElementById('edit-file-info').textContent = '';
    modal.querySelector('.lyrics-group').open = false;
    fillGenreList();
    setEditCoverPreview(null);
    const probe = new Image();
    probe.onload = () => { if (editState.trackId === trackId && !editState.cover) setEditCoverPreview(probe.src); };
    probe.src = artworkUrl(trackId);
    showModal('metadata-modal');

    try {
        const res = await fetch(`/api/tracks/${trackId}/details`);
        if (!res.ok || editState.trackId !== trackId) return;
        const d = await res.json();
        for (const [field, id] of Object.entries(EDIT_FIELDS)) {
            const v = d.tags[field];
            if (v !== undefined) document.getElementById(id).value = v === 0 ? '' : v;
        }
        if (d.tags.lyrics) modal.querySelector('.lyrics-group').open = true;
        const info = KlmmTrackInfo.summary(d);
        document.getElementById('edit-file-info').textContent = [info, track.file_path].filter(Boolean).join(' — ');
    } catch (e) {
        console.warn('Cannot load track details', e);
    }
}

function onEditCoverChosen(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    editState.cover = file;
    setEditCoverPreview(URL.createObjectURL(file));
    document.getElementById('edit-cover-status').textContent = `New image: ${file.name} (saved when you click Save)`;
}

function onEditCoverRemove() {
    editState.cover = 'remove';
    setEditCoverPreview(null);
    document.getElementById('edit-cover-status').textContent = 'Album art will be removed when you click Save.';
}

async function saveCover(trackId) {
    if (!editState.folder || !editState.cover) return true;
    const album = document.getElementById('edit-cover-album').checked;
    let res;
    if (editState.cover === 'remove') {
        res = await fetch(`/api/tracks/${trackId}/artwork?apply_album=${album ? 1 : 0}`, { method: 'DELETE' });
    } else {
        const form = new FormData();
        form.append('image', editState.cover);
        form.append('apply_album', album ? '1' : '0');
        res = await fetch(`/api/tracks/${trackId}/artwork`, { method: 'POST', body: form });
    }
    if (!res.ok) {
        alert(`Cannot save album art: ${await errorText(res)}`);
        return false;
    }
    state.artVersion = (state.artVersion || 0) + 1;
    return true;
}

async function saveMetadata() {
    const trackId = Number(document.getElementById('edit-track-id').value);
    const fields = editState.folder ? Object.keys(EDIT_FIELDS) : IPOD_EDIT_FIELDS;
    const data = {};
    for (const field of fields) data[field] = document.getElementById(EDIT_FIELDS[field]).value;
    if (!editState.folder) data.rating = document.getElementById('edit-rating').value;

    try {
        const response = await fetch(`/api/tracks/update/${trackId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const res = await response.json();
        if (!res.success) {
            alert(res.error || 'Error saving metadata.');
            return;
        }
        if (!(await saveCover(trackId))) return;
        closeModal('metadata-modal');
        await fetchTracks();
        if (state.currentPlayingTrackId === trackId) {
            Player.refreshArtwork();
            Player.loadFileInfo(trackId);
        }
    } catch (e) {
        console.error(e);
        alert('Error saving metadata.');
    }
}

// Download/Export track: opens the export dialog (format / options / destination)
function downloadTrack(trackId) {
    openExportModal(trackId);
}

// Reveal track in Finder
async function revealInFinder(trackId) {
    try {
        const response = await fetch(`/api/tracks/reveal/${trackId}`, {
            method: 'POST'
        });
        const res = await response.json();
        if (!res.success) {
            alert("Failed to reveal file: " + res.error);
        }
    } catch (e) {
        console.error("Error revealing in Finder", e);
    }
}

// Confirm Delete Track
function confirmDeleteTrack(trackId) {
    const track = state.tracks.find(t => t.id === trackId);
    if (!track) return;

    if (confirm(`Are you sure you want to permanently delete "${track.title}" from your iPod? This deletes the file.`)) {
        deleteTrack(trackId);
    }
}

async function deleteTrack(trackId) {
    try {
        const response = await fetch(`/api/tracks/${trackId}`, {
            method: 'DELETE'
        });
        const res = await response.json();
        if (res.success) {
            state.selectedTrackId = null;
            exportTrackBtn.setAttribute('disabled', 'true');
            deleteTrackBtn.setAttribute('disabled', 'true');
            
            // If deleting playing track, stop player
            if (state.currentPlayingTrackId === trackId) {
                audioPlayer.pause();
                state.currentPlayingTrackId = null;
                currentTrackTitle.textContent = "No track loaded";
                currentTrackArtist.textContent = "";
                setIcon(playIcon, 'play');
            }
            
            fetchTracks();
            fetchDevice();
        } else {
            alert("Delete failed.");
        }
    } catch (e) {
        console.error(e);
    }
}

// Create Playlist
async function createPlaylist() {
    const nameInput = document.getElementById('playlist-name-input');
    const name = nameInput.value.trim();
    if (!name) return;

    try {
        const response = await fetch('/api/playlists/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const res = await response.json();
        if (res.success) {
            nameInput.value = '';
            closeModal('playlist-modal');
            fetchPlaylists();
        } else {
            alert("Failed to create playlist.");
        }
    } catch (e) {
        console.error(e);
    }
}

// Delete Playlist
function confirmDeletePlaylist(name) {
    if (confirm(`Are you sure you want to delete playlist "${name}"? This will not delete the music files.`)) {
        deletePlaylist(name);
    }
}

async function deletePlaylist(name) {
    try {
        const response = await fetch(`/api/playlists/${encodeURIComponent(name)}`, {
            method: 'DELETE'
        });
        const res = await response.json();
        if (res.success) {
            if (state.currentPlaylistName === name) {
                state.currentPlaylistName = null;
                state.currentCategory = 'all';
                document.querySelector('.category-list li[data-category="all"]').classList.add('active');
            }
            fetchPlaylists();
            renderTracks();
        } else {
            alert("Failed to delete playlist.");
        }
    } catch (e) {
        console.error(e);
    }
}

// Add Track to Playlist
async function addTrackToPlaylist(playlistName, trackId) {
    try {
        const response = await fetch(`/api/playlists/${encodeURIComponent(playlistName)}/add/${trackId}`, {
            method: 'POST'
        });
        const res = await response.json();
        if (res.success) {
            fetchPlaylists();
            alert(`Added track to playlist "${playlistName}"`);
        } else {
            alert("Failed to add to playlist.");
        }
    } catch (e) {
        console.error(e);
    }
}

// Database Repair check
async function repairDatabase() {
    try {
        const response = await fetch('/api/device/repair', {
            method: 'POST'
        });
        const res = await response.json();
        if (res.success) {
            alert("iPod database checksums and hashes updated successfully!");
        } else {
            alert("Failed to update database checksums.");
        }
    } catch (e) {
        console.error(e);
    }
}

// Redetect device
async function redetectDevice() {
    try {
        const response = await fetch('/api/device/redetect', {
            method: 'POST'
        });
        const res = await response.json();
        if (res.success) {
            // Chỉ tải lại dữ liệu. KHÔNG gọi initApp(): nó đăng ký lại mọi listener
            // (nút Tools có 2 listener toggle -> mở rồi đóng ngay, phím tắt chạy 2 lần...)
            await Promise.all([fetchSettings(), fetchDevice(), fetchTracks(), fetchPlaylists()]);
            alert(`iPod redetected: ${res.device.model} loaded at ${res.mountpoint}`);
        } else {
            alert("No iPod detected.");
        }
    } catch (e) {
        console.error(e);
    }
}

// Update column sorting header arrows
function updateHeaderArrows() {
    document.querySelectorAll('.tracks-table th').forEach(th => {
        const col = th.dataset.sort;
        if (!col) return;
        
        let textSpan = th.querySelector('.th-text');
        if (!textSpan) {
            textSpan = document.createElement('span');
            textSpan.classList.add('th-text');
            const childNodes = Array.from(th.childNodes);
            childNodes.forEach(node => {
                if (node.nodeType === Node.TEXT_NODE) {
                    textSpan.appendChild(node);
                }
            });
            th.insertBefore(textSpan, th.firstChild);
        }
        
        let text = textSpan.textContent.replace(/ [▲▼]/g, '');
        if (state.sortColumn === col) {
            text += state.sortDirection === 'asc' ? ' ▲' : ' ▼';
        }
        textSpan.textContent = text;
    });
}

// Make table columns resizable by dragging
function makeColumnsResizable() {
    const table = document.querySelector('.tracks-table');
    if (!table) return;
    
    const headers = table.querySelectorAll('th');
    headers.forEach((header) => {
        if (header.querySelector('.resizer')) return;
        
        const resizer = document.createElement('div');
        resizer.classList.add('resizer');
        header.appendChild(resizer);
        
        resizer.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            
            const startX = e.clientX;
            const startWidth = header.offsetWidth;
            
            const onMouseMove = (moveEvent) => {
                const newWidth = startWidth + (moveEvent.clientX - startX);
                if (newWidth > 50) { // minimum column width
                    header.style.width = `${newWidth}px`;
                }
            };
            
            const onMouseUp = () => {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                header.classList.remove('th-resizing');
            };
            
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            header.classList.add('th-resizing');
        });
    });
}

// ======================================================================
// Settings, track export (with conversion), library export
// ======================================================================
const SAMPLE_RATE_LABELS = { 0: 'Keep original', 44100: '44.1 kHz', 48000: '48 kHz', 96000: '96 kHz' };
const FLAC_LEVELS = [0, 1, 2, 3, 4, 5, 6, 7, 8];

async function fetchSettings() {
    try {
        const [settingsRes, formatsRes] = await Promise.all([fetch('/api/settings'), fetch('/api/formats')]);
        state.settings = await settingsRes.json();
        state.formats = await formatsRes.json();
    } catch (e) {
        console.error('Failed to load settings', e);
    }
}

function fillSelect(select, items, selected) {
    select.innerHTML = '';
    items.forEach(({ value, label }) => {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        if (String(value) === String(selected)) opt.selected = true;
        select.appendChild(opt);
    });
}

function formatById(id) {
    return ((state.formats && state.formats.formats) || []).find(f => f.id === id);
}

function bitrateItems() {
    const all = new Set();
    ((state.formats && state.formats.formats) || []).forEach(f => f.bitrates.forEach(b => all.add(b)));
    return [...all].sort((a, b) => a - b).map(b => ({ value: b, label: `${b} kbps` }));
}

const sampleRateItems = () => Object.entries(SAMPLE_RATE_LABELS).map(([v, l]) => ({ value: v, label: l }));
const flacLevelItems = () =>
    FLAC_LEVELS.map(l => ({ value: l, label: l === 0 ? '0 (fastest)' : l === 8 ? '8 (smallest)' : String(l) }));

function formatItems() {
    const ffmpeg = state.formats && state.formats.ffmpeg_available;
    return ((state.formats && state.formats.formats) || []).map(f => ({
        value: f.id,
        label: f.id === 'original' || ffmpeg ? f.label : `${f.label} (needs ffmpeg)`,
    }));
}

function setStatus(el, text, kind = '') {
    el.className = `form-status ${kind}`;
    el.textContent = text;
}

// Shows "Saved to <path>" plus a "Show" button when running inside the desktop app
function setSavedStatus(el, path) {
    setStatus(el, `Saved to ${path}`, 'ok');
    if (window.klmm && window.klmm.showItemInFolder) {
        const btn = document.createElement('button');
        btn.className = 'btn secondary';
        btn.textContent = 'Show';
        btn.addEventListener('click', () => window.klmm.showItemInFolder(path));
        el.appendChild(btn);
    }
}

// Filename from Content-Disposition (RFC 5987 filename* first, then filename)
function filenameFromDisposition(disposition, fallbackName) {
    const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition || '');
    if (star) return decodeURIComponent(star[1]);
    const plain = /filename="?([^";]+)"?/i.exec(disposition || '');
    return plain ? plain[1] : fallbackName;
}

// Download a response as a file (browser save / Electron save dialog)
async function saveResponseAsFile(res, fallbackName) {
    const name = filenameFromDisposition(res.headers.get('Content-Disposition'), fallbackName);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    return name;
}

async function errorText(res) {
    try {
        const data = await res.json();
        return data.error || `HTTP ${res.status}`;
    } catch (e) {
        return `HTTP ${res.status}`;
    }
}

// ---------------- Settings modal
async function openSettings() {
    await fetchSettings();
    const s = state.settings;
    if (!s) return;
    document.getElementById('set-export-dir').value = s.export_dir;
    fillSelect(document.getElementById('set-export-format'), formatItems(), s.export_format);
    fillSelect(document.getElementById('set-bitrate'), bitrateItems(), s.export_options.bitrate_kbps);
    fillSelect(document.getElementById('set-sample-rate'), sampleRateItems(), s.export_options.sample_rate);
    fillSelect(document.getElementById('set-flac-level'), flacLevelItems(), s.export_options.flac_level);
    document.getElementById('set-read-only').checked = s.read_only;
    document.getElementById('set-stream').checked = s.stream_unsupported;
    document.getElementById('set-ipod-convert').value = s.ipod_import_convert || 'auto';
    document.getElementById('set-ffmpeg-path').value = s.ffmpeg_path;
    document.getElementById('set-auto-rescan').checked = s.auto_rescan_idle;
    document.getElementById('set-idle-minutes').value = s.auto_rescan_idle_minutes;
    document.getElementById('set-rescan-hours').value = s.auto_rescan_interval_hours;
    const last = s.last_auto_rescan ? new Date(s.last_auto_rescan).toLocaleString() : 'never';
    document.getElementById('set-rescan-hint').textContent =
        `Off by default. Only new, changed or deleted files are read. Last library scan: ${last}.`;
    const ffStatus = document.getElementById('set-ffmpeg-status');
    const ffOk = state.formats && state.formats.ffmpeg_available;
    ffStatus.textContent = ffOk
        ? `Using: ${state.formats.ffmpeg_path}`
        : 'ffmpeg not found: only "Original" export works and streaming is off.';
    ffStatus.className = ffOk ? 'form-hint' : 'form-hint warn';
    document.getElementById('settings-error').textContent = '';
    showModal('settings-modal');
}

async function saveSettings() {
    const errEl = document.getElementById('settings-error');
    const wasReadOnly = state.settings.read_only;
    const payload = {
        export_dir: document.getElementById('set-export-dir').value.trim(),
        export_format: document.getElementById('set-export-format').value,
        export_options: {
            bitrate_kbps: parseInt(document.getElementById('set-bitrate').value, 10),
            sample_rate: parseInt(document.getElementById('set-sample-rate').value, 10),
            flac_level: parseInt(document.getElementById('set-flac-level').value, 10),
        },
        read_only: document.getElementById('set-read-only').checked,
        stream_unsupported: document.getElementById('set-stream').checked,
        ipod_import_convert: document.getElementById('set-ipod-convert').value,
        ffmpeg_path: document.getElementById('set-ffmpeg-path').value.trim(),
        auto_rescan_idle: document.getElementById('set-auto-rescan').checked,
        auto_rescan_idle_minutes: parseInt(document.getElementById('set-idle-minutes').value, 10),
        auto_rescan_interval_hours: parseInt(document.getElementById('set-rescan-hours').value, 10),
    };
    try {
        const res = await fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            errEl.textContent = await errorText(res);
            return;
        }
        state.settings = await res.json();
        closeModal('settings-modal');
        // Read-only changes which buttons exist: reload the UI to apply cleanly
        if (state.settings.read_only !== wasReadOnly) {
            window.location.reload();
        } else {
            await fetchSettings();
        }
    } catch (e) {
        errEl.textContent = `Cannot save settings: ${e}`;
    }
}

async function browseInto(inputId, kind) {
    if (!window.klmm) return;
    const path = kind === 'file' ? await window.klmm.selectFile() : await window.klmm.selectFolder();
    if (path) document.getElementById(inputId).value = path;
}

// ---------------- Export track modal
async function openExportModal(trackId) {
    await fetchSettings();
    const track = state.tracks.find(t => t.id === trackId);
    if (!track || !state.settings) return;
    state.exportTrackId = trackId;
    const s = state.settings;
    document.getElementById('export-track-name').textContent = `${track.artist} - ${track.title}`;
    document.getElementById('exp-folder-path').textContent = s.export_dir;
    fillSelect(document.getElementById('exp-format'), formatItems(), s.export_format);
    fillSelect(document.getElementById('exp-sample-rate'), sampleRateItems(), s.export_options.sample_rate);
    fillSelect(document.getElementById('exp-flac-level'), flacLevelItems(), s.export_options.flac_level);
    updateExportOptions();
    setStatus(document.getElementById('export-status'), '');
    showModal('export-modal');
}

// Show only the options that apply to the chosen format
function updateExportOptions() {
    const id = document.getElementById('exp-format').value;
    const fmt = formatById(id);
    const ffmpeg = state.formats && state.formats.ffmpeg_available;
    const converting = id !== 'original';
    document.getElementById('exp-bitrate-group').style.display = fmt && fmt.lossy ? '' : 'none';
    document.getElementById('exp-flac-group').style.display = id === 'flac' ? '' : 'none';
    document.getElementById('exp-sample-rate-group').style.display = converting ? '' : 'none';
    if (fmt && fmt.lossy) {
        const preferred = state.settings.export_options.bitrate_kbps;
        const selected = fmt.bitrates.includes(preferred) ? preferred : fmt.default_bitrate;
        fillSelect(
            document.getElementById('exp-bitrate'),
            fmt.bitrates.map(b => ({ value: b, label: `${b} kbps` })),
            selected,
        );
    }
    const hint = document.getElementById('exp-ffmpeg-hint');
    hint.textContent = converting && !ffmpeg ? 'ffmpeg not found: set its path in Settings.' : '';
    hint.className = 'form-hint warn';
    document.getElementById('export-submit-btn').disabled = converting && !ffmpeg;
}

async function submitExport() {
    const statusEl = document.getElementById('export-status');
    const btn = document.getElementById('export-submit-btn');
    const format = document.getElementById('exp-format').value;
    const destination = document.querySelector('input[name="exp-dest"]:checked').value;
    const options = {
        sample_rate: parseInt(document.getElementById('exp-sample-rate').value, 10) || 0,
        flac_level: parseInt(document.getElementById('exp-flac-level').value, 10),
    };
    const fmt = formatById(format);
    if (fmt && fmt.lossy) options.bitrate_kbps = parseInt(document.getElementById('exp-bitrate').value, 10);
    btn.disabled = true;
    setStatus(statusEl, format === 'original' ? 'Copying...' : 'Converting...');
    try {
        const res = await fetch(`/api/tracks/export/${state.exportTrackId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ format, options, destination }),
        });
        if (!res.ok) {
            setStatus(statusEl, `Export failed: ${await errorText(res)}`, 'error');
        } else if (destination === 'folder') {
            setSavedStatus(statusEl, (await res.json()).path);
        } else {
            const name = await saveResponseAsFile(res, 'track');
            setStatus(statusEl, `Downloaded ${name}`, 'ok');
        }
    } catch (e) {
        setStatus(statusEl, `Export failed: ${e}`, 'error');
    } finally {
        btn.disabled = false;
    }
}

// ---------------- Library export modal
async function openLibraryExport(kind = 'tracks') {
    await fetchSettings();
    document.querySelector(`input[name="lib-kind"][value="${kind}"]`).checked = true;
    document.getElementById('lib-folder-path').textContent = (state.settings && state.settings.export_dir) || '';
    const pl = state.currentPlaylistName;
    document.getElementById('lib-scope-playlist-label').style.display = pl ? '' : 'none';
    document.getElementById('lib-scope-playlist-name').textContent = pl || '';
    if (!pl) document.querySelector('input[name="lib-scope"][value="all"]').checked = true;
    updateLibraryExportForm();
    setStatus(document.getElementById('library-export-status'), '');
    showModal('library-export-modal');
}

function updateLibraryExportForm() {
    const kind = document.querySelector('input[name="lib-kind"]:checked').value;
    document.getElementById('lib-scope-group').style.display = kind === 'tracks' ? '' : 'none';
    document.getElementById('library-export-title').textContent =
        kind === 'tracks' ? 'Export Track List' : 'Export Library Info';
}

async function submitLibraryExport() {
    const statusEl = document.getElementById('library-export-status');
    const kind = document.querySelector('input[name="lib-kind"]:checked').value;
    const format = document.querySelector('input[name="lib-format"]:checked').value;
    const destination = document.querySelector('input[name="lib-dest"]:checked').value;
    const params = new URLSearchParams({ format });
    if (kind === 'tracks' && document.querySelector('input[name="lib-scope"]:checked').value === 'playlist') {
        params.set('playlist', state.currentPlaylistName);
    }
    if (destination === 'folder') params.set('destination', 'folder');
    const url = `/api/library/${kind === 'tracks' ? 'tracks' : 'info'}?${params}`;
    setStatus(statusEl, 'Exporting...');
    try {
        const res = await fetch(url);
        if (!res.ok) {
            setStatus(statusEl, `Export failed: ${await errorText(res)}`, 'error');
        } else if (destination === 'folder') {
            setSavedStatus(statusEl, (await res.json()).path);
        } else {
            const base = kind === 'tracks' ? 'klmm-tracks' : 'klmm-library';
            const name = await saveResponseAsFile(res, `${base}.${format}`);
            setStatus(statusEl, `Downloaded ${name}`, 'ok');
        }
    } catch (e) {
        setStatus(statusEl, `Export failed: ${e}`, 'error');
    }
}

function setupSettingsAndExport() {
    const onClick = (id, fn) =>
        document.getElementById(id).addEventListener('click', e => {
            e.preventDefault();
            fn();
        });
    onClick('tool-settings', openSettings);
    onClick('tool-export-tracks', () => openLibraryExport('tracks'));
    onClick('tool-export-library', () => openLibraryExport('info'));
    onClick('settings-save-btn', saveSettings);
    onClick('set-export-dir-browse', () => browseInto('set-export-dir', 'folder'));
    onClick('set-ffmpeg-browse', () => browseInto('set-ffmpeg-path', 'file'));
    onClick('export-submit-btn', submitExport);
    onClick('library-export-submit-btn', submitLibraryExport);
    document.getElementById('exp-format').addEventListener('change', updateExportOptions);
    document.querySelectorAll('input[name="lib-kind"]').forEach(r =>
        r.addEventListener('change', updateLibraryExportForm),
    );
}

// Entry points for the Electron application menu (main process calls these)
window.klmmUI = {
    openSettings,
    openLibraryExport,
};
