/**
 * Blogs — HTML / CSS デモの共通部品 (エディタと記事ページの両方で読み込む)
 *
 * - srcdoc(): iframe の中身。blog/blocks.py の demo_srcdoc と同じ内容を組み立てる
 *   (ただしエディタ用なので、CSS 変数を受け取るスクリプトは入れない。エディタは iframe に直接書き込む)
 * - detectVars(): CSS から「--name: 値」を拾い、スライダー / 色にできるものを返す
 * - varsCss(): CSS 変数を全要素へ上書きする CSS (記事ページの iframe 内スクリプトと同じ規則)
 * - bindCompare(): Before / After の境界をドラッグ・キーボードで動かす
 * - bindControls(): スライダー / 色の入力を CSS 変数として iframe へ届ける
 */
window.BlogDemoKit = (() => {
    const BG = { dark: ['#1c1c1e', '#f5f5f7'], light: ['#ffffff', '#1d1d1f'], checker: ['#2c2c2e', '#f5f5f7'] };
    const CSP = "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
        + "font-src https://fonts.gstatic.com data:; img-src https: data:";
    const UNITS = ['px', '%', 'rem', 'em', 'deg', 'ms', 's', 'vw', 'vh'];
    const MAX_CONTROLS = 8;
    const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)');

    function srcdoc(b, before = false) {
        const [bg, fg] = BG[b.bg] || BG.dark;
        const checker = b.bg === 'checker'
            ? 'background-image:conic-gradient(#3a3a3c 25%,transparent 0 50%,#3a3a3c 0 75%,transparent 0);background-size:20px 20px;'
            : '';
        const center = b.layout === 'top' ? '' : 'display:flex;align-items:center;justify-content:center;';
        const html = before ? (b.beforeHtml || b.html) : b.html;
        const css = before ? b.beforeCss : b.css;
        return '<!DOCTYPE html><html><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width,initial-scale=1">'
            + `<meta http-equiv="Content-Security-Policy" content="${CSP}">`
            + '<style>html,body{margin:0;min-height:100%;}'
            + `body{box-sizing:border-box;min-height:100vh;padding:24px;background:${bg};color:${fg};${checker}${center}`
            + 'font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Arial,sans-serif;}</style>'
            + `<style>${css}</style></head><body>${html}</body></html>`;
    }

    const VAR_RE = /^--[A-Za-z][A-Za-z0-9_-]{0,39}$/;
    const VALUE_RE = /^[#0-9A-Za-z.%-]{1,40}$/;
    /** blog/blocks.py の DEMO_VARS_SCRIPT と同じ規則で、変数を上書きする CSS を作る */
    function varsCss(vars) {
        const decl = Object.entries(vars)
            .filter(([k, v]) => VAR_RE.test(k) && VALUE_RE.test(String(v)))
            .map(([k, v]) => `${k}:${v}!important;`).join('');
        return `:root,*,::before,::after{${decl}}`;
    }

    const round = (n) => Math.round(n * 10000) / 10000;

    /** 値 (例: 12px / 0.6 / #0071e3) から、スライダーの初期範囲を推測する */
    function guessRange(value, unit) {
        const v = Math.abs(value);
        const table = {
            px: [0, Math.max(48, Math.ceil(v * 3)), 1],
            '%': [0, 100, 1],
            rem: [0, Math.max(4, round(v * 3)), 0.05],
            em: [0, Math.max(4, round(v * 3)), 0.05],
            deg: [0, 360, 1],
            s: [0, Math.max(2, round(v * 3)), 0.05],
            ms: [0, Math.max(1000, Math.ceil(v * 3)), 10],
            vw: [0, 100, 1],
            vh: [0, 100, 1],
        };
        if (table[unit]) return table[unit];
        if (v <= 1) return [0, 1, 0.01];
        return [0, Math.ceil(v * 3), v >= 10 ? 1 : 0.1];
    }

    /** CSS の中の「--name: 値;」を、最初に現れた順に返す (同じ名前は最初の 1 つ) */
    function detectVars(css) {
        const found = [];
        const seen = new Set();
        const re = /(--[A-Za-z][A-Za-z0-9_-]{0,39})\s*:\s*([^;{}]+?)\s*(?=[;}])/g;
        const clean = String(css || '').replace(/\/\*[\s\S]*?\*\//g, '');
        let m;
        while ((m = re.exec(clean)) && found.length < 40) {
            const [, name, raw] = m;
            if (seen.has(name)) continue;
            seen.add(name);
            const value = raw.trim();
            let hex = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
            if (hex) {
                let h = hex[1].toLowerCase();
                if (h.length === 3) h = h.split('').map((c) => c + c).join('');
                found.push({ name, kind: 'color', value: `#${h}` });
                continue;
            }
            const num = value.match(/^(-?\d*\.?\d+)([a-z%]*)$/i);
            if (num && (num[2] === '' || UNITS.includes(num[2].toLowerCase()))) {
                found.push({ name, kind: 'range', value: Number(num[1]), unit: num[2].toLowerCase() });
            }
        }
        return found;
    }

    /** 記事に保存するコントロールの形を、検出した変数から作る */
    function controlFromVar(v, label) {
        const c = { name: v.name, label: label || v.name.slice(2), kind: v.kind, value: v.value };
        if (v.kind === 'range') {
            const [min, max, step] = guessRange(v.value, v.unit);
            Object.assign(c, { min: Math.min(min, v.value), max: Math.max(max, v.value), step, unit: v.unit });
        }
        return c;
    }

    const format = (input) => (input.type === 'color' ? input.value : `${round(Number(input.value))}${input.dataset.unit || ''}`);

    /**
     * スライダー / 色の入力を CSS 変数として届ける。
     * @param {HTMLElement} bar  [data-var] の input を含む要素 (data-reset のボタンで元に戻す)
     * @param {(vars: object) => void} apply  {'--name': '12px', ...} を受け取って iframe に反映する
     * @returns {() => object} 今の値を返す関数
     */
    function bindControls(bar, apply) {
        const inputs = [...bar.querySelectorAll('[data-var]')];
        const current = () => Object.fromEntries(inputs.map((i) => [i.dataset.var, format(i)]));
        const refresh = (input) => {
            const out = input.parentElement.querySelector('output');
            if (out) out.textContent = format(input);
            if (input.type === 'range') {
                const p = ((input.value - input.min) / (input.max - input.min)) * 100;
                input.style.setProperty('--fill', `${Math.max(0, Math.min(100, p))}%`);
            }
        };
        let frame = 0;
        const push = () => {
            if (frame) return;
            frame = requestAnimationFrame(() => { frame = 0; apply(current()); });
        };
        inputs.forEach((input) => {
            refresh(input);
            input.addEventListener('input', () => { refresh(input); bar.classList.add('is-touched'); push(); });
        });
        const reset = bar.querySelector('[data-reset]');
        if (reset) reset.addEventListener('click', () => {
            inputs.forEach((i) => { i.value = i.dataset.default; refresh(i); });
            bar.classList.remove('is-touched');
            push();
        });
        return current;
    }

    /** Before / After の境界。stage の --split (0〜100) を動かす */
    function bindCompare(stage, { hint = true } = {}) {
        const handle = stage.querySelector('.bk-cmp-handle');
        let split = 50;
        const set = (v) => {
            split = Math.max(0, Math.min(100, v));
            stage.style.setProperty('--split', `${split}%`);
            handle.setAttribute('aria-valuenow', String(Math.round(split)));
        };
        const fromPointer = (e) => {
            const r = stage.getBoundingClientRect();
            set(((e.clientX - r.left) / r.width) * 100);
        };
        handle.addEventListener('pointerdown', (e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            stage.classList.remove('is-hinting');
            handle.setPointerCapture(e.pointerId);
            stage.classList.add('is-dragging');
            const move = (ev) => fromPointer(ev);
            const up = () => {
                stage.classList.remove('is-dragging');
                handle.removeEventListener('pointermove', move);
                handle.removeEventListener('pointerup', up);
                handle.removeEventListener('pointercancel', up);
            };
            handle.addEventListener('pointermove', move);
            handle.addEventListener('pointerup', up);
            handle.addEventListener('pointercancel', up);
        });
        handle.addEventListener('keydown', (e) => {
            const step = e.shiftKey ? 10 : 2;
            const keys = { ArrowLeft: -step, ArrowRight: step, Home: -100, End: 100 };
            if (!(e.key in keys)) return;
            e.preventDefault();
            stage.classList.remove('is-hinting');
            set(split + keys[e.key]);
        });
        set(50);
        // 初めて画面に入ったとき、境界を少し揺らして「動かせる」ことを伝える
        if (hint && !REDUCED.matches && 'IntersectionObserver' in window) {
            const io = new IntersectionObserver((entries) => {
                if (!entries.some((en) => en.isIntersecting)) return;
                io.disconnect();
                stage.classList.add('is-hinting');
                stage.addEventListener('animationend', () => stage.classList.remove('is-hinting'), { once: true });
            }, { threshold: 0.6 });
            io.observe(stage);
        }
        return set;
    }

    return { srcdoc, varsCss, detectVars, controlFromVar, guessRange, bindControls, bindCompare, MAX_CONTROLS };
})();
