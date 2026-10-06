/**
 * Blogs — ブロックエディタ: ドラッグでブロックのサイズを自由に変える
 * - ブロックの左右の端: 本文の幅 (中央寄せなので両側が同時に動く)。本文幅・ワイド・全幅に吸い付く
 * - 列の境目: 列の比率 (1/4・1/3・1/2・2/3・3/4 に吸い付く)
 * - 余白ブロック・HTML / CSS デモのプレビューの下端: 高さ
 * どれもダブルクリックで元 (決まった値) に戻し、← → / ↑ ↓ キーでも動かせる。Alt / Option を押している間は吸い付かない。
 * ドラッグ中は CSS 変数だけを書き換え (requestAnimationFrame で 1 フレーム 1 回)、離したときに状態へ確定する。
 * 保存形式: style.maxw / widths / px / stage_height (blog/blocks.py)
 */
(() => {
    const { BlockEditor } = window.BlogBlocks;
    const MIN_WIDTH = 240;
    const MIN_COL = 0.1;
    const WIDTH_SNAP_PX = 12;
    const COL_SNAPS = [0.25, 1 / 3, 0.5, 2 / 3, 0.75];
    const COL_SNAP = 0.016;
    const SPACER = { min: 8, max: 800, presets: { s: 24, m: 56, l: 112 } };
    const STAGE = { min: 160, max: 1200, presets: { s: 240, m: 380, l: 560 } };
    const WIDTH_TYPES = new Set(['text', 'callout', 'quote', 'divider', 'button']);
    const RICH = new Set(['text', 'callout', 'quote']);

    const px = (v) => parseFloat(v) || 0;
    const round4 = (n) => Math.round(n * 10000) / 10000;

    /**
     * 汎用のドラッグ: requestAnimationFrame でまとめ、pointer capture で要素の外に出ても追従する
     * @returns 開始時に呼ぶ関数 (pointerdown の中で)
     */
    function drag(grip, { start, move, end }) {
        grip.addEventListener('pointerdown', (e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            e.stopPropagation();
            const state = start(e);
            if (state === false) return;
            grip.setPointerCapture(e.pointerId);
            let last = e;
            let frame = 0;
            const tick = () => { frame = 0; move(last); };
            const onMove = (ev) => { last = ev; if (!frame) frame = requestAnimationFrame(tick); };
            const onUp = (ev) => {
                if (frame) { cancelAnimationFrame(frame); move(last); }
                grip.removeEventListener('pointermove', onMove);
                grip.removeEventListener('pointerup', onUp);
                grip.removeEventListener('pointercancel', onUp);
                end(ev.type === 'pointercancel');
            };
            grip.addEventListener('pointermove', onMove);
            grip.addEventListener('pointerup', onUp);
            grip.addEventListener('pointercancel', onUp);
        });
    }

    const make = (cls, attrs = {}) => {
        const el = document.createElement('span');
        el.className = `bk-rs ${cls}`;
        Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
        return el;
    };

    Object.assign(BlockEditor.prototype, {
        /** renderBody のたびに呼ばれる: 前回のつまみを外して、今のブロックに合うものを付け直す */
        bindResize(block, bk) {
            bk.querySelectorAll(':scope > .bk-rs, :scope > .bk-grid > .bk-rs').forEach((el) => el.remove());
            if (block.resizeObserver) { block.resizeObserver.disconnect(); block.resizeObserver = null; }
            if (WIDTH_TYPES.has(block.type)) this.bindWidthResize(block, bk);
            if (RICH.has(block.type) && block.columns > 1) this.bindColumnResize(block, bk);
            if (block.type === 'spacer') this.bindHeightResize(block, bk, bk, SPACER, 'px');
            if (block.type === 'demo') {
                const stage = bk.querySelector('.bk-demo-stage');
                if (stage) this.bindHeightResize(block, bk, stage, STAGE, 'stageHeight');
            }
        },

        /** サイズの吹き出し (ドラッグ中だけ表示) */
        sizeBadge(host) {
            const badge = make('bk-rs-badge', { 'aria-hidden': 'true' });
            host.append(badge);
            return badge;
        },

        // ── 本文の幅 ───────────────────────────────────
        bindWidthResize(block, bk) {
            const t = this.t.resize || {};
            const badge = this.sizeBadge(bk);
            const pad = () => { const s = getComputedStyle(bk); return px(s.paddingLeft) + px(s.paddingRight); };
            const measures = () => {
                const s = getComputedStyle(this.root);
                return { text: px(s.getPropertyValue('--blog-measure')), wide: px(s.getPropertyValue('--blog-measure-wide')) };
            };
            // 置ける最大の幅 (エディタのキャンバスいっぱい = 全幅)
            const available = () => this.root.clientWidth - pad();
            const contentWidth = () => bk.getBoundingClientRect().width - pad();

            /** 幅 w を今の見た目に反映し、吸い付いた先 (text / wide / full / null) を返す */
            const preview = (w, free) => {
                const max = available();
                const m = measures();
                // 決まった幅 (狭い順)。キャンバスより広い幅はキャンバスいっぱいとして扱い、同じ幅なら狭い方を選ぶ
                const cands = [['text', Math.min(m.text, max)], ['wide', Math.min(m.wide, max)], ['full', max]];
                let snap = null;
                if (!free) {
                    const hit = cands.find(([, v]) => Math.abs(w - v) <= WIDTH_SNAP_PX);
                    if (hit) { snap = hit[0]; w = hit[1]; }
                }
                w = Math.round(Math.min(max, Math.max(MIN_WIDTH, w)));
                if (w >= max - 1) snap = cands.find(([, v]) => v >= max - 1)[0];
                bk.classList.remove('bk-w-wide', 'bk-w-full');
                bk.style.setProperty('--bk-max', `${w}px`);
                const name = snap ? (t[snap] || snap) : '';
                badge.textContent = name ? `${w} px · ${name}` : `${w} px`;
                bk.classList.toggle('is-snapped', !!snap);
                return { w, snap };
            };
            const commit = ({ w, snap }) => {
                if (snap === 'full' || snap === 'wide' || snap === 'text') {
                    block.style.width = snap;
                    block.style.maxw = null;
                } else {
                    block.style.width = 'text';
                    block.style.maxw = w;
                }
                this.renderBody(block);
                this.changed();
            };

            ['left', 'right'].forEach((edge) => {
                const dir = edge === 'right' ? 1 : -1;
                const grip = make(`bk-rs-width bk-rs-width--${edge}`, {
                    role: 'separator', 'aria-orientation': 'vertical', tabindex: '0',
                    'aria-label': t.widthLabel || '', title: t.width || '',
                });
                bk.append(grip);
                let startX = 0;
                let startW = 0;
                let result = null;
                drag(grip, {
                    start: (e) => {
                        startX = e.clientX;
                        startW = contentWidth();
                        result = null;
                        bk.classList.add('is-resizing');
                        document.body.classList.add('bk-resizing-x');
                        return true;
                    },
                    move: (ev) => { result = preview(startW + dir * 2 * (ev.clientX - startX), ev.altKey); },
                    end: (cancel) => {
                        bk.classList.remove('is-resizing', 'is-snapped');
                        document.body.classList.remove('bk-resizing-x');
                        if (cancel || !result) { this.renderBody(block); return; }
                        commit(result);
                    },
                });
                grip.addEventListener('dblclick', () => {
                    block.style.width = 'text';
                    block.style.maxw = null;
                    this.renderBody(block);
                    this.changed();
                });
                grip.addEventListener('keydown', (e) => {
                    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
                    e.preventDefault();
                    const step = (e.shiftKey ? 64 : 16) * (e.key === 'ArrowRight' ? dir : -dir) * 2;
                    commit(preview(contentWidth() + step, true));
                    bk.querySelector(`.bk-rs-width--${edge}`).focus();
                });
            });
        },

        // ── 列の比率 ───────────────────────────────────
        bindColumnResize(block, bk) {
            const t = this.t.resize || {};
            const grid = bk.querySelector(':scope > .bk-grid');
            if (!grid) return;
            const badge = this.sizeBadge(bk);
            const n = block.columns;
            const grips = [];
            const gap = () => px(getComputedStyle(grid).columnGap);
            const cells = () => block.cells.map((c) => c.el);
            /** 今の見た目の比率 (決まった比率のときも実際の幅から求める) */
            const fractions = () => {
                const ws = cells().map((el) => el.getBoundingClientRect().width);
                const sum = ws.reduce((a, b) => a + b, 0) || 1;
                return ws.map((w) => w / sum);
            };
            const place = () => {
                const g = grid.getBoundingClientRect();
                const cs = cells();
                grips.forEach((grip, i) => {
                    const a = cs[i].getBoundingClientRect();
                    const b = cs[i + 1].getBoundingClientRect();
                    grip.style.left = `${(a.right + b.left) / 2 - g.left}px`;
                });
            };
            const apply = (f) => {
                bk.classList.add('bk-custom-cols');
                bk.style.setProperty('--bk-cols', f.map((w) => `minmax(0, ${round4(w)}fr)`).join(' '));
                place();
            };
            const label = (f) => f.map((w) => `${Math.round(w * 100)}%`).join(' · ');
            const commit = (f) => {
                const equal = f.every((w) => Math.abs(w - 1 / n) < 0.006);
                if (equal) {
                    block.widths = null;
                    block.ratio = 'equal';
                } else if (n === 2 && Math.abs(f[0] - 2 / 3) < 0.006) {
                    block.widths = null;
                    block.ratio = 'wide-left';
                } else if (n === 2 && Math.abs(f[0] - 1 / 3) < 0.006) {
                    block.widths = null;
                    block.ratio = 'wide-right';
                } else {
                    block.widths = f.map(round4);
                }
                this.renderBody(block);
                this.changed();
            };

            for (let i = 0; i < n - 1; i++) {
                const grip = make('bk-rs-col', {
                    role: 'separator', 'aria-orientation': 'vertical', tabindex: '0',
                    'aria-label': t.columnsLabel || '', title: t.columns || '',
                });
                grip.innerHTML = '<i aria-hidden="true"></i>';
                grid.append(grip);
                grips.push(grip);
                let f0 = null;
                let cur = null;
                // 境目 i をポインタの位置へ。左右の 2 列だけでやり取りし、ほかの列はそのまま
                const setBoundary = (x, free) => {
                    const g = grid.getBoundingClientRect();
                    const gp = gap();
                    const track = g.width - gp * (n - 1);
                    const left = f0.slice(0, i).reduce((a, b) => a + b, 0);
                    const pair = f0[i] + f0[i + 1];
                    let boundary = (x - g.left - gp * (i + 0.5)) / track; // 境目までの割合 (0〜1)
                    let snapped = false;
                    if (!free) {
                        const s = COL_SNAPS.find((p) => Math.abs(boundary - p) < COL_SNAP);
                        if (s !== undefined) { boundary = s; snapped = true; }
                        // 3 列: 2 列の組を均等に分ける位置にも吸い付く
                        const mid = left + pair / 2;
                        if (!snapped && Math.abs(boundary - mid) < COL_SNAP) { boundary = mid; snapped = true; }
                    }
                    const a = Math.min(pair - MIN_COL, Math.max(MIN_COL, boundary - left));
                    cur = f0.slice();
                    cur[i] = a;
                    cur[i + 1] = pair - a;
                    apply(cur);
                    badge.textContent = label(cur);
                    bk.classList.toggle('is-snapped', snapped);
                };
                drag(grip, {
                    start: () => {
                        f0 = fractions();
                        cur = null;
                        bk.classList.add('is-resizing', 'is-col-resizing');
                        document.body.classList.add('bk-resizing-x');
                        badge.textContent = label(f0);
                        return true;
                    },
                    move: (ev) => setBoundary(ev.clientX, ev.altKey),
                    end: (cancel) => {
                        bk.classList.remove('is-resizing', 'is-col-resizing', 'is-snapped');
                        document.body.classList.remove('bk-resizing-x');
                        if (cancel || !cur) { this.renderBody(block); return; }
                        commit(cur);
                    },
                });
                grip.addEventListener('dblclick', () => {
                    block.widths = null;
                    block.ratio = 'equal';
                    this.renderBody(block);
                    this.changed();
                });
                grip.addEventListener('keydown', (e) => {
                    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
                    e.preventDefault();
                    const f = fractions();
                    const step = (e.shiftKey ? 0.1 : 0.02) * (e.key === 'ArrowRight' ? 1 : -1);
                    const pair = f[i] + f[i + 1];
                    f[i] = Math.min(pair - MIN_COL, Math.max(MIN_COL, f[i] + step));
                    f[i + 1] = pair - f[i];
                    commit(f);
                    const again = bk.querySelectorAll('.bk-rs-col')[i];
                    if (again) again.focus();
                });
            }
            // 文章の量や画面幅で列の位置が変わったら、つまみを付け直す
            requestAnimationFrame(place);
            if (window.ResizeObserver) {
                block.resizeObserver = new ResizeObserver(() => place());
                block.resizeObserver.observe(grid);
                cells().forEach((el) => block.resizeObserver.observe(el));
            }
        },

        // ── 高さ (余白・デモのプレビュー) ─────────────────────
        bindHeightResize(block, bk, target, limits, key) {
            const t = this.t.resize || {};
            const badge = this.sizeBadge(target === bk ? bk : target);
            const grip = make('bk-rs-height', {
                role: 'separator', 'aria-orientation': 'horizontal', tabindex: '0',
                'aria-label': t.heightLabel || '', title: t.height || '',
            });
            grip.innerHTML = '<i aria-hidden="true"></i>';
            target.append(grip);
            let startY = 0;
            let startH = 0;
            let result = null;
            const preview = (h, free) => {
                let snap = null;
                if (!free) {
                    snap = Object.keys(limits.presets).find((k) => Math.abs(h - limits.presets[k]) <= 8) || null;
                    if (snap) h = limits.presets[snap];
                }
                h = Math.round(Math.min(limits.max, Math.max(limits.min, h)));
                target.style.height = `${h}px`;
                badge.textContent = snap ? `${h} px · ${snap.toUpperCase()}` : `${h} px`;
                bk.classList.toggle('is-snapped', !!snap);
                return { h, snap };
            };
            const commit = ({ h, snap }) => {
                if (snap) { block.height = snap; block[key] = null; } else { block[key] = h; }
                // デモは描き直すとプレビューを読み込み直すので、見た目はそのままにして状態だけ確定する
                if (block.type !== 'demo') this.renderBody(block);
                this.changed();
            };
            drag(grip, {
                start: (e) => {
                    startY = e.clientY;
                    startH = target.getBoundingClientRect().height;
                    result = null;
                    bk.classList.add('is-resizing', 'is-height-resizing');
                    document.body.classList.add('bk-resizing-y');
                    return true;
                },
                move: (ev) => { result = preview(startH + ev.clientY - startY, ev.altKey); },
                end: (cancel) => {
                    bk.classList.remove('is-resizing', 'is-height-resizing', 'is-snapped');
                    document.body.classList.remove('bk-resizing-y');
                    if (cancel || !result) { target.style.height = `${startH}px`; return; }
                    commit(result);
                },
            });
            grip.addEventListener('dblclick', () => {
                block.height = 'm';
                block[key] = null;
                if (block.type === 'demo') target.style.height = `${limits.presets.m}px`;
                else this.renderBody(block);
                this.changed();
            });
            grip.addEventListener('keydown', (e) => {
                if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
                e.preventDefault();
                const step = (e.shiftKey ? 64 : 8) * (e.key === 'ArrowDown' ? 1 : -1);
                commit(preview(target.getBoundingClientRect().height + step, true));
                const again = target.querySelector(':scope > .bk-rs-height');
                if (again) again.focus();
            });
        },
    });
})();
