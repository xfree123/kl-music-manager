// Logic thuần của Electron shell (không cần chạy Electron): node --test electron/tests
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');

const lib = require('../lib');

test('dev backend uses the project .venv python on Windows', () => {
    const appRoot = path.join('C:', 'proj');
    const exists = p => p === path.join(appRoot, '.venv', 'Scripts', 'python.exe');
    const b = lib.resolveBackend({ isPackaged: false, appRoot, resourcesPath: '', platform: 'win32', exists });
    assert.equal(b.command, path.join(appRoot, '.venv', 'Scripts', 'python.exe'));
    assert.deepEqual(b.args, [path.join(appRoot, 'app.py')]);
    assert.equal(b.cwd, appRoot);
});

test('dev backend falls back to python on PATH when there is no .venv', () => {
    const b = lib.resolveBackend({ isPackaged: false, appRoot: '/p', resourcesPath: '', platform: 'darwin', exists: () => false });
    assert.equal(b.command, 'python3');
    const w = lib.resolveBackend({ isPackaged: false, appRoot: 'C:\\p', resourcesPath: '', platform: 'win32', exists: () => false });
    assert.equal(w.command, 'python');
});

test('packaged backend is the frozen executable in resources', () => {
    const res = path.join('C:', 'App', 'resources');
    const b = lib.resolveBackend({ isPackaged: true, appRoot: '', resourcesPath: res, platform: 'win32', exists: () => true });
    assert.equal(b.command, path.join(res, 'backend', 'KL-Music-Manager-Backend.exe'));
    assert.deepEqual(b.args, []);
    const m = lib.resolveBackend({ isPackaged: true, appRoot: '', resourcesPath: '/R', platform: 'darwin', exists: () => true });
    assert.equal(m.command, path.join('/R', 'backend', 'KL-Music-Manager-Backend'));
});

test('bundled ffmpeg only when packaged and present', () => {
    const res = path.join('C:', 'App', 'resources');
    const exe = path.join(res, 'ffmpeg', 'ffmpeg.exe');
    assert.equal(lib.resolveFfmpeg({ isPackaged: true, resourcesPath: res, platform: 'win32', exists: p => p === exe }), exe);
    assert.equal(lib.resolveFfmpeg({ isPackaged: true, resourcesPath: res, platform: 'win32', exists: () => false }), '');
    assert.equal(lib.resolveFfmpeg({ isPackaged: false, resourcesPath: res, platform: 'win32', exists: () => true }), '');
});

test('backend env carries port, no-browser, data dir and ffmpeg', () => {
    const env = lib.backendEnv({ PATH: 'x' }, { port: 5123, dataDir: 'D:\\data', ffmpeg: 'C:\\ff.exe' });
    assert.equal(env.PATH, 'x');
    assert.equal(env.KLMM_PORT, '5123');
    assert.equal(env.KLMM_NO_BROWSER, '1');
    assert.equal(env.KLMM_DATA_DIR, 'D:\\data');
    assert.equal(env.KLMM_FFMPEG, 'C:\\ff.exe');
    assert.equal(env.PYTHONIOENCODING, 'utf-8');
    const dev = lib.backendEnv({}, { port: 1, dataDir: '', ffmpeg: '' });
    assert.equal('KLMM_DATA_DIR' in dev, false);
    assert.equal('KLMM_FFMPEG' in dev, false);
});

test('findFreePort returns a usable port', async () => {
    const port = await lib.findFreePort();
    assert.ok(Number.isInteger(port) && port > 0 && port < 65536);
    const server = http.createServer().listen(port, '127.0.0.1');
    await new Promise(r => server.once('listening', r));
    server.close();
});

test('waitForBackend resolves once the health URL answers 200', async () => {
    let calls = 0;
    const fetchImpl = async () => {
        calls += 1;
        if (calls < 3) throw new Error('ECONNREFUSED');
        return { ok: true };
    };
    await lib.waitForBackend('http://x/api/device', { timeoutMs: 2000, intervalMs: 5, fetchImpl });
    assert.equal(calls, 3);
});

test('waitForBackend rejects after the timeout', async () => {
    const fetchImpl = async () => { throw new Error('ECONNREFUSED'); };
    await assert.rejects(
        lib.waitForBackend('http://x/api/device', { timeoutMs: 50, intervalMs: 5, fetchImpl }),
        /did not start/,
    );
});

test('waitForBackend stops early when the process has exited', async () => {
    const fetchImpl = async () => { throw new Error('ECONNREFUSED'); };
    await assert.rejects(
        lib.waitForBackend('http://x/api/device', { timeoutMs: 5000, intervalMs: 5, fetchImpl, isAlive: () => false }),
        /exited/,
    );
});

test('killTree uses taskkill on Windows and signal elsewhere', () => {
    const calls = [];
    lib.killTree({ pid: 42, kill: s => calls.push(['kill', s]) }, 'win32', (cmd, args) => calls.push([cmd, args]));
    assert.deepEqual(calls, [['taskkill', ['/pid', '42', '/T', '/F']]]);
    calls.length = 0;
    lib.killTree({ pid: 42, kill: s => calls.push(['kill', s]) }, 'darwin', () => calls.push(['spawn']));
    assert.deepEqual(calls, [['kill', 'SIGTERM']]);
});

test('packaged executables use dashes, no spaces', () => {
    const pkg = require('../../package.json');
    assert.equal(pkg.build.executableName, 'KL-Music-Manager');
    assert.ok(!/\s/.test(pkg.build.executableName));
    assert.ok(!/\s/.test(lib.BACKEND_NAME));
    assert.equal(pkg.build.extraResources[0].from, `packaging/out/backend-dist/${lib.BACKEND_NAME}`);
});

test('auto rescan only when enabled, idle long enough and interval passed', () => {
    const now = new Date('2026-11-26T12:00:00');
    const base = { enabled: true, idleSeconds: 20 * 60, idleMinutes: 15, lastRunIso: '2026-11-25T10:00:00', intervalHours: 24, now };
    assert.equal(lib.shouldAutoRescan(base), true);
    assert.equal(lib.shouldAutoRescan({ ...base, enabled: false }), false);
    assert.equal(lib.shouldAutoRescan({ ...base, idleSeconds: 14 * 60 }), false);
    assert.equal(lib.shouldAutoRescan({ ...base, lastRunIso: '2026-11-26T01:00:00' }), false);
    assert.equal(lib.shouldAutoRescan({ ...base, lastRunIso: '' }), true);
    assert.equal(lib.shouldAutoRescan({ ...base, lastRunIso: 'garbage' }), true);
});
