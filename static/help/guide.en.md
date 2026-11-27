# KL Music Manager User Guide

KL Music Manager is a music player and library manager for **classic iPods** (Classic, Nano, Mini, Shuffle) and for **music folders on your computer**. Everything runs locally: no Internet connection is needed and no data leaves your machine.

## System requirements {#requirements}

| Component | Minimum |
|---|---|
| Operating system (installer) | Windows 10 or Windows 11, 64-bit (x64) |
| Disk space | about 450 MB after installation (installer 151 MB) |
| iPod | USB mass-storage iPods (Classic, Nano 1st–5th gen, Mini, Shuffle, Video), **Windows-formatted (FAT32)** |
| Running from source (browser mode) | Python 3.10 or newer on Windows, macOS or Linux |

> macOS 13 Ventura or newer is supported when building from source; release 1.1.1 ships a Windows installer only.

## Installation {#install}

1. Run `KL-Music-Manager-Setup-1.1.1.exe`.
2. Windows SmartScreen may warn because the installer is not code-signed: choose **More info → Run anyway**.
3. Pick an install folder and finish. Start **KL Music Manager** from the Start menu.

## Quick start

1. Plug in your iPod and wait until it shows up as a drive in File Explorer (iPods synced with iTunes need *Enable disk use*).
2. Open KL Music Manager. It finds the iPod automatically; the status bar shows the model and track count.
3. Double-click a track to play it. Click **Now Playing** to see the album art and spectrum.

No iPod? Use a music folder (see below) or the virtual iPod that is created when no iPod is found.

## Library source: iPod or music folder {#library}

The **Library** card at the top of the right sidebar shows the current source. Click **Change** (or *Tools → Library Source…*, or *Library → Open Music Folder…* / Ctrl+O):

- **iPod**: the connected iPod (or the iPod path set in the configuration).
- **Music folder**: any folder on your computer. Sub-folders are scanned and tags (title, artist, album, …) are read. `.m3u` / `.m3u8` files become playlists. Recently opened folders are remembered.

The first scan of a large folder can take a while; later scans use the library database and only read new or changed files. Switching back to the iPod takes a few seconds while its database is read.

### Several libraries {#libraries}

Every music folder you open becomes a **library** in the **Libraries** list of the right sidebar (with its track count). Click a library to switch to it.

