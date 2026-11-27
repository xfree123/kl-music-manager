// Trang Browse: tag cloud theo genre / artist / album / year / playlist (KlmmTagCloud).
// Bấm một mục -> về Library, lọc theo mục đó (chip lọc trên thanh công cụ, nút ✕ để bỏ).
// Dùng state / renderTracks / renderPlaylists (app.js), showView / artworkUrl (player.js).

const BROWSE_LABELS = { genre: 'Genre', artist: 'Artist', album: 'Album', year: 'Year', playlist: 'Playlist' };
const BROWSE_LIMIT = 300; // số mục tối đa mỗi cloud (artist/album có thể hàng nghìn)
const browseState = { by: localStorage.getItem('browseBy') || 'genre' };

function hueIndex(text) {
    let h = 0;
    for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
    return h % 6;
}

function renderBrowse() {
    const by = browseState.by;
    document.querySelectorAll('#browse-tabs .browse-tab').forEach(b => b.classList.toggle('active', b.dataset.by === by));
    const all = KlmmTagCloud.groups(state.tracks, by, { playlists: state.playlists });
    const shown = all.length > BROWSE_LIMIT
        ? KlmmTagCloud.groups(state.tracks, by, { playlists: state.playlists, limit: BROWSE_LIMIT })
        : all;
    const summary = document.getElementById('browse-summary');
    const noun = `${BROWSE_LABELS[by].toLowerCase()}${all.length === 1 ? '' : 's'}`;
    summary.textContent = all.length > shown.length
        ? `Top ${shown.length} of ${all.length} ${noun} · ${state.tracks.length} tracks`
        : `${all.length} ${noun} · ${state.tracks.length} tracks`;

    // album: ảnh bìa nhỏ của bài đầu tiên trong album
    const firstTrack = new Map();
    if (by === 'album') {
        for (const t of state.tracks) {
            const key = KlmmTagCloud.normalize(t.album);
            if (key && !firstTrack.has(key)) firstTrack.set(key, t.id);
        }
    }

    const cloud = document.getElementById('tag-cloud');
    if (!shown.length) {
        const empty = document.createElement('div');
        empty.className = 'tag-cloud-empty';
        empty.textContent = by === 'playlist' ? 'No playlists with tracks yet.' : `No ${BROWSE_LABELS[by].toLowerCase()} information in this library.`;
        cloud.replaceChildren(empty);
        return;
    }
    cloud.replaceChildren(...shown.map(g => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `tag w${g.weight} hue${hueIndex(g.key)}`;
        btn.title = `${g.label}: ${g.count} track${g.count === 1 ? '' : 's'}`;
        const id = firstTrack.get(g.key);
        if (id !== undefined) {
            const img = document.createElement('img');
            img.className = 'tag-cover';
            img.loading = 'lazy';
            img.alt = '';
            img.src = artworkUrl(id);
            img.addEventListener('error', () => img.remove());
            btn.appendChild(img);
        }
        const label = document.createElement('span');
        label.className = 'tag-label';
        label.textContent = g.label;
        const count = document.createElement('span');
        count.className = 'tag-count';
        count.textContent = g.count;
        btn.append(label, count);
        btn.addEventListener('click', () => chooseBrowseGroup(by, g));
        return btn;
    }));
}

function chooseBrowseGroup(by, group) {
    document.querySelectorAll('.category-list li').forEach(li => li.classList.toggle('active', li.dataset.category === 'all' && by !== 'playlist'));
    if (typeof clearSearch === 'function') clearSearch();
    if (by === 'playlist') {
        setBrowseFilter(null, false);
        state.currentPlaylistName = group.key;
        state.currentCategory = null;
        renderPlaylists();
    } else {
        state.currentPlaylistName = null;
        state.currentCategory = 'all';
        document.querySelectorAll('.playlist-list li').forEach(li => li.classList.remove('active'));
        setBrowseFilter({ by, key: group.key, label: group.label }, false);
    }
    showView('library');
    renderTracks();
}

/** Đặt / bỏ (filter=null) bộ lọc Browse; rerender=true thì vẽ lại bảng ngay. */
function setBrowseFilter(filter, rerender = true) {
    state.browseFilter = filter;
    const chip = document.getElementById('browse-chip');
    chip.hidden = !filter;
    const text = filter ? `${BROWSE_LABELS[filter.by]}: ${filter.label}` : '';
    document.getElementById('browse-chip-text').textContent = text;
    chip.title = text;
    if (rerender) renderTracks();
}

function setupBrowse() {
    document.getElementById('view-browse-btn').addEventListener('click', () => showView('browse'));
    document.querySelectorAll('#browse-tabs .browse-tab').forEach(btn =>
        btn.addEventListener('click', () => {
            browseState.by = btn.dataset.by;
            localStorage.setItem('browseBy', browseState.by);
            renderBrowse();
        }),
    );
    document.getElementById('browse-chip-clear').addEventListener('click', () => setBrowseFilter(null));
}

document.addEventListener('DOMContentLoaded', setupBrowse);

window.klmmUI = Object.assign(window.klmmUI || {}, {
    showBrowse: () => showView('browse'),
});
