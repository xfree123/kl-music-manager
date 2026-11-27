# Personalizing KL Music Manager

This repository carries the identity of its publisher, [xfree123](https://github.com/xfree123). If you fork
it and publish your own build, replace these values with yours. Tests (`tests/test_version.py`) check that
`version.py` and `package.json` agree.

## 1. Required for a fork: your identity

| File | Key | Current value | Notes |
|---|---|---|---|
| `package.json` | `author` | `xfree123` | Shown in About; may be `"Name <email>"` |
| `package.json` | `homepage` | `https://github.com/xfree123/kl-music-manager` | Shown in About |
| `package.json` | `repository.url` | `https://github.com/xfree123/kl-music-manager.git` | |
| `package.json` | `build.appId` | `io.github.xfree123.klmusicmanager` | Reverse-DNS ID of the installed app. **Pick it once** before your first public release: a different appId installs as a separate app instead of upgrading. |
| `package.json` | `build.copyright` | `Copyright © 2026 xfree123` | Written into the .exe file properties |
| `version.py` | `AUTHOR`, `HOMEPAGE` | same as `package.json` | Must match `author` / `homepage` exactly |
| `README.md` | `## License` copyright line | `xfree123` | |

Keep `LICENSE` unchanged (it is the verbatim GPLv3 text) and keep the **Origin** section of
`THIRD_PARTY_NOTICES.md` and the **Credits** section of `README.md`: the GPL requires the credit to the
original project and a note that the work was modified.

## 2. Optional: version

`package.json` `version` and `version.py` `VERSION` (must match), then add a section to `CHANGELOG.md`.

## 3. Optional: logo and colors

- Logo: edit the colors / shapes at the top of `packaging/make_logo.py`, then run
  `python packaging/make_logo.py`. It regenerates `static/icons/app-icon.png`, `app-icon-32.png` and
  `packaging/icon-512.png` (the installer icon).
- Interface accent color: `--color-accent` / `--color-accent-hover` in `static/style.css`.
- Icons: the interface uses [Lucide](https://lucide.dev) icons from `static/icons/sprite.svg`. To add one,
  append its Lucide name to `ICONS` in `packaging/make_icon_sprite.py`, run
  `python packaging/make_icon_sprite.py`, and use it as
  `<svg class="icon"><use href="icons/sprite.svg#NAME"></use></svg>`.
- Font: Lexend (`static/fonts/`). To change it, replace the `.ttf` + `OFL.txt` and the `@font-face` in
  `static/style.css` and `static/help/index.html`; `tests/test_assets.py` checks the font covers
  Vietnamese.

## 4. Optional: renaming the app

The display name "KL Music Manager" appears in `package.json` (`productName`, `build.productName`),
`version.py` (`APP_NAME`), `electron/main.js` (`APP_NAME`), `static/index.html`, `static/help/*`,
the launchers and the docs. Executable names use dashes: `build.executableName` in `package.json`,
`packaging/kl-music-manager-backend.spec` and `BACKEND_NAME` in `electron/lib.js`.
Renaming `productName` also moves the data folder (`%APPDATA%\<productName>`).

## 5. Check and build

```bash
python -m pip install -r requirements-dev.txt   # once (in a virtualenv)
npm install                                     # once; if Electron is "not installed": node node_modules/electron/install.js
python packaging/fetch_ffmpeg.py                # once: static ffmpeg "essentials" build (SHA-256 checked)
python scripts/check.py                         # lint, format, Python + JS tests
npm run dist                                    # installer in dist/
```

`packaging/vendor-ffmpeg/` and `node_modules/` are not in git, so a fresh clone needs the three
"once" steps. The build stops with a clear message if one is missing.
