// Player: hàng đợi (KlmmQueue), điều khiển, view Now Playing (ảnh bìa / spectrum),
// phím tắt, Media Session (phím media của OS, overlay Windows SMTC / macOS Now Playing).
// Dùng state / formatTime / showModal ... của app.js (script thường, chung phạm vi global).
// URL ảnh bìa; state.artVersion tăng sau khi sửa ảnh -> bỏ qua cache trình duyệt (max-age 1 giờ)
function artworkUrl(id) {
    return `/api/tracks/${id}/artwork?v=${state.artVersion || 0}`;
}

const Player = (() => {
    const $ = id => document.getElementById(id);
    const audio = $('audio-preview-player');
    const queue = new KlmmQueue.PlayQueue();
    const els = {};
    let viz = null;
    let volume = clamp(parseFloat(localStorage.getItem('volume') ?? '1'), 0, 1);
    let muted = localStorage.getItem('muted') === 'true';
    let npMode = localStorage.getItem('npMode') || 'cover';
    let seeking = false;
    let view = 'library';
    let lastPositionUpdate = 0;

    function clamp(v, lo, hi) {
        return Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : hi;
    }

    function trackById(id) {
        return state.tracksById ? state.tracksById.get(id) : state.tracks.find(t => t.id === id);
    }

    // ---------------------------------------------------------------- âm thanh / spectrum
    function ensureAudioGraph() {
        if (viz) {
            viz.ensureContext();
            return;
        }
        try {
            viz = new KlmmSpectrum.Visualizer(audio, els.canvas);
            viz.mode = localStorage.getItem('vizStyle') || 'bars';
            viz.ensureContext();
        } catch (e) {
            console.warn('Web Audio unavailable; spectrum disabled', e);
            viz = null;
        }
        applyVolume();
    }

    function applyVolume() {
        const v = muted ? 0 : volume;
        if (viz && viz.gain) {
            audio.volume = 1;
            viz.setVolume(v);
        } else {
            audio.volume = v;
        }
        els.volumeSlider.value = String(muted ? 0 : volume);
        setIcon(els.volumeIcon, KlmmIcons.volumeIcon(v)); // setIcon('volume-x' | 'volume' | 'volume-1' | 'volume-2')
        els.muteBtn.title = muted ? 'Unmute (M)' : 'Mute (M)';
    }

    function setVolume(v) {
        volume = clamp(v, 0, 1);
        muted = volume === 0 ? muted : false;
        localStorage.setItem('volume', String(volume));
        localStorage.setItem('muted', String(muted));
        applyVolume();
    }

    function toggleMute() {
        muted = !muted;
        localStorage.setItem('muted', String(muted));
        applyVolume();
    }

    function updateVizRunning() {
        if (!viz) return;
        const visible = view === 'nowplaying' && npMode !== 'cover';
        if (visible && !audio.paused) viz.start();
        else viz.stop();
    }

    // ---------------------------------------------------------------- phát
    /** Phát bài `id` với danh sách ngữ cảnh = các bài đang hiển thị (sau lọc/tìm/sắp xếp). */
    function playFromList(id) {
        const ids = state.visibleTrackIds && state.visibleTrackIds.includes(id) ? state.visibleTrackIds : [id];
        queue.setList(ids, id);
        load(id);
    }

    function load(id) {
        const track = trackById(id);
        if (!track) return;
        state.currentPlayingTrackId = id;
        ensureAudioGraph();
        highlightPlaying();
        showTrackInfo(track);
        setArtwork(id);
        loadFileInfo(id);
        if (state.settings && state.settings.stream_unsupported) {
            els.artist.textContent = `${track.artist} (preparing…)`;
        }
        els.seek.disabled = false;
        audio.src = `/api/tracks/play/${id}`;
        audio
            .play()
            .then(() => {
                if (state.currentPlayingTrackId === id) els.artist.textContent = track.artist;
            })
            .catch(err => handlePlaybackError(track, err));
        updateMediaSession(track);
        renderQueue();
    }

    function next(auto = false) {
        const id = queue.next({ auto });
        if (id === null) {
            // Hết danh sách: dừng ở cuối bài
            audio.pause();
            setPlayIcon(false);
            return;
        }
        if (auto && id === state.currentPlayingTrackId) {
            audio.currentTime = 0;
            audio.play();
            return;
        }
        load(id);
    }

    function prev() {
        if (audio.currentTime > 3) {
            audio.currentTime = 0;
            return;
        }
        const id = queue.prev();
        if (id !== null) load(id);
    }

    function togglePlay() {
        if (!audio.getAttribute('src') || state.currentPlayingTrackId === null) {
            const id = state.selectedTrackId ?? (state.visibleTrackIds || [])[0];
            if (id !== undefined && id !== null) playFromList(id);
            return;
        }
        ensureAudioGraph();
        if (audio.paused) audio.play();
        else audio.pause();
    }

    function seekBy(seconds) {
        if (!Number.isFinite(audio.duration)) return;
        audio.currentTime = clamp(audio.currentTime + seconds, 0, audio.duration);
    }

    // Trình duyệt không phát được: file có -> định dạng không hỗ trợ (vd ALAC khi tắt stream
    // hoặc không có ffmpeg) -> mở bằng System Player; file không có -> báo lỗi.
    async function handlePlaybackError(track, err) {
        if (err && err.name === 'AbortError') return; // đã chuyển bài khác
        console.warn('Browser playback failed', err);
        // Chỉ "không giải mã được" mới chuyển sang System Player. NotAllowedError (chính sách
        // autoplay: chưa có thao tác người dùng) không được mở app ngoài — chỉ chờ bấm Play.
        const mediaCode = audio.error ? audio.error.code : 0; // 3 = DECODE, 4 = SRC_NOT_SUPPORTED
        const unsupported = (err && err.name === 'NotSupportedError') || mediaCode === 3 || mediaCode === 4;
        if (!unsupported) {
            if (state.currentPlayingTrackId === track.id) {
                els.artist.textContent = `${track.artist} (press Play to start)`;
                setPlayIcon(false);
            }
            return;
        }
        let exists = false;
        try {
            const res = await fetch(`/api/tracks/play/${track.id}`, { headers: { Range: 'bytes=0-0' } });
            if (res.body) res.body.cancel();
            exists = res.ok;
        } catch (e) {
            exists = false;
        }
        if (state.currentPlayingTrackId !== track.id) return;
        if (exists) {
            await playSystemTrack(track.id);
            els.artist.textContent = `${track.artist} (System Player — format not supported by the player)`;
        } else {
            els.title.textContent = 'Error: Track not found';
            els.artist.textContent = 'Make sure the file exists in the library';
            setPlayIcon(false);
        }
    }

    // ---------------------------------------------------------------- hiển thị
    function setPlayIcon(playing) {
        setIcon(els.playIcon, playing ? 'pause' : 'play');
        els.playBtn.title = playing ? 'Pause (Space)' : 'Play (Space)';
    }

    function highlightPlaying() {
        document.querySelectorAll('.tracks-table tbody tr').forEach(row => {
            row.classList.toggle('playing', Number(row.dataset.id) === state.currentPlayingTrackId);
        });
    }

    function showTrackInfo(track) {
        els.title.textContent = track.title;
        els.artist.textContent = track.artist;
        els.npTitle.textContent = track.title;
        els.npArtist.textContent = track.artist || '';
        const extra = [track.album, track.year ? String(track.year) : ''].filter(Boolean).join(' · ');
        els.npAlbum.textContent = extra;
        document.title = `${track.title} — ${track.artist || 'KL Music Manager'}`;
    }

    // Codec / bitrate / sample rate / bit depth / kênh / dung lượng của bài đang phát
    async function loadFileInfo(id) {
        els.format.textContent = '';
        els.npFormat.replaceChildren();
        els.format.title = '';
        let d = null;
        try {
            const res = await fetch(`/api/tracks/${id}/details`);
            if (res.ok) d = await res.json();
        } catch (e) {
            console.warn('Cannot load file info', e);
        }
        if (!d || state.currentPlayingTrackId !== id) return;
        els.format.textContent = KlmmTrackInfo.short(d);
        els.format.title = KlmmTrackInfo.summary(d);
        for (const part of KlmmTrackInfo.parts(d)) {
            const chip = document.createElement('span');
            chip.className = 'np-format-chip';
            chip.textContent = part;
            els.npFormat.appendChild(chip);
        }
    }

    function refreshArtwork() {
        if (state.currentPlayingTrackId) setArtwork(state.currentPlayingTrackId);
    }

    function setArtwork(id) {
        const url = artworkUrl(id);
        const apply = ok => {
            els.npCover.hidden = !ok;
            els.npPlaceholder.hidden = ok;
            els.miniArt.hidden = !ok;
            els.miniPlaceholder.hidden = ok;
            els.backdrop.style.backgroundImage = ok ? `url("${url}")` : 'none';
        };
        const img = new Image();
        img.onload = () => {
            if (state.currentPlayingTrackId !== id) return;
            els.npCover.src = url;
            els.miniArt.src = url;
            apply(true);
        };
        img.onerror = () => {
            if (state.currentPlayingTrackId === id) apply(false);
        };
        img.src = url;
    }

    function setNpMode(mode) {
        npMode = mode;
        localStorage.setItem('npMode', mode);
        els.visual.dataset.mode = mode;
        document.querySelectorAll('.np-mode[data-mode]').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
        if (mode !== 'cover') ensureAudioGraph();
        updateVizRunning();
    }

    function toggleVizStyle() {
        const style = (viz ? viz.mode : localStorage.getItem('vizStyle') || 'bars') === 'bars' ? 'wave' : 'bars';
        localStorage.setItem('vizStyle', style);
        if (viz) viz.mode = style;
        els.styleBtn.textContent = style === 'bars' ? 'Bars' : 'Wave';
    }

    function showView(name) {
        view = name;
        $('now-playing-view').hidden = name !== 'nowplaying';
        $('browse-view').hidden = name !== 'browse';
        $('manage-view').hidden = name !== 'manage';
        document.querySelector('.tracks-pane').hidden = name !== 'library';
        $('view-library-btn').classList.toggle('active', name === 'library');
        $('view-nowplaying-btn').classList.toggle('active', name === 'nowplaying');
        $('view-browse-btn').classList.toggle('active', name === 'browse');
        $('view-manage-btn').classList.toggle('active', name === 'manage');
        if (name === 'browse' && typeof renderBrowse === 'function') renderBrowse();
        if (name === 'manage' && typeof renderManage === 'function') renderManage();
        if (name === 'nowplaying') renderQueue();
        updateVizRunning();
    }

    function updateShuffleRepeatUI() {
        els.shuffleBtn.classList.toggle('on', queue.shuffle);
        els.shuffleBtn.title = `Shuffle: ${queue.shuffle ? 'on' : 'off'} (S)`;
        els.repeatBtn.classList.toggle('on', queue.repeat !== 'off');
        els.repeatBadge.hidden = queue.repeat !== 'one';
        els.repeatBtn.title = `Repeat: ${queue.repeat} (R)`;
        const parts = [queue.shuffle ? 'Shuffle' : '', queue.repeat === 'all' ? 'Repeat all' : queue.repeat === 'one' ? 'Repeat one' : ''];
        els.queueMode.textContent = parts.filter(Boolean).join(' · ');
    }

    function toggleShuffle() {
        queue.setShuffle(!queue.shuffle);
        localStorage.setItem('shuffle', String(queue.shuffle));
        updateShuffleRepeatUI();
        renderQueue();
    }

    function cycleRepeat() {
        queue.cycleRepeat();
        localStorage.setItem('repeat', queue.repeat);
        updateShuffleRepeatUI();
        renderQueue();
    }

    function renderQueue() {
        const list = els.queueList;
        list.innerHTML = '';
        const manual = new Set(queue.manual);
        const ids = queue.upcoming(50);
        if (!ids.length) {
            const li = document.createElement('li');
            li.className = 'np-queue-empty';
            li.textContent = state.currentPlayingTrackId === null ? 'Nothing queued yet.' : 'End of the list.';
            list.appendChild(li);
            return;
        }
        ids.forEach((id, i) => {
            const t = trackById(id);
            if (!t) return;
            const li = document.createElement('li');
            li.className = 'np-queue-item' + (i < queue.manual.length && manual.has(id) ? ' manual' : '');
            const title = document.createElement('span');
            title.className = 'q-title';
            title.textContent = t.title;
            const artist = document.createElement('span');
            artist.className = 'q-artist';
            artist.textContent = t.artist;
            li.append(title, artist);
            if (li.classList.contains('manual')) {
                const rm = document.createElement('button');
                rm.className = 'q-remove';
                rm.title = 'Remove from queue';
                rm.textContent = '×';
                rm.addEventListener('click', e => {
                    e.stopPropagation();
                    queue.removeFromQueue(id);
                    renderQueue();
                });
                li.appendChild(rm);
            }
            li.addEventListener('dblclick', () => {
                if (li.classList.contains('manual')) {
                    queue.removeFromQueue(id);
                    queue.playNext(id);
                    next();
                } else if (queue.jumpTo(id) !== null) {
                    load(id);
                }
            });
            li.title = 'Double-click to play';
            list.appendChild(li);
        });
    }

    function enqueue(id, mode) {
        if (id === null || id === undefined) return;
        if (state.currentPlayingTrackId === null) {
            playFromList(id);
            return;
        }
        if (mode === 'next') queue.playNext(id);
        else queue.addToQueue(id);
        renderQueue();
    }

    // ---------------------------------------------------------------- Media Session
    function updateMediaSession(track) {
        if (!('mediaSession' in navigator)) return;
        navigator.mediaSession.metadata = new MediaMetadata({
            title: track.title,
            artist: track.artist,
            album: track.album,
            artwork: [{ src: `${location.origin}${artworkUrl(track.id)}`, sizes: '600x600', type: 'image/jpeg' }],
        });
    }

    function setupMediaSession() {
        if (!('mediaSession' in navigator)) return;
        const ms = navigator.mediaSession;
        const handlers = {
            play: () => audio.play(),
            pause: () => audio.pause(),
            previoustrack: prev,
            nexttrack: () => next(),
            seekbackward: d => seekBy(-(d.seekOffset || 10)),
            seekforward: d => seekBy(d.seekOffset || 10),
            seekto: d => {
                if (Number.isFinite(d.seekTime)) audio.currentTime = d.seekTime;
            },
        };
        for (const [action, fn] of Object.entries(handlers)) {
            try {
                ms.setActionHandler(action, fn);
            } catch (e) {
                // hành động không được hỗ trợ trên nền tảng này
            }
        }
    }

    function updatePositionState() {
        if (!('mediaSession' in navigator) || !Number.isFinite(audio.duration)) return;
        const now = Date.now();
        if (now - lastPositionUpdate < 1000) return;
        lastPositionUpdate = now;
        try {
            navigator.mediaSession.setPositionState({
                duration: audio.duration,
                position: Math.min(audio.currentTime, audio.duration),
                playbackRate: audio.playbackRate,
            });
        } catch (e) {
            // bỏ qua: một số nền tảng không hỗ trợ
        }
    }

    // ---------------------------------------------------------------- phím tắt
    function isTyping(target) {
        const tag = (target && target.tagName) || '';
        return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (target && target.isContentEditable);
    }

    function onKeyDown(e) {
        if (isTyping(e.target) || document.querySelector('.modal-overlay.show')) return;
        const key = e.key;
        if (key === ' ') {
            e.preventDefault();
            togglePlay();
        } else if (key === 'ArrowRight' || key === 'ArrowLeft') {
            e.preventDefault();
            const forward = key === 'ArrowRight';
            if (e.ctrlKey || e.metaKey) forward ? next() : prev();
            else seekBy(forward ? 5 : -5);
        } else if (key === 'ArrowUp' || key === 'ArrowDown') {
            e.preventDefault();
            setVolume(volume + (key === 'ArrowUp' ? 0.05 : -0.05));
        } else if ((key === 'm' || key === 'M') && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            showView('manage'); // Ctrl+M (bản desktop: menu View cũng gọi)
        } else if (key === 'm' || key === 'M') {
            toggleMute();
        } else if (key === 's' || key === 'S') {
            toggleShuffle();
        } else if (key === 'r' || key === 'R') {
            cycleRepeat();
        } else if (key === 'n' || key === 'N') {
            showView(view === 'nowplaying' ? 'library' : 'nowplaying');
        }
    }

    // ---------------------------------------------------------------- khởi tạo
    function setup() {
        Object.assign(els, {
            playBtn: $('play-pause-btn'),
            playIcon: $('play-icon'),
            seek: $('seek-slider'),
            cur: $('current-time'),
            total: $('total-time'),
            title: $('current-track-title'),
            artist: $('current-track-artist'),
            miniArt: $('mini-art-img'),
            miniPlaceholder: document.querySelector('#mini-art .art-placeholder'),
            shuffleBtn: $('shuffle-btn'),
            repeatBtn: $('repeat-btn'),
            repeatBadge: $('repeat-one-badge'),
            muteBtn: $('mute-btn'),
            volumeIcon: $('volume-icon'),
            volumeSlider: $('volume-slider'),
            canvas: $('np-spectrum'),
            visual: $('np-visual'),
            npCover: $('np-cover-img'),
            npPlaceholder: $('np-cover-placeholder'),
            backdrop: $('np-backdrop'),
            npTitle: $('np-title'),
            npArtist: $('np-artist'),
            npAlbum: $('np-album'),
            npFormat: $('np-format'),
            format: $('current-track-format'),
            styleBtn: $('np-style-btn'),
            queueList: $('np-queue-list'),
            queueMode: $('np-queue-mode'),
        });

        queue.setShuffle(localStorage.getItem('shuffle') === 'true');
        queue.setRepeat(localStorage.getItem('repeat') || 'off');
        updateShuffleRepeatUI();
        els.styleBtn.textContent = (localStorage.getItem('vizStyle') || 'bars') === 'bars' ? 'Bars' : 'Wave';
        applyVolume();
        setNpMode(npMode);

        els.playBtn.addEventListener('click', togglePlay);
        $('prev-btn').addEventListener('click', prev);
        $('next-btn').addEventListener('click', () => next());
        els.shuffleBtn.addEventListener('click', toggleShuffle);
        els.repeatBtn.addEventListener('click', cycleRepeat);
        els.muteBtn.addEventListener('click', toggleMute);
        els.volumeSlider.addEventListener('input', e => setVolume(parseFloat(e.target.value)));
        $('mini-art').addEventListener('click', () => showView('nowplaying'));
        $('view-library-btn').addEventListener('click', () => showView('library'));
        $('view-nowplaying-btn').addEventListener('click', () => showView('nowplaying'));
        document.querySelectorAll('.np-mode[data-mode]').forEach(b => b.addEventListener('click', () => setNpMode(b.dataset.mode)));
        els.styleBtn.addEventListener('click', toggleVizStyle);

        els.seek.addEventListener('input', () => {
            seeking = true;
            els.cur.textContent = formatTime(parseFloat(els.seek.value));
        });
        els.seek.addEventListener('change', () => {
            audio.currentTime = parseFloat(els.seek.value);
            seeking = false;
        });

        audio.addEventListener('timeupdate', () => {
            if (!seeking) {
                els.seek.value = String(audio.currentTime);
                els.cur.textContent = formatTime(audio.currentTime);
            }
            updatePositionState();
        });
        audio.addEventListener('durationchange', () => {
            if (Number.isFinite(audio.duration)) {
                els.seek.max = String(audio.duration);
                els.total.textContent = formatTime(audio.duration);
            }
        });
        audio.addEventListener('play', () => {
            setPlayIcon(true);
            if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'playing';
            updateVizRunning();
        });
        audio.addEventListener('pause', () => {
            setPlayIcon(false);
            if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'paused';
            updateVizRunning();
        });
        audio.addEventListener('ended', () => next(true));

        // System Player toggle
        const toggle = $('player-toggle');
        toggle.checked = localStorage.getItem('useSystemPlayer') === 'true';
        toggle.addEventListener('change', () => localStorage.setItem('useSystemPlayer', toggle.checked));

        // Context menu: Play Next / Add to Queue
        $('menu-play-next').addEventListener('click', () => enqueue(state.selectedTrackId, 'next'));
        $('menu-add-queue').addEventListener('click', () => enqueue(state.selectedTrackId, 'queue'));

        document.addEventListener('keydown', onKeyDown);
        setupMediaSession();
    }

    return { setup, playFromList, togglePlay, next, prev, showView, enqueue, queue, audio, refreshArtwork, loadFileInfo };
})();

// Phát bằng trình phát mặc định của hệ điều hành (nút gạt System Player / fallback)
async function playSystemTrack(trackId) {
    const track = state.tracksById ? state.tracksById.get(trackId) : null;
    if (!track) return;
    Player.audio.pause();
    state.currentPlayingTrackId = trackId;
    document.getElementById('current-track-title').textContent = track.title;
    document.getElementById('current-track-artist').textContent = `${track.artist} (System Player)`;
    try {
        await fetch(`/api/tracks/play-system/${trackId}`, { method: 'POST' });
    } catch (e) {
        console.error('Error playing in system player', e);
    }
}

function showView(name) {
    Player.showView(name);
}

window.klmmUI = Object.assign(window.klmmUI || {}, {
    togglePlay: () => Player.togglePlay(),
    nextTrack: () => Player.next(),
    prevTrack: () => Player.prev(),
    showNowPlaying: () => Player.showView('nowplaying'),
    showLibrary: () => Player.showView('library'),
});
