# Changelog

## 1.1.0 — 2026-11-27

### Added
- **File details of the playing track**: codec, bitrate, sample rate, bit depth, channels and file size in Now Playing (short form in the top bar).
- **Several libraries**: each music folder is a named library in the sidebar; add, rename, open, rescan, rebuild or clear them (*Tools → Manage Libraries…*).
- **Library database** (SQLite, `library_cache/library.db`) for tags and file details, replacing the per-folder JSON cache: editing one track no longer rewrites the whole cache, and grouped / indexed lookups are fast.
- **Richer tag editor** for music folders: album artist, composer, total tracks, disc / total discs, BPM, comment, lyrics, and **album art** (choose an image or remove it, optionally for the whole album). Works for MP3, M4A (AAC/ALAC), FLAC, OGG, Opus, WAV and AIFF. iPod tracks gain album artist and composer.
- **Browse** tab: tag cloud of genres, artists, albums (with covers), years and playlists; click an item to filter the library.
- **Maintenance** (*Tools → Maintenance…*): database and cache sizes, clear cache, rescan all libraries.
- Optional **rescan when the computer is idle** (Settings, off by default, desktop app).
- Embedded cover art in OGG / Opus files is now shown.
- **Manage** tab (Ctrl+M): select many tracks (checkboxes, Shift-click, whole albums / artists / genres / playlists) and **export them in one go** with one format for the whole list, to a chosen folder (Artist / Album folders or flat, optional subfolder, skip files that already exist). Exports run as a queue with progress and Cancel; music folders export up to 4 tracks in parallel, the iPod one at a time.
- **Default library**: an empty virtual iPod that is always in the Libraries list and cannot be removed. The **iPod** entry is shown only while an iPod is connected.
- **Import into an iPod converts formats it cannot play** (FLAC, OGG, Opus, WAV with DTS) with ffmpeg before copying: by default lossless → 16-bit ALAC, lossy → AAC 256 kbps, stereo, at most 48 kHz (Settings: auto / AAC / MP3 / ALAC / don't convert). Such files were refused before. The import result shows the conversion, e.g. "converted FLAC → ALAC".
- Removing a library is now done only in the Manage tab; the library that is open can be removed too (the app switches to the Default library). Music files are never deleted.

### Fixed
- **iPod Classic (6G) showed no tracks or playlists after any change made by the app.** Its database carries both checksums (hash58 and hash72); only hash72 was updated, so the iPod rejected the stale hash58. Both are now written (hash72 first, hash58 last) according to the device's checksum type. To repair an affected iPod: open it and run *Tools → Repair Checksums*, then eject it safely.
- WAV files that contain a DTS stream (DTS-CD / DTS-WAV) played as white noise: they are now detected, shown as codec *DTS* with their real channel count, and converted to stereo FLAC for playback.

### Changed
- A newly created virtual iPod (Default library) is empty: no more demo "Welcome" track.
- New interface icons from [Lucide](https://lucide.dev) (ISC) replace the icons inherited from Floola; they follow the theme colors.
- New application logo and installer icon (original artwork, `packaging/make_logo.py`).
- UI font is now Lexend (SIL OFL), which covers every Vietnamese character; the previous font (Outfit) lacked most Vietnamese letters with diacritics.
- Project identity separated from Floola-Next: package name `kl-music-manager`, new app ID, environment variables `KLMM_*` (were `FLOOLA_*`), renderer API `window.klmm`. Author, homepage and app ID are placeholders (see `PERSONALIZE.md`).
- About shows the author and homepage.

### Removed
- Automatic copy of settings from a Floola-Next installation.

## 1.0.0 — 2026-11-26

First release of **KL Music Manager** (formerly Floola-Next). Windows 10/11 x64 installer.

### Highlights
- Desktop app (Electron) with a bundled backend and ffmpeg — no Python or browser needed.
- Music player: queue, shuffle, repeat, volume, keyboard shortcuts, OS media keys / Windows media overlay.
- Now Playing view with album art, real-time spectrum analyzer (bars / wave) or both.
- Libraries: iPod (USB disk mode) or any music folder (tag cache, `.m3u8` playlists).
- Whole-library search that ignores Vietnamese accents.
- Multi-file / folder import straight into a playlist.
- Export with conversion to MP3, AAC, FLAC, ALAC, WAV; track list and library reports (HTML / JSON).
- Apple Lossless playback through on-the-fly FLAC conversion.
- Settings screen, read-only mode, built-in user guide (Vietnamese and English).

### Performance and size
- Opening an iPod: 2.7 s → 0.18 s from the second time on (USB identification is cached per volume); app start with a 2 000-track iPod ≈ 1.1–1.4 s.
- Installer 184 MB → 151 MB: ffmpeg "essentials" build instead of the full build, only English/Vietnamese Chromium locales, unused Pillow plugins removed, maximum NSIS compression.
- The UI font ships with the app (no request to Google Fonts; works offline).

### Fixes since the preview builds
- Parallel streaming requests for the same ALAC track no longer fail with HTTP 500.
- Tools menu keeps working after *Re-detect iPod*.
- *Show in Explorer* selects the file even when its path contains spaces.
- Empty iPod playlists are found again on import (no duplicate playlists).
- Track and playlist names are shown as text, never interpreted as HTML.
- Upload file names cannot escape the temporary folder.
- `config.json` saved with a byte-order mark (Notepad) is read correctly.
- Playlists can be deleted from the sidebar (×); playlist names with special characters work.

### Known limitations
- Installer is not code-signed (SmartScreen warning).
- macOS and Linux packages are configured but not built or tested yet.
- Mac-formatted (HFS+) iPods cannot be read on Windows.
