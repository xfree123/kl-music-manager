// Logic thuần của Electron shell — tách khỏi main.js để test bằng node --test.
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const { spawn } = require('node:child_process');

// Tên file thực thi backend (PyInstaller, packaging/kl-music-manager-backend.spec): dùng "-", không khoảng trắng
const BACKEND_NAME = 'KL-Music-Manager-Backend';

/** Lệnh chạy backend Flask: bản đóng gói (PyInstaller) hoặc python của .venv khi dev. */
function resolveBackend({ isPackaged, appRoot, resourcesPath, platform, exists = fs.existsSync }) {
    const win = platform === 'win32';
    if (isPackaged) {
        const exe = path.join(resourcesPath, 'backend', win ? `${BACKEND_NAME}.exe` : BACKEND_NAME);
        return { command: exe, args: [], cwd: path.dirname(exe) };
    }
    const venvPython = win
        ? path.join(appRoot, '.venv', 'Scripts', 'python.exe')
        : path.join(appRoot, '.venv', 'bin', 'python');
    const command = exists(venvPython) ? venvPython : win ? 'python' : 'python3';
    return { command, args: [path.join(appRoot, 'app.py')], cwd: appRoot };
}

/** ffmpeg đóng kèm bộ cài ("" khi dev hoặc không có — backend tự tìm trên PATH). */
function resolveFfmpeg({ isPackaged, resourcesPath, platform, exists = fs.existsSync }) {
    if (!isPackaged) return '';
    const exe = path.join(resourcesPath, 'ffmpeg', platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg');
    return exists(exe) ? exe : '';
}

/** Biến môi trường cho backend (xem app.py main(), settings.data_dir(), converter.find_ffmpeg()). */
function backendEnv(baseEnv, { port, dataDir, ffmpeg }) {
    const env = { ...baseEnv, KLMM_PORT: String(port), KLMM_NO_BROWSER: '1', PYTHONIOENCODING: 'utf-8' };
    if (dataDir) env.KLMM_DATA_DIR = dataDir;
    if (ffmpeg) env.KLMM_FFMPEG = ffmpeg;
    return env;
}

/** Cổng TCP trống trên 127.0.0.1. */
function findFreePort() {
    return new Promise((resolve, reject) => {
        const srv = net.createServer();
        srv.unref();
        srv.on('error', reject);
        srv.listen(0, '127.0.0.1', () => {
            const { port } = srv.address();
            srv.close(() => resolve(port));
        });
    });
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

/** Chờ backend trả 200 ở `url`. Lỗi nếu quá timeout hoặc process backend đã thoát. */
async function waitForBackend(url, { timeoutMs = 60000, intervalMs = 300, fetchImpl = fetch, isAlive = () => true } = {}) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (!isAlive()) throw new Error('Backend process exited during startup');
        try {
            const res = await fetchImpl(url);
            if (res.ok) return;
        } catch (e) {
            // chưa lắng nghe — thử lại
        }
        await sleep(intervalMs);
    }
    throw new Error(`Backend did not start within ${Math.round(timeoutMs / 1000)}s`);
}

/** Dừng backend kèm process con (bootloader PyInstaller tạo process con trên Windows). */
function killTree(child, platform = process.platform, spawnImpl = spawn) {
    if (!child || !child.pid) return;
    if (platform === 'win32') {
        spawnImpl('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
    } else {
        child.kill('SIGTERM');
    }
}

// Quét lại thư viện khi máy rảnh: bật trong cài đặt, rảnh đủ số phút, và đã qua khoảng cách giờ
// kể từ lần quét trước (lastRunIso rỗng / sai = chưa quét lần nào).
function shouldAutoRescan({ enabled, idleSeconds, idleMinutes, lastRunIso, intervalHours, now = new Date() }) {
    if (!enabled || idleSeconds < idleMinutes * 60) return false;
    const last = Date.parse(lastRunIso || '');
    if (Number.isNaN(last)) return true;
    return now.getTime() - last >= intervalHours * 3600 * 1000;
}

module.exports = { BACKEND_NAME, resolveBackend, resolveFfmpeg, backendEnv, findFreePort, waitForBackend, killTree, shouldAutoRescan };