- **Default library** is always at the top: an empty virtual iPod on this computer (`virtual_ipod/` in the data folder). It cannot be removed, and the app falls back to it when no iPod is connected or when you remove the library that is open.
- **iPod** appears only while an iPod is connected.
- **+** adds a folder as a new library (it is scanned right away). The ⚙ button, *Tools → Manage Libraries…* or *Library → Manage Libraries…* opens **Libraries & Maintenance**.
- There you can rename a library (edit the name, press Enter), **Open** it, **Rescan** (read new / changed / deleted files), **Rebuild** (re-read the tags of every file) or **Clear** it (delete the indexed metadata; the folder is read again on the next scan).
- **Removing a library** from the app is done only in the [Manage](#manage) tab (**Remove** button), so it cannot happen by a stray click. It deletes the entry and its metadata from the database, never your music files. Removing the library that is open switches to the Default library.
- Tags and file details of every library are kept in a local database (`library_cache/library.db`), which makes opening a large folder fast.

**Tools → Re-detect iPod / Rescan** reloads the iPod or rescans the folder (after plugging in an iPod or copying new files into the folder).

## Browse (tag cloud) {#browse}

The **Browse** tab (Ctrl+B) groups the current library as a tag cloud: **Genres**, **Artists**, **Albums** (with a small cover), **Years** or **Playlists**. The bigger the word, the more tracks it has; hover to see the count.

Click an item to go back to the Library showing only its tracks. A chip such as *Album: Nghe Mưa* appears next to the track count; click its **×** (or pick another category or playlist) to show everything again. Very large libraries show the 300 biggest groups.

## Select many tracks and export them (Manage) {#manage}

The **Manage** tab (Ctrl+M) works on many tracks at once. Music keeps playing while you use it.

- **Select tracks**: click a row to select or unselect it; hold **Shift** and click another row to select everything in between. The box in the column header selects or clears every shown track; **Select shown** selects every track currently shown (after filtering) and **Clear** unselects everything. **Filter tracks…** filters the table like the search box (accent-insensitive).
- **Select whole groups**: the left column has **Albums**, **Artists**, **Genres** and **Playlists** tabs. Click a group to select all of its tracks, click again to unselect them. A box with a dash means the group is partly selected.
- The number of selected tracks and their total size are shown above the table.

**Export…** opens the batch export dialog:

- **Format**: **one format for the whole list** (Original, MP3, AAC, FLAC, ALAC, WAV, see [Exporting](#export)), not per track.
- **Save to folder**: destination folder (the export folder from Settings by default; **Choose…** to pick another).
- **Folders**: *Artist / Album* (a folder per artist with a folder per album inside) or *All in one folder*. **Subfolder** (optional) puts every file in one sub-folder; it is filled in with the playlist name when exactly one playlist is selected.
- **Run at once**: how many tracks are processed at the same time. Music folders can run 1–4 in parallel (*Auto* = by CPU cores, at most 4). The iPod always runs one at a time, because reading from it in parallel is only slower.
- **Skip files that already exist**: a file with the same name in the destination is skipped (exporting again after an interruption only does what is missing). Turn it off to save duplicates as `… (2)`.

Tracks run as a **queue**: the progress bar shows how many are done and how many are running; failed tracks are listed below and do not stop the queue. **Cancel** stops taking new tracks (those already running finish). At the end a summary shows exported / skipped / failed / cancelled counts; **Show Folder** opens the export folder (destination folder + subfolder).

The left column also lists the **Libraries**: open another library, **+ Add** a folder, or **Remove** a library from the app (music files are kept).

## Search

Type in **Search library…** (or press `/` or Ctrl+F). Search covers the **whole library**: title, artist, album, album artist, genre and composer.

- Accents are ignored: `hong nhung` finds *Hồng Nhung*.
- Several words must all match: `trinh cong son khanh ly`.
- Enter plays the first result. Esc or **Clear** resets the search.

## Playing music {#player}

The top bar has previous / play–pause / next, a small cover, the position slider, **Shuffle**, **Repeat** (off → all → one) and volume.

- Double-click a track to play it. The list currently shown (after filtering, searching and sorting) becomes the play queue.
- Playback moves to the next track automatically.
- Right-click a track → **Play Next** (right after the current track) or **Add to Queue** (end of the queue).
- Keyboard media keys and the Windows media overlay control the app.

**Now Playing** (toolbar button, `N`, or click the small cover) shows a large cover on a blurred backdrop and the **Up Next** list. Display modes:

- **Cover**: album art.
- **Spectrum**: real-time spectrum analyzer. **Bars** / **Wave** switches the style.
- **Both**: album art with the spectrum on top.

Under the title, Now Playing shows the **file details** of the current track: codec (MP3, AAC, ALAC, FLAC, Vorbis, Opus, PCM, DTS), bitrate, sample rate, bit depth (lossless files), channels and file size. A short version (codec · bitrate · sample rate) sits at the right of the top bar; hover it for the full line.

Album art comes from, in order: art embedded in the file, a `cover.jpg` / `folder.jpg` in the same folder, then the iPod artwork database.

**Apple Lossless (ALAC)**: the built-in player cannot decode ALAC directly. With *Stream formats the player can't decode* on (the default) the app converts it to FLAC on the fly; the first play of each track waits about a second. With the option off, ALAC tracks open in the Windows default player.

**WAV files containing DTS** ("DTS-CD" rips, albums tagged `[DTS]`, `[DTS-ES]`): the file claims to be PCM but holds DTS surround audio, so playing it directly gives only white noise. The app detects this, shows the codec as *DTS* and converts it to stereo FLAC for playback (same option).

**System Player**: turn this switch on to open every track in the operating system's default player.

## Keyboard shortcuts {#shortcuts}

| Key | Action |
|---|---|
| Space | Play / pause |
| ← / → | Seek back / forward 5 s |
| Ctrl+← / Ctrl+→ | Previous / next track |
| ↑ / ↓ | Volume up / down |
| M | Mute / unmute |
| S | Shuffle on / off |
| R | Cycle repeat mode |
| N | Library ⇄ Now Playing |
| Ctrl+B | Browse (tag cloud) |
| Ctrl+M | Manage (select many tracks, batch export) |
| / or Ctrl+F | Search |
| F1 | Open this guide |
| Ctrl+O | Open a music folder |
| Ctrl+I / Ctrl+Shift+I | Import files / import a folder |
| Ctrl+, | Settings |

## Importing music {#import}

Click **Import** (or drag files onto the track list):

1. Choose files (several at once). The desktop app also has **Files…** and **Folder…** buttons with native dialogs; choosing a folder imports its sub-folders too.
2. **Add to playlist**: an existing playlist, *+ New playlist…*, or *None*.
3. Click **Import**. The list below shows the result for each file.

- Into an iPod: files are copied onto the iPod and added to its database.
  - The iPod plays MP3, AAC, ALAC, WAV and AIFF; those files are copied as they are.
  - FLAC, OGG, Opus and WAV containing DTS do not play on an iPod, so the app **converts them automatically** before copying (needs ffmpeg, bundled with the installer). By default lossless sources (FLAC) become 16-bit ALAC and compressed sources (OGG, Opus, DTS) become AAC 256 kbps; all stereo, at most 48 kHz. Change this in [Settings](#settings).
  - The result list says so, e.g. *imported (converted FLAC → ALAC)*. The original file on your computer is not changed.
- Into a music folder: files are copied to `<folder>/<Artist>/<Album>/` based on their tags.
- When importing a single file, *Edit tags before import* lets you change its tags first.

> Back up your iPod before writing to it for the first time. Read-only mode blocks every write.

## Playlists

- Create: the **+** button next to *Playlists*. Delete: the **×** next to a playlist (music files are kept).
- Add a track: right-click → *Add to Playlist*. Find a track's playlists: right-click → *Show in Playlist*.
- In a music folder, playlists are `.m3u8` files in `<folder>/Playlists/`, so other players can open them.

## Editing track info

Right-click → **Edit Metadata**. On an iPod, changes go into the iPod database; in a music folder they are written into the file's tags. **Delete from iPod** removes the track and its file (after confirmation).

- **Music folder**: title, artist, album artist, album, genre, composer, year, track *n* of *total*, disc *n* of *total*, BPM, comment and lyrics. Works for MP3, M4A (AAC / ALAC), FLAC, OGG, Opus, WAV and AIFF. Leave a field empty to remove it.
- **Album art** (music folders): **Choose image…** (JPEG, PNG, …; resized to at most 1200 px and saved as JPEG inside the file) or **Remove**. Tick **Apply to the whole album** to change every track with the same album and album artist. The change is written when you click **Save Changes**.
- **iPod**: title, artist, album artist, album, genre, composer, year, track number and rating. Album art on the iPod cannot be edited.
- The bottom of the dialog shows the file details and its path.

## Exporting and converting tracks {#export}

Select a track → **Export** (or right-click → *Export to PC*):

| Format | Notes |
|---|---|
| Original | Copies the file as is |
| MP3 | 128–320 kbps |
| AAC (.m4a) | 128–320 kbps |
| FLAC | Lossless, compression 0–8 |
| ALAC (.m4a) | Apple Lossless |
| WAV | 16-bit PCM |

You can also change the sample rate (keep, 44.1, 48 or 96 kHz). Tags and cover art are kept. Save to the **export folder** (default `Music\KL Music Manager`) or choose a location. **Show** opens the folder containing the file.

To export many tracks, a whole album or a playlist at once, use the [Manage](#manage) tab.

## Exporting track lists and library information

*Tools → Export Track List…* or *Export Library Info…*:

- **Track list**: the whole library or the selected playlist.
- **Library information**: device, total tracks / time / size, file types, playlists.
- **HTML** (view or print in a browser) or **JSON** (scripts, backups).

## Settings {#settings}

*Tools → Settings…* (Ctrl+,):

- **Export folder**: where exported files go.
- **Default export format**, **Bitrate**, **Sample rate**, **FLAC compression**: defaults for the export dialog.
- **Read-only mode**: see below.
- **Stream formats the player can't decode**: play ALAC and DTS-in-WAV by converting them automatically.
- **Importing into an iPod**: what happens to files the iPod cannot play when you import them into an iPod.
  - *Convert automatically* (default): lossless becomes ALAC, compressed becomes AAC.
  - *AAC 256 kbps*: plays on every iPod, including the Shuffle and older Nanos, which cannot play ALAC.
  - *MP3 320 kbps*.
  - *ALAC*.
  - *Don't convert*: such files are not imported.
- **ffmpeg path**: leave empty to use the ffmpeg bundled with the installer.
- **Rescan libraries when the computer is idle** (off by default, desktop app only): after the computer has been idle for the set number of minutes, all libraries are rescanned (new, changed and deleted files only), at most once per the set number of hours. The track list refreshes without stopping the music.

## Maintenance {#maintenance}

*Tools → Maintenance…* shows the size of the library database, the album art cache and the streaming cache.

- **Rescan all libraries now**: read new, changed and deleted files of every library.
- **Clear cache**: remove cached album art and the temporary FLAC files made for Apple Lossless playback (a file that is playing right now is kept).
- Per library (in the list above): **Rescan**, **Rebuild** and **Clear**; see *Several libraries*.

## Read-only mode {#read-only}

When on, the app **never writes** to the iPod or the music folder: Import, Delete, tag editing and playlist changes are hidden and blocked on the server side too. Playing, searching, exporting and changing settings still work. Use it when you only want to listen or copy music off the device.

## Troubleshooting {#troubleshooting}

- **iPod not found**: check that the iPod appears as a drive in File Explorer, then *Tools → Re-detect iPod*. Mac-formatted (HFS+) iPods cannot be read on Windows.
- **ALAC tracks do not play in the app**: turn on *Stream formats the player can't decode* in Settings.
- **A WAV file plays only white noise**: it contains DTS. Turn on the option above. If the library was scanned by an older version, *Rebuild* it so the file details show *DTS*.
- **MP3/FLAC/… export shows "needs ffmpeg"**: leave *ffmpeg path* empty to use the bundled copy, or point it at your `ffmpeg.exe`.
- **Backend error message**: *Help → Open Backend Log*; attach the log when reporting a problem.
- **Slow folder scan**: only the first time; tags are stored in the library database for later scans.
- **Wrong or outdated tags after editing files in another program**: *Tools → Maintenance…* → **Rescan** the library, or **Rebuild** to re-read every file.

## Where data is stored {#data}

All app data lives in `%APPDATA%\KL Music Manager` (*Help → Open Data Folder*):

| Item | Contents |
|---|---|
| `config.json` | Settings |
| `library_cache/library.db` | Library database: the list of libraries and the tags / file details of their tracks (SQLite) |
| `virtual_ipod/` | Default library (virtual iPod on this computer) |
| `stream_cache/` | Temporary FLAC copies for ALAC playback (max 1 GB, cleaned automatically) |
| `device_cache.json` | iPod identification (makes opening the iPod faster) |
| `logs/backend.log` | Log of the latest session |

Uninstalling does not remove this folder; delete it manually if you want.

## License {#license}

KL Music Manager is free software under the **GNU GPL version 3 or later**. The installer bundles ffmpeg (GPLv3), Electron/Chromium and other open-source libraries; see `LICENSE` and `THIRD_PARTY_NOTICES.md`.
