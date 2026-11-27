// Spectrum analyzer: tính toán thuần (dải tần log, mức, đỉnh) + Visualizer vẽ canvas (trình duyệt).
// UMD: trình duyệt -> window.KlmmSpectrum; node (test) -> module.exports.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.KlmmSpectrum = factory();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    /** Chia binCount bin FFT thành `bands` dải đều theo log tần số [fMin, fMax]. Mỗi dải >= 1 bin. */
    function logBands(binCount, sampleRate, bands, fMin = 20, fMax = 20000) {
        const nyquist = sampleRate / 2;
        const hzPerBin = nyquist / binCount;
        const top = Math.min(fMax, nyquist);
        const ratio = Math.log(top / fMin);
        const result = [];
        let prevEnd = Math.max(1, Math.floor(fMin / hzPerBin));
        for (let i = 0; i < bands; i++) {
            const fHigh = fMin * Math.exp((ratio * (i + 1)) / bands);
            let start = prevEnd;
            let end = Math.min(binCount, Math.max(start + 1, Math.round(fHigh / hzPerBin)));
            if (start >= binCount) {
                start = binCount - 1;
                end = binCount;
            }
            result.push([start, end]);
            prevEnd = end;
        }
        return result;
    }

    /** Mức mỗi dải (0..1) = giá trị lớn nhất trong dải của dữ liệu byte (getByteFrequencyData). */
    function bandLevels(data, bands) {
        return bands.map(([s, e]) => {
            let m = 0;
            for (let i = s; i < e; i++) if (data[i] > m) m = data[i];
            return m / 255;
        });
    }

    /** Đỉnh giữ giá trị lớn nhất rồi rơi `decay` mỗi khung hình. */
    function updatePeaks(levels, peaks, decay) {
        return levels.map((v, i) => {
            const fallen = peaks ? peaks[i] - decay : 0;
            return Math.max(v, fallen > 1e-9 ? fallen : 0);
        });
    }

    /** Vẽ spectrum từ một <audio> qua Web Audio API (chỉ chạy trong trình duyệt). */
    class Visualizer {
        constructor(audioEl, canvas) {
            this.audio = audioEl;
            this.canvas = canvas;
            this.mode = 'bars'; // 'bars' | 'wave'
            this.ctx = null;
            this.analyser = null;
            this.bands = null;
            this.peaks = null;
            this.running = false;
            this._frame = this._frame.bind(this);
        }

        /** Gọi trong một thao tác người dùng (chính sách autoplay của Chromium). */
        ensureContext() {
            if (this.ctx) {
                if (this.ctx.state === 'suspended') this.ctx.resume();
                return;
            }
            const Ctx = window.AudioContext || window.webkitAudioContext;
            this.ctx = new Ctx();
            const source = this.ctx.createMediaElementSource(this.audio);
            this.analyser = this.ctx.createAnalyser();
            this.analyser.fftSize = 4096;
            this.analyser.smoothingTimeConstant = 0.78;
            // source -> analyser -> gain -> loa: spectrum đo trước gain (không nhỏ lại theo âm lượng)
            this.gain = this.ctx.createGain();
            source.connect(this.analyser);
            this.analyser.connect(this.gain);
            this.gain.connect(this.ctx.destination);
            this.freq = new Uint8Array(this.analyser.frequencyBinCount);
            this.wave = new Uint8Array(this.analyser.fftSize);
        }

        setVolume(v) {
            if (this.gain) this.gain.gain.value = v;
        }

        start() {
            if (this.running || !this.analyser) return;
            this.running = true;
            requestAnimationFrame(this._frame);
        }

        stop() {
            this.running = false;
        }

        _resize() {
            const dpr = window.devicePixelRatio || 1;
            const w = Math.max(1, Math.round(this.canvas.clientWidth * dpr));
            const h = Math.max(1, Math.round(this.canvas.clientHeight * dpr));
            if (this.canvas.width !== w || this.canvas.height !== h) {
                this.canvas.width = w;
                this.canvas.height = h;
            }
            return [w, h, dpr];
        }

        _frame() {
            if (!this.running) return;
            const g = this.canvas.getContext('2d');
            const [w, h, dpr] = this._resize();
            g.clearRect(0, 0, w, h);
            if (this.mode === 'wave') this._drawWave(g, w, h, dpr);
            else this._drawBars(g, w, h, dpr);
            requestAnimationFrame(this._frame);
        }

        _drawBars(g, w, h, dpr) {
            const count = Math.max(16, Math.min(96, Math.floor(w / (10 * dpr))));
            if (!this.bands || this.bands.length !== count) {
                this.bands = logBands(this.analyser.frequencyBinCount, this.ctx.sampleRate, count);
                this.peaks = null;
            }
            this.analyser.getByteFrequencyData(this.freq);
            const levels = bandLevels(this.freq, this.bands);
            this.peaks = updatePeaks(levels, this.peaks, 0.012);
            const gap = 2 * dpr;
            const bw = (w - gap * (count - 1)) / count;
            const grad = g.createLinearGradient(0, h, 0, 0);
            grad.addColorStop(0, '#0ea5e9');
            grad.addColorStop(0.65, '#38bdf8');
            grad.addColorStop(1, '#e0f2fe');
            for (let i = 0; i < count; i++) {
                const x = i * (bw + gap);
                const bh = Math.max(2 * dpr, levels[i] * h * 0.92);
                g.fillStyle = grad;
                g.fillRect(x, h - bh, bw, bh);
                g.fillStyle = 'rgba(248, 250, 252, 0.85)';
                g.fillRect(x, h - this.peaks[i] * h * 0.92 - 3 * dpr, bw, 2 * dpr);
            }
        }

        _drawWave(g, w, h, dpr) {
            this.analyser.getByteTimeDomainData(this.wave);
            g.lineWidth = 2 * dpr;
            g.strokeStyle = '#38bdf8';
            g.shadowColor = 'rgba(14, 165, 233, 0.6)';
            g.shadowBlur = 8 * dpr;
            g.beginPath();
            const step = this.wave.length / w;
            for (let x = 0; x < w; x++) {
                const v = this.wave[Math.floor(x * step)] / 128 - 1;
                const y = h / 2 + v * h * 0.45;
                if (x === 0) g.moveTo(x, y);
                else g.lineTo(x, y);
            }
            g.stroke();
            g.shadowBlur = 0;
        }
    }

    return { logBands, bandLevels, updatePeaks, Visualizer };
});
