// Electron shell: chạy backend Flask (cổng trống, chỉ 127.0.0.1) rồi mở cửa sổ app.
// Env:
//   KLMM_SMOKE=<file.png>  chụp cửa sổ sau khi tải xong rồi thoát (kiểm thử tự động)
//   KLMM_SMOKE_JS=<js>     (kèm KLMM_SMOKE) chạy JS trong trang trước khi chụp
//   KLMM_DATA_DIR          ghi đè thư mục dữ liệu (mặc định: bản đóng gói = userData,
//                            dev = thư mục project như `python app.py`)
const { app, BrowserWindow, Menu, dialog, ipcMain, powerMonitor, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const lib = require('./lib');

const APP_ROOT = path.resolve(__dirname, '..');
const SMOKE_PNG = process.env.KLMM_SMOKE || '';

let backend = null;
let backendExited = false;
let mainWindow = null;
let quitting = false;

const APP_NAME = 'KL Music Manager';

function dataDir() {
    if (process.env.KLMM_DATA_DIR) return process.env.KLMM_DATA_DIR;
    return app.isPackaged ? app.getPath('userData') : '';
}

function logFile() {
    const dir = path.join(app.getPath('userData'), 'logs');
    fs.mkdirSync(dir, { recursive: true });
    return path.join(dir, 'backend.log');
}

async function startBackend() {
    const port = await lib.findFreePort();
    const { command, args, cwd } = lib.resolveBackend({
        isPackaged: app.isPackaged,
        appRoot: APP_ROOT,
        resourcesPath: process.resourcesPath,
        platform: process.platform,
    });
    const ffmpeg = lib.resolveFfmpeg({
        isPackaged: app.isPackaged,
        resourcesPath: process.resourcesPath,
        platform: process.platform,
    });
    const out = fs.openSync(logFile(), 'w');
    backend = spawn(command, args, {
        cwd,
        env: lib.backendEnv(process.env, { port, dataDir: dataDir(), ffmpeg }),
        stdio: ['ignore', out, out],
        windowsHide: true,
    });
    backendExited = false;
    backend.on('exit', code => {
        backendExited = true;
        if (!quitting) {
            dialog.showErrorBox(APP_NAME, `The backend stopped unexpectedly (code ${code}).\nLog: ${logFile()}`);
            app.quit();
        }
    });
    backend.on('error', err => {
        backendExited = true;
        if (!quitting) dialog.showErrorBox(APP_NAME, `Cannot start the backend: ${err.message}`);
    });
    const base = `http://127.0.0.1:${port}`;
    await lib.waitForBackend(`${base}/api/device`, { timeoutMs: 90000, isAlive: () => !backendExited });
    return base;
}

function stopBackend() {
    if (backend && !backendExited) lib.killTree(backend);
}

// Gọi hàm UI trong trang (static/app.js: window.klmmUI)
function ui(call) {
    if (mainWindow) mainWindow.webContents.executeJavaScript(`window.klmmUI && window.klmmUI.${call}`);
}

function buildMenu() {
    const isMac = process.platform === 'darwin';
    const template = [
        ...(isMac ? [{ role: 'appMenu' }] : []),
        {
            label: 'File',
            submenu: [
                { label: 'Export Track List…', click: () => ui("openLibraryExport('tracks')") },
                { label: 'Export Library Info…', click: () => ui("openLibraryExport('info')") },
                { type: 'separator' },
                { label: 'Settings…', accelerator: 'CmdOrCtrl+,', click: () => ui('openSettings()') },
                { type: 'separator' },
                isMac ? { role: 'close' } : { role: 'quit' },
            ],
        },
        { role: 'editMenu' },
        {
            label: 'Library',
            submenu: [
                { label: 'Open Music Folder…', accelerator: 'CmdOrCtrl+O', click: () => ui('openFolder()') },
                { label: 'Use iPod', click: () => ui('useIpod()') },
                { label: 'Library Source…', click: () => ui('openSourceDialog()') },
                { label: 'Manage Libraries…', click: () => ui('openLibraries()') },
                { label: 'Maintenance…', click: () => ui('openMaintenance()') },
                { type: 'separator' },
                { label: 'Import Files…', accelerator: 'CmdOrCtrl+I', click: () => ui('importFiles()') },
                { label: 'Import Folder…', accelerator: 'CmdOrCtrl+Shift+I', click: () => ui('importFolder()') },
            ],
        },
        {
            label: 'Playback',
            submenu: [
                // Không đặt accelerator Space/←/→: trang đã xử lý, tránh bắt phím khi đang gõ chữ
                { label: 'Play / Pause', click: () => ui('togglePlay()') },
                { label: 'Next Track', click: () => ui('nextTrack()') },
                { label: 'Previous Track', click: () => ui('prevTrack()') },
                { type: 'separator' },
                { label: 'Now Playing', accelerator: 'CmdOrCtrl+L', click: () => ui('showNowPlaying()') },
                { label: 'Library View', click: () => ui('showLibrary()') },
                { label: 'Browse (Tag Cloud)', accelerator: 'CmdOrCtrl+B', click: () => ui('showBrowse()') },
                { label: 'Manage (Select & Export)', accelerator: 'CmdOrCtrl+M', click: () => ui('showManage()') },
            ],
        },
        {
            label: 'View',
            submenu: [
                { role: 'reload' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
                { type: 'separator' },
                { role: 'togglefullscreen' },
            ],
        },
        {
            label: 'Help',
            submenu: [
                // F1 do trang xử lý (không đặt accelerator để không bắt phím 2 lần)
                { label: 'User Guide (F1)', click: () => ui('openHelp()') },
                { label: 'Keyboard Shortcuts', click: () => ui("openHelp('shortcuts')") },
                { label: 'Troubleshooting', click: () => ui("openHelp('troubleshooting')") },
                { type: 'separator' },
                { label: 'Open Data Folder', click: () => shell.openPath(dataDir() || APP_ROOT) },
                { label: 'Open Backend Log', click: () => shell.openPath(logFile()) },
                { type: 'separator' },
                { label: `About ${APP_NAME}`, click: () => ui('openAbout()') },
            ],
        },
    ];
    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function registerIpc() {
    ipcMain.handle('klmm:select-folder', async () => {
        const r = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory', 'createDirectory'] });
        return r.canceled ? '' : r.filePaths[0];
    });
    ipcMain.handle('klmm:select-file', async () => {
        const r = await dialog.showOpenDialog(mainWindow, { properties: ['openFile'] });
        return r.canceled ? '' : r.filePaths[0];
    });
    ipcMain.handle('klmm:select-audio-files', async () => {
        const r = await dialog.showOpenDialog(mainWindow, {
            properties: ['openFile', 'multiSelections'],
            filters: [
                { name: 'Audio', extensions: ['mp3', 'm4a', 'm4b', 'aac', 'flac', 'wav', 'ogg', 'oga', 'opus', 'aif', 'aiff'] },
                { name: 'All files', extensions: ['*'] },
            ],
        });
        return r.canceled ? [] : r.filePaths;
    });
    ipcMain.handle('klmm:show-item-in-folder', (_e, filePath) => {
        if (typeof filePath === 'string' && filePath) shell.showItemInFolder(filePath);
    });
    // Mở một thư mục (vd. thư mục gốc của lần export hàng loạt); chỉ nhận thư mục có thật
    ipcMain.handle('klmm:open-folder', async (_e, dirPath) => {
        if (typeof dirPath !== 'string' || !dirPath) return false;
        try {
            if (!fs.statSync(dirPath).isDirectory()) return false;
        } catch {
            return false;
        }
        return (await shell.openPath(dirPath)) === '';
    });
}

// Quét lại thư viện khi máy rảnh (cài đặt auto_rescan_idle, mặc định tắt). Backend kiểm lại
// khoảng cách giờ (only_if_due) nên gọi trùng cũng không quét thừa.
const IDLE_CHECK_MS = 60 * 1000;
let idleBusy = false;

async function idleRescanTick(baseUrl) {
    if (idleBusy || quitting) return;
    idleBusy = true;
    try {
        const cfg = await (await fetch(`${baseUrl}/api/settings`)).json();
        const due = lib.shouldAutoRescan({
            enabled: cfg.auto_rescan_idle,
            idleSeconds: powerMonitor.getSystemIdleTime(),
            idleMinutes: cfg.auto_rescan_idle_minutes,
            lastRunIso: cfg.last_auto_rescan,
            intervalHours: cfg.auto_rescan_interval_hours,
        });
        if (!due) return;
        const res = await fetch(`${baseUrl}/api/libraries/rescan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ only_if_due: true }),
        });
        const result = await res.json();
        if (result && result.active_changed) ui('onLibraryRescanned()');
    } catch (err) {
        console.log(`[idle-rescan] ${err && err.message}`);
    } finally {
        idleBusy = false;
    }
}

async function createWindow(baseUrl) {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 820,
        minWidth: 900,
        minHeight: 600,
        title: APP_NAME,
        backgroundColor: '#0f172a',
        icon: path.join(APP_ROOT, 'static', 'icons', 'app-icon.png'),
        show: !SMOKE_PNG,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    // Link ngoài mở bằng trình duyệt mặc định, không mở cửa sổ Electron mới
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        if (/^https?:\/\//.test(url) && !url.startsWith(baseUrl)) shell.openExternal(url);
        return { action: 'deny' };
    });
    mainWindow.webContents.on('will-navigate', (event, url) => {
        if (!url.startsWith(baseUrl)) {
            event.preventDefault();
            shell.openExternal(url);
        }
    });
    if (SMOKE_PNG) {
        mainWindow.webContents.once('did-finish-load', () => {
            setTimeout(async () => {
                if (process.env.KLMM_SMOKE_JS) {
                    try {
                        // userGesture=true: như người dùng bấm (cho phép phát âm thanh khi kiểm thử)
                        const result = await mainWindow.webContents.executeJavaScript(process.env.KLMM_SMOKE_JS, true);
                        console.log(`[smoke] js result: ${JSON.stringify(result)}`);
                    } catch (err) {
                        console.log(`[smoke] js error: ${err && err.message}`);
                    }
                    await new Promise(r => setTimeout(r, 1500));
                }
                const image = await mainWindow.webContents.capturePage();
                fs.writeFileSync(SMOKE_PNG, image.toPNG());
                app.quit();
            }, 4000);
        });
    }
    await mainWindow.loadURL(baseUrl);
}

if (!app.requestSingleInstanceLock()) {
    app.quit();
} else {
    app.on('second-instance', () => {
        if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.focus();
        }
    });

    app.whenReady().then(async () => {
        buildMenu();
        registerIpc();
        try {
            const baseUrl = await startBackend();
            await createWindow(baseUrl);
            if (!SMOKE_PNG) setInterval(() => idleRescanTick(baseUrl), IDLE_CHECK_MS);
        } catch (err) {
            dialog.showErrorBox(APP_NAME, `${err.message}\nLog: ${logFile()}`);
            quitting = true;
            stopBackend();
            app.quit();
        }
    });

    app.on('before-quit', () => {
        quitting = true;
        stopBackend();
    });
    app.on('window-all-closed', () => app.quit());
}
