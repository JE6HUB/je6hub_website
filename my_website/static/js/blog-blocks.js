/**
 * Blogs — ブロックエディタ (Notion 風)
 * 本文をブロックの並びとして編集する。ブロックごとに 1〜3 列を選べ、各列は独立した
 * Quill (リッチテキスト) になる。保存形式は blog/blocks.py と対応している。
 *
 * - ブロックにカーソルを合わせると左に「＋」(追加) と「⋮⋮」(設定・ドラッグで並べ替え)
 * - 空の行で「/」→ ブロックの追加メニュー (検索可)
 * - ⋮⋮ をクリック → 列数・比率・背景・幅・余白などの見た目、複製・削除
 */
window.BlogBlocks = (() => {
    const STYLE_DEFAULTS = { bg: 'none', width: 'text', space: 'm', valign: 'top', size: 'm', rule: false, animate: false };
    const RICH = new Set(['text', 'callout', 'quote']);
    const uid = () => Math.random().toString(36).slice(2, 10);
    // スマホなど狭い画面では、メニューをアンカーの近くではなく画面下からのシートとして出す
    const SHEET_MQ = window.matchMedia('(max-width: 640px)');
    // 指で操作する端末 (タッチ) か。検索欄への自動フォーカスでキーボードが出るのを避ける
    const COARSE_MQ = window.matchMedia('(pointer: coarse)');
    const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

    // ── HTML / CSS デモ ─────────────────────────────────
    // 記事ページと同じ srcdoc (blog-demo-kit.js / blog/blocks.py の demo_srcdoc と対応) を組み立てて、
    // sandbox 付き iframe でプレビューする。スクリプトは動かず、ページ本体からも分離される。
    const Kit = window.BlogDemoKit;
    const DEMO_HEIGHTS = { s: 240, m: 380, l: 560 };
    // カード幅の下限: プレビューの中身が収まる幅と、この値の大きい方 (エディタが使える幅)
    const DEMO_MIN_WIDTH = 320;
    // 最初の見本。CSS 変数 (--radius など) を使うと、読者が触れるコントロールにできる
    const DEMO_STARTER = {
        html: '<button class="btn">Get started</button>',
        css: [
            ':root {',
            '  --brand: #0071e3;',
            '  --radius: 980px;',
            '  --size: 17px;',
            '}',
            '',
            '.btn {',
            '  padding: calc(var(--size) * 0.7) calc(var(--size) * 1.4);',
            '  border: none;',
            '  border-radius: var(--radius);',
            '  background: var(--brand);',
            '  color: #fff;',
            '  font: 600 var(--size)/1 -apple-system, BlinkMacSystemFont, sans-serif;',
            '  cursor: pointer;',
            '  transition: transform 0.2s ease, filter 0.2s ease;',
            '}',
            '.btn:hover { filter: brightness(1.1); transform: scale(1.04); }',
            '.btn:active { transform: scale(0.97); }',
        ].join('\n'),
    };

    /** 追加メニューの項目。apply(editor, block) で作成直後の中身を整える */
    const INSERT_ITEMS = [
        { key: 'text', icon: 'notes', type: 'text' },
        { key: 'heading', icon: 'title', type: 'text', apply: (ed, b) => b.cells[0].quill.formatLine(0, 1, 'header', 2) },
        { key: 'cols2', icon: 'view_column_2', type: 'text', columns: 2 },
        { key: 'cols3', icon: 'view_week', type: 'text', columns: 3 },
        { key: 'image', icon: 'image', type: 'text', apply: (ed, b) => ed.options.pickImage(b.cells[0].quill) },
        { key: 'mediaText', icon: 'vertical_split', type: 'text', columns: 2, style: { valign: 'center' },
          apply: (ed, b) => ed.options.pickImage(b.cells[0].quill) },
        { key: 'callout', icon: 'lightbulb', type: 'callout' },
        { key: 'quote', icon: 'format_quote', type: 'quote' },
        { key: 'math', icon: 'function', type: 'text', apply: (ed, b) => ed.options.openMath(b.cells[0].quill) },
        { key: 'code', icon: 'code_blocks', type: 'text', apply: (ed, b) => b.cells[0].quill.formatLine(0, 1, 'code-block', true) },
        { key: 'demo', icon: 'web', type: 'demo' },
        { key: 'divider', icon: 'horizontal_rule', type: 'divider' },
        { key: 'spacer', icon: 'height', type: 'spacer' },
        { key: 'button', icon: 'smart_button', type: 'button' },
    ];

    class BlockEditor {
        /**
         * @param {HTMLElement} root  ブロックを並べる要素
         * @param {object} options    { Quill, t, quillOptions(block), onQuill(quill), onChange(), pickImage(quill), openMath(quill) }
         */
        constructor(root, options) {
            this.root = root;
            this.options = options;
            this.t = options.t;
            this.Quill = options.Quill;
            this.blocks = [];
            this.active = null; // 最後にフォーカスした Quill
            this.menu = this.buildPopover('bk-menu');
            this.inserter = this.buildPopover('bk-inserter');
            this.dropLine = document.createElement('div');
            this.dropLine.className = 'bk-drop-line';
            this.dropLine.hidden = true;
            document.body.append(this.dropLine);
            // シート表示のときの背景。タップで閉じる (pointerdown ではなく click で閉じ、下の要素が押されないようにする)
            this.backdrop = document.createElement('div');
            this.backdrop.className = 'bk-sheet-backdrop';
            this.backdrop.hidden = true;
            this.backdrop.addEventListener('click', () => { this.closePopover(this.menu); this.closePopover(this.inserter); });
            document.body.append(this.backdrop);
            // ソフトウェアキーボードが出たら、シートをキーボードの上に載せる
            if (window.visualViewport) {
                const fit = () => this.fitSheets();
                window.visualViewport.addEventListener('resize', fit);
                window.visualViewport.addEventListener('scroll', fit);
            }
            // 外側を押したら閉じる。ただしメニュー内の操作 (項目の選択で別のメニューを開く場合を含む) は除く
            document.addEventListener('pointerdown', (e) => {
                if (e.target.closest('.bk-sheet-backdrop')) return;
                if (!e.target.closest('.bk-popover, .bk-handle, .bk-callout-icon, .bk-button button')) this.closePopover(this.menu);
                if (!e.target.closest('.bk-popover, .bk-add, .blog-add-block')) this.closePopover(this.inserter);
            });
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') { this.closePopover(this.menu); this.closePopover(this.inserter); }
            });
            // シートは画面に固定なので、スクロール (キーボード表示に伴うものを含む) では閉じない
            window.addEventListener('scroll', () => { if (!this.menu.classList.contains('is-sheet')) this.closePopover(this.menu); }, { passive: true });
        }

        // ── 読み込み / 保存 ───────────────────────────────
        load(data, legacy) {
            const blocks = data && Array.isArray(data.blocks) ? data.blocks : [];
            if (blocks.length) {
                blocks.forEach((b) => this.insertBlock(b, this.blocks.length, { silent: true }));
            } else {
                // ブロック導入前の記事: 本文全体を 1 つのテキストブロックとして読み込む
                const block = this.insertBlock({ type: 'text' }, 0, { silent: true });
                const q = block.cells[0].quill;
                if (legacy.delta && Array.isArray(legacy.delta.ops) && legacy.delta.ops.length) {
                    q.setContents(legacy.delta, this.Quill.sources.SILENT);
                } else if (legacy.html) {
                    q.clipboard.dangerouslyPasteHTML(legacy.html, this.Quill.sources.SILENT);
                }
                q.history.clear();
            }
        }

        serialize() {
            const cellHtml = (q) => (q.getLength() <= 1 ? '' : q.getSemanticHTML().replace(/&nbsp;/g, ' '));
            return {
                version: 1,
                blocks: this.blocks.map((b) => {
                    const out = { id: b.id, type: b.type, style: { ...b.style } };
                    if (RICH.has(b.type)) {
                        out.columns = b.columns;
                        out.ratio = b.ratio;
                        out.cells = b.cells.map((c) => ({ delta: c.quill.getContents(), html: cellHtml(c.quill) }));
                        if (b.type === 'callout') out.icon = b.icon;
                    } else if (b.type === 'divider') out.variant = b.variant;
                    else if (b.type === 'spacer') out.height = b.height;
                    else if (b.type === 'button') Object.assign(out, { label: b.label, url: b.url, variant: b.variant, align: b.align });
                    else if (b.type === 'demo') Object.assign(out, {
                        html: b.html, css: b.css, bg: b.bg, height: b.height, layout: b.layout, card_width: b.cardWidth,
                        controls: b.controls, compare: b.compare, before_html: b.beforeHtml, before_css: b.beforeCss,
                        before_label: b.beforeLabel, after_label: b.afterLabel,
                    });
                    return out;
                }),
            };
        }

        /** 検索・抜粋用に全ブロックを 1 本にした HTML (サーバーでも作り直す) */
        combinedHtml(data) {
            return data.blocks.flatMap((b) => (b.cells || []).map((c) => c.html)).join('');
        }

        changed() { this.options.onChange(); }

        // ── ブロックの生成 ─────────────────────────────────
        insertBlock(data, index, { silent = false, focus = false } = {}) {
            const type = data.type || 'text';
            const block = {
                id: data.id || uid(),
                type,
                style: { ...STYLE_DEFAULTS, ...(data.style || {}) },
                columns: RICH.has(type) && type !== 'quote' ? Math.min(3, Math.max(1, data.columns || 1)) : 1,
                ratio: data.ratio || 'equal',
                icon: data.icon || '💡',
                variant: data.variant || (type === 'divider' ? 'line' : 'primary'),
                height: data.height || 'm',
                label: data.label || '',
                url: data.url || '',
                align: data.align || 'center',
                html: data.html !== undefined ? data.html : (type === 'demo' ? DEMO_STARTER.html : ''),
                css: data.css !== undefined ? data.css : (type === 'demo' ? DEMO_STARTER.css : ''),
                bg: data.bg || 'dark',
                layout: data.layout || 'center',
                cardWidth: Number.isFinite(data.card_width) ? data.card_width : null,
                controls: Array.isArray(data.controls) ? data.controls.map((c) => ({ ...c })) : [],
                compare: data.compare === true,
                beforeHtml: data.before_html || '',
                beforeCss: data.before_css || '',
                beforeLabel: data.before_label || '',
                afterLabel: data.after_label || '',
                cells: [],
            };
            block.el = this.renderShell(block);
            if (RICH.has(type)) {
                const cellsData = data.cells || [];
                for (let i = 0; i < block.columns; i++) this.addCell(block, cellsData[i]);
            }
            this.renderBody(block);
            const ref = this.blocks[index];
            this.root.insertBefore(block.el, ref ? ref.el : null);
            this.blocks.splice(index, 0, block);
            if (focus) this.focusBlock(block);
            if (!silent) this.changed();
            return block;
        }

        renderShell(block) {
            const el = document.createElement('div');
            el.className = 'bk-edit';
            el.dataset.id = block.id;
            el.innerHTML = `
                <div class="bk-gutter">
                    <button type="button" class="bk-add" aria-label="${esc(this.t.addBlock)}" title="${esc(this.t.addBlock)}">
                        <span class="material-symbols-outlined" aria-hidden="true">add</span></button>
                    <button type="button" class="bk-handle" aria-label="${esc(this.t.blockMenu)}" title="${esc(this.t.blockMenu)}">
                        <span class="material-symbols-outlined" aria-hidden="true">drag_indicator</span></button>
                </div>
                <div class="bk"></div>`;
            el.querySelector('.bk-add').addEventListener('click', (e) => {
                this.openInserter(e.currentTarget, this.blocks.indexOf(block) + 1);
            });
            this.enableDrag(block, el.querySelector('.bk-handle'));
            return el;
        }

        /** ブロックの中身と見た目 (クラス) を状態から描き直す */
        renderBody(block) {
            const bk = block.el.querySelector('.bk');
            const s = block.style;
            const classes = ['bk', `bk-${block.type}`, `bk-w-${s.width}`, `bk-space-${s.space}`];
            if (RICH.has(block.type)) {
                classes.push(`bk-cols-${block.columns}`, `bk-ratio-${block.ratio}`, `bk-bg-${s.bg}`, `bk-valign-${s.valign}`, `bk-size-${s.size}`);
                if (s.rule) classes.push('bk-rule');
            }
            bk.className = classes.join(' ');

            if (RICH.has(block.type)) {
                let grid = bk.querySelector(':scope > .bk-grid');
                if (!grid) {
                    grid = document.createElement('div');
                    grid.className = 'bk-grid';
                    bk.append(grid);
                }
                block.cells.forEach((c) => { if (c.el.parentElement !== grid) grid.append(c.el); });
                let icon = bk.querySelector(':scope > .bk-callout-icon');
                if (block.type === 'callout') {
                    if (!icon) {
                        icon = document.createElement('button');
                        icon.type = 'button';
                        icon.className = 'bk-callout-icon';
                        icon.title = this.t.changeIcon;
                        icon.addEventListener('click', () => this.openMenu(block, icon));
                        bk.prepend(icon);
                    }
                    icon.textContent = block.icon;
                } else if (icon) {
                    icon.remove();
                }
            } else if (block.type === 'divider') {
                bk.classList.add(`bk-divider--${block.variant}`);
                bk.innerHTML = '<hr>';
            } else if (block.type === 'spacer') {
                bk.classList.add(`bk-spacer--${block.height}`);
                bk.innerHTML = `<span class="bk-spacer-label">${esc(this.t.types.spacer)}</span>`;
            } else if (block.type === 'demo') {
                this.renderDemo(block, bk);
            } else if (block.type === 'button') {
                bk.classList.add(`bk-align-${block.align}`);
                const cls = block.variant === 'secondary' ? 'ap-btn ap-btn-outline' : 'ap-btn ap-btn-primary';
                bk.innerHTML = `<button type="button" class="${cls}">${esc(block.label || this.t.buttonPlaceholder)}</button>`;
                bk.querySelector('button').addEventListener('click', () => this.openMenu(block, bk.querySelector('button')));
            }
        }

        /** HTML / CSS デモ: 左右 (狭い画面では上下) に HTML と CSS、下にライブプレビュー。
         *  カードの左右の端をドラッグして幅を変えられる (下限はプレビューの中身が収まる幅)。
         *  比較をオンにすると「変更前」のコード欄と、境界をドラッグできる 2 枚重ねのプレビューになる。
         *  CSS 変数 (--name) は「読者が触れるコントロール」として公開できる */
        renderDemo(block, bk) {
            const t = this.t;
            bk.classList.add('bk-demo-block');
            const grip = (edge) => `<span class="bk-demo-resize bk-demo-resize--${edge}" data-edge="${edge}" role="separator"
                aria-orientation="vertical" tabindex="0" aria-label="${esc(t.demoResizeLabel)}" title="${esc(t.demoResize)}"></span>`;
            const field = (lang, label, placeholder = '') => `<label class="bk-demo-field"><span>${esc(label)}</span>`
                + `<textarea spellcheck="false" autocapitalize="off" data-lang="${lang}" rows="9" placeholder="${esc(placeholder)}"></textarea></label>`;
            // iframe は allow-same-origin (スクリプトは不可のまま) にして、中身の幅を測ったり変数を書き込んだりできるようにする
            const iframe = (title) => `<iframe class="bk-demo-frame" sandbox="allow-same-origin" referrerpolicy="no-referrer" title="${esc(title)}"></iframe>`;
            const stage = block.compare
                ? `<div class="bk-demo-stage bk-demo-stage--compare" data-compare style="height: ${DEMO_HEIGHTS[block.height] || DEMO_HEIGHTS.m}px">
                        ${iframe(t.demoBefore)}
                        <div class="bk-cmp-after">${iframe(t.demoPreview)}</div>
                        <span class="bk-cmp-label bk-cmp-label--before" aria-hidden="true">${esc(block.beforeLabel || 'Before')}</span>
                        <span class="bk-cmp-label bk-cmp-label--after" aria-hidden="true">${esc(block.afterLabel || 'After')}</span>
                        <div class="bk-cmp-handle" role="slider" tabindex="0" aria-valuemin="0" aria-valuemax="100" aria-label="${esc(t.demoSplit)}">
                            <span class="bk-cmp-knob" aria-hidden="true"><span class="material-symbols-outlined">code</span></span>
                        </div>
                   </div>`
                : `<div class="bk-demo-stage" style="height: ${DEMO_HEIGHTS[block.height] || DEMO_HEIGHTS.m}px">${iframe(t.demoPreview)}</div>`;
            bk.innerHTML = `
                <div class="bk-demo-sizer">
                    <div class="bk-demo bk-demo--edit">
                        <div class="bk-demo-editors">
                            ${field('html', block.compare ? `HTML · ${t.demoAfterShort}` : 'HTML')}
                            ${field('css', block.compare ? `CSS · ${t.demoAfterShort}` : 'CSS')}
                            ${block.compare ? field('beforeHtml', `HTML · ${t.demoBeforeShort}`, t.demoBeforeHtmlHint) + field('beforeCss', `CSS · ${t.demoBeforeShort}`) : ''}
                        </div>
                        ${stage}
                        <div class="bk-ctl-bar" data-controls hidden></div>
                        <details class="bk-ctl-setup">
                            <summary><span class="material-symbols-outlined" aria-hidden="true">tune</span>${esc(t.demoControls)}<span class="bk-ctl-count"></span></summary>
                            <div class="bk-ctl-setup-body"></div>
                        </details>
                    </div>
                    ${grip('left')}${grip('right')}
                    <span class="bk-demo-size" aria-hidden="true"></span>
                </div>`;
            const frames = [...bk.querySelectorAll('iframe')];
            const [beforeFrame, afterFrame] = block.compare ? frames : [null, frames[0]];
            const bar = bk.querySelector('[data-controls]');
            const setup = bk.querySelector('.bk-ctl-setup');
            let vars = null; // 試しに動かした値 (保存はしない)

            // 変数を iframe に直接書き込む (記事ページでは iframe 内のスクリプトが同じことをする)
            const applyVars = () => frames.forEach((f) => {
                try {
                    const doc = f.contentDocument;
                    if (!doc || !doc.head) return;
                    let st = doc.getElementById('bk-vars');
                    if (!st) { st = doc.createElement('style'); st.id = 'bk-vars'; doc.head.append(st); }
                    st.textContent = vars ? Kit.varsCss(vars) : '';
                } catch (e) { /* 読み込み途中 */ }
            });
            frames.forEach((f) => f.addEventListener('load', applyVars));
            const reload = () => {
                afterFrame.srcdoc = Kit.srcdoc(block);
                if (beforeFrame) beforeFrame.srcdoc = Kit.srcdoc(block, true);
            };
            reload();
            this.bindDemoResize(block, bk, afterFrame);
            if (block.compare) Kit.bindCompare(bk.querySelector('[data-compare]'), { hint: false });

            // 読者に見えるコントロールの見た目 (記事ページと同じ) を描き、試しに動かせるようにする
            const renderBar = () => {
                bar.hidden = !block.controls.length;
                vars = null;
                bar.innerHTML = block.controls.length ? `
                    <span class="bk-ctl-badge"><span class="material-symbols-outlined" aria-hidden="true">tune</span>${esc(t.demoTry)}</span>
                    ${block.controls.map((c) => `<label class="bk-ctl bk-ctl--${c.kind}"><span class="bk-ctl-name">${esc(c.label)}</span>${c.kind === 'color'
                        ? `<input type="color" value="${esc(c.value)}" data-var="${esc(c.name)}" data-default="${esc(c.value)}"><output></output>`
                        : `<input type="range" min="${c.min}" max="${c.max}" step="${c.step}" value="${c.value}" data-var="${esc(c.name)}" data-unit="${esc(c.unit)}" data-default="${c.value}"><output></output>`}</label>`).join('')}
                    <button type="button" class="bk-ctl-reset" data-reset title="${esc(t.demoReset)}" aria-label="${esc(t.demoReset)}">
                        <span class="material-symbols-outlined" aria-hidden="true">restart_alt</span></button>` : '';
                if (block.controls.length) Kit.bindControls(bar, (v) => { vars = v; applyVars(); });
                applyVars();
            };

            // コントロールの設定: CSS の変数を一覧にして、公開するものを選ぶ
            const renderSetup = () => {
                const found = Kit.detectVars(`${block.css}\n${block.compare ? block.beforeCss : ''}`);
                // CSS 側の値が変わったら、公開中のコントロールの初期値も追従させる (範囲は必要なら広げる)
                let touched = false;
                block.controls = block.controls.filter((c) => {
                    const v = found.find((x) => x.name === c.name);
                    if (!v || v.kind !== c.kind) { touched = true; return false; }
                    if (c.value !== v.value) {
                        touched = true;
                        c.value = v.value;
                        if (c.kind === 'range') { c.unit = v.unit; c.min = Math.min(c.min, v.value); c.max = Math.max(c.max, v.value); }
                    }
                    return true;
                });
                bk.querySelector('.bk-ctl-count').textContent = block.controls.length ? ` · ${block.controls.length}` : '';
                const body = setup.querySelector('.bk-ctl-setup-body');
                if (!found.length) {
                    body.innerHTML = `<p class="bk-ctl-empty">${t.demoControlsEmpty}</p>`;
                } else {
                    body.innerHTML = `<p class="bk-ctl-hint">${esc(t.demoControlsHint)}</p>` + found.map((v) => {
                        const c = block.controls.find((x) => x.name === v.name);
                        const full = !c && block.controls.length >= Kit.MAX_CONTROLS;
                        const range = c && c.kind === 'range' ? `
                            <input type="number" class="bk-menu-input bk-ctl-num" data-f="min" value="${c.min}" step="any" aria-label="${esc(t.demoMin)}" title="${esc(t.demoMin)}">
                            <span aria-hidden="true">–</span>
                            <input type="number" class="bk-menu-input bk-ctl-num" data-f="max" value="${c.max}" step="any" aria-label="${esc(t.demoMax)}" title="${esc(t.demoMax)}">` : '';
                        return `<div class="bk-ctl-row${c ? ' is-on' : ''}" data-name="${esc(v.name)}">
                            <label class="bk-switch"><input type="checkbox" data-f="on"${c ? ' checked' : ''}${full ? ' disabled' : ''}><span class="bk-switch-track"></span>
                                <code>${esc(v.name)}</code></label>
                            ${c ? `<input type="text" class="bk-menu-input bk-ctl-label" data-f="label" value="${esc(c.label)}" maxlength="40" aria-label="${esc(t.demoLabel)}" placeholder="${esc(t.demoLabel)}">${range}`
                                : `<span class="bk-ctl-sample">${v.kind === 'color' ? `<i style="background:${esc(v.value)}"></i>` : ''}${esc(String(v.value))}${esc(v.unit || '')}</span>`}
                        </div>`;
                    }).join('');
                }
                return touched;
            };
            setup.addEventListener('change', (e) => {
                const row = e.target.closest('[data-name]');
                if (!row) return;
                const name = row.dataset.name;
                const f = e.target.dataset.f;
                const c = block.controls.find((x) => x.name === name);
                if (f === 'on') {
                    if (e.target.checked && !c) {
                        const v = Kit.detectVars(`${block.css}\n${block.compare ? block.beforeCss : ''}`).find((x) => x.name === name);
                        if (v && block.controls.length < Kit.MAX_CONTROLS) block.controls.push(Kit.controlFromVar(v));
                    } else if (!e.target.checked) {
                        block.controls = block.controls.filter((x) => x.name !== name);
                    }
                    renderSetup();
                } else if (c && (f === 'min' || f === 'max')) {
                    const n = Number(e.target.value);
                    if (Number.isFinite(n)) c[f] = n;
                    if (c.min >= c.max) { c.min = Math.min(c.min, c.value); c.max = Math.max(c.min + c.step, c.max, c.value); }
                    c.value = Math.min(c.max, Math.max(c.min, c.value));
                    renderSetup();
                } else if (c && f === 'label') {
                    c.label = e.target.value.trim() || name.slice(2);
                }
                renderBar();
                this.changed();
            });
            setup.addEventListener('input', (e) => {
                if (e.target.dataset.f !== 'label') return;
                const c = block.controls.find((x) => x.name === e.target.closest('[data-name]').dataset.name);
                if (!c) return;
                c.label = e.target.value.trim() || c.name.slice(2);
                const name = [...bar.querySelectorAll('[data-var]')].find((i) => i.dataset.var === c.name);
                if (name) name.parentElement.querySelector('.bk-ctl-name').textContent = c.label;
                this.changed();
            });
            renderSetup();
            renderBar();

            let timer = null;
            bk.querySelectorAll('textarea').forEach((area) => {
                const lang = area.dataset.lang;
                area.value = block[lang];
                area.addEventListener('input', () => {
                    block[lang] = area.value;
                    clearTimeout(timer);
                    timer = setTimeout(() => {
                        reload();
                        if (/css/i.test(lang) && renderSetup()) renderBar();
                    }, 250);
                    this.changed();
                });
                // Tab キーでインデント (フォーカス移動ではなく 2 スペースを入れる)
                area.addEventListener('keydown', (e) => {
                    if (e.key !== 'Tab' || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey) return;
                    e.preventDefault();
                    const { selectionStart: a, selectionEnd: z } = area;
                    area.setRangeText('  ', a, z, 'end');
                    area.dispatchEvent(new Event('input'));
                });
            });
        }

        /** デモカードの幅のドラッグ変更。カードは中央寄せなので、端を動かした量の 2 倍だけ幅が変わる */
        bindDemoResize(block, bk, frame) {
            const sizer = bk.querySelector('.bk-demo-sizer');
            const label = bk.querySelector('.bk-demo-size');
            let minWidth = DEMO_MIN_WIDTH;

            // 置ける最大の幅 (ブロックの内側)
            const available = () => {
                const s = getComputedStyle(bk);
                return bk.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
            };
            // プレビューの中身がはみ出さずに表示できる最小の幅 (min-content + 余白)
            const measure = () => {
                try {
                    const doc = frame.contentDocument;
                    if (!doc || !doc.body) return DEMO_MIN_WIDTH;
                    const probe = doc.createElement('style');
                    probe.textContent = 'html,body{width:min-content!important;min-width:0!important;max-width:none!important}';
                    doc.head.append(probe);
                    const need = Math.max(doc.body.getBoundingClientRect().width, doc.body.scrollWidth);
                    probe.remove();
                    return Math.max(DEMO_MIN_WIDTH, Math.ceil(need));
                } catch (e) {
                    return DEMO_MIN_WIDTH;
                }
            };
            const apply = () => {
                sizer.style.maxWidth = block.cardWidth ? `${block.cardWidth}px` : '';
                const now = Math.round(sizer.getBoundingClientRect().width);
                label.textContent = block.cardWidth ? `${now} px` : `${this.t.demoFullWidth} · ${now} px`;
                bk.querySelectorAll('.bk-demo-resize').forEach((g) => {
                    g.setAttribute('aria-valuenow', String(now));
                    g.setAttribute('aria-valuemin', String(minWidth));
                    g.setAttribute('aria-valuemax', String(Math.round(available())));
                });
            };
            const setWidth = (w) => {
                const max = available();
                const clamped = Math.round(Math.min(max, Math.max(minWidth, w)));
                // 置き場所いっぱいまで広げたら「指定なし」(= 全幅) に戻す
                block.cardWidth = clamped >= max - 1 ? null : clamped;
                apply();
            };

            // 中身が変わったら下限を測り直し、今の幅が足りなければ広げる
            frame.addEventListener('load', () => {
                minWidth = Math.min(measure(), available());
                if (block.cardWidth && block.cardWidth < minWidth) {
                    setWidth(minWidth);
                    this.changed();
                } else {
                    apply();
                }
            });
            apply();

            bk.querySelectorAll('.bk-demo-resize').forEach((grip) => {
                const dir = grip.dataset.edge === 'right' ? 1 : -1;
                grip.addEventListener('pointerdown', (e) => {
                    if (e.button !== 0) return;
                    e.preventDefault();
                    minWidth = Math.min(measure(), available());
                    const startX = e.clientX;
                    const startW = sizer.getBoundingClientRect().width;
                    grip.setPointerCapture(e.pointerId);
                    sizer.classList.add('is-resizing');
                    const move = (ev) => setWidth(startW + dir * 2 * (ev.clientX - startX));
                    const up = () => {
                        grip.removeEventListener('pointermove', move);
                        grip.removeEventListener('pointerup', up);
                        grip.removeEventListener('pointercancel', up);
                        sizer.classList.remove('is-resizing');
                        this.changed();
                    };
                    grip.addEventListener('pointermove', move);
                    grip.addEventListener('pointerup', up);
                    grip.addEventListener('pointercancel', up);
                });
                grip.addEventListener('dblclick', () => { block.cardWidth = null; apply(); this.changed(); });
                // キーボード: ← → で 16px ずつ (Shift で 64px)
                grip.addEventListener('keydown', (e) => {
                    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
                    e.preventDefault();
                    minWidth = Math.min(measure(), available());
                    const step = (e.shiftKey ? 64 : 16) * (e.key === 'ArrowRight' ? dir : -dir) * 2;
                    setWidth(sizer.getBoundingClientRect().width + step);
                    this.changed();
                });
            });
        }

        addCell(block, cellData) {
            const el = document.createElement('div');
            el.className = 'bk-cell';
            const holder = document.createElement('div');
            el.append(holder);
            // renderBody 前は grid が無いので一時的にブロック要素へ
            block.el.querySelector('.bk').append(el);
            const opts = this.options.quillOptions(block);
            // Quill 既定の Backspace/Enter より先に評価させるため、生成時の設定に入れる
            opts.modules.keyboard.bindings = {
                ...opts.modules.keyboard.bindings,
                ...this.blockBindings(block),
            };
            const quill = new this.Quill(holder, opts);
            if (cellData && cellData.delta && Array.isArray(cellData.delta.ops) && cellData.delta.ops.length) {
                quill.setContents(cellData.delta, this.Quill.sources.SILENT);
            } else if (cellData && cellData.html) {
                quill.clipboard.dangerouslyPasteHTML(cellData.html, this.Quill.sources.SILENT);
            }
            quill.history.clear();
            quill.on('selection-change', (range) => { if (range) this.active = quill; });
            quill.on('text-change', () => this.changed());
            quill.root.addEventListener('focus', () => { this.active = quill; });
            quill.__block = block;
            block.cells.push({ el, quill });
            this.options.onQuill(quill);
            return quill;
        }

        /** 列の Quill に渡すキーバインド: 「/」で追加メニュー、空ブロックで Backspace → 削除 */
        blockBindings(block) {
            const editor = this;
            return {
                'bk-slash': {
                    key: '/',
                    shiftKey: null,
                    collapsed: true,
                    prefix: /^$/,
                    suffix: /^$/,
                    handler(range) {
                        const quill = this.quill;
                        const isEmptyBlock = block.type === 'text' && block.cells.length === 1 && quill.getLength() <= 1;
                        const anchor = {
                            getBoundingClientRect() {
                                const b = quill.getBounds(range.index);
                                const c = quill.container.getBoundingClientRect();
                                return { left: c.left + b.left, top: c.top + b.top, bottom: c.top + b.top + b.height };
                            },
                        };
                        const i = editor.blocks.indexOf(block);
                        editor.openInserter(anchor, isEmptyBlock ? i : i + 1, isEmptyBlock ? block : null, quill);
                        return false;
                    },
                },
                'bk-backspace': {
                    key: 'Backspace',
                    collapsed: true,
                    offset: 0,
                    handler() {
                        // 空の単一テキストブロックで Backspace → ブロックごと削除し、前のブロックの末尾へ
                        const quill = this.quill;
                        if (quill.getLength() > 1 || block.cells.length > 1 || block.type !== 'text' || editor.blocks.length < 2) return true;
                        const i = editor.blocks.indexOf(block);
                        editor.removeBlock(block);
                        editor.focusBlock(editor.blocks[Math.max(0, i - 1)], true);
                        return false;
                    },
                },
            };
        }

        focusBlock(block, atEnd = false) {
            if (!block || !block.cells.length) return;
            const q = block.cells[0].quill;
            q.focus();
            q.setSelection(atEnd ? q.getLength() - 1 : 0, 0, this.Quill.sources.SILENT);
            this.active = q;
        }

        // ── ブロックの操作 ─────────────────────────────────
        setColumns(block, n) {
            if (n === block.columns) return;
            if (n > block.columns) {
                for (let i = block.columns; i < n; i++) this.addCell(block);
            } else {
                // 減らす列の中身は残す列の末尾へまとめる (内容を失わない)
                const Delta = this.Quill.import('delta');
                const keep = block.cells[n - 1].quill;
                block.cells.splice(n).forEach((c) => {
                    if (c.quill.getLength() > 1) {
                        keep.updateContents(new Delta().retain(keep.getLength()).concat(c.quill.getContents()), this.Quill.sources.USER);
                    }
                    c.el.remove();
                });
            }
            block.columns = n;
            if (!['equal', ...(n === 2 ? ['wide-left', 'wide-right'] : [])].includes(block.ratio)) block.ratio = 'equal';
            this.renderBody(block);
            this.changed();
        }

        convert(block, type) {
            if (block.type === type) return;
            block.type = type;
            if (type === 'quote' && block.columns > 1) this.setColumns(block, 1);
            this.renderBody(block);
            this.changed();
        }

        moveBlock(block, to) {
            const from = this.blocks.indexOf(block);
            if (from < 0 || to === from || to === from + 1) return;
            this.blocks.splice(from, 1);
            const index = to > from ? to - 1 : to;
            const ref = this.blocks[index];
            this.root.insertBefore(block.el, ref ? ref.el : null);
            this.blocks.splice(index, 0, block);
            this.changed();
        }

        duplicate(block) {
            const data = this.serialize().blocks[this.blocks.indexOf(block)];
            delete data.id;
            this.insertBlock(data, this.blocks.indexOf(block) + 1);
        }

        removeBlock(block) {
            const i = this.blocks.indexOf(block);
            if (i < 0) return;
            this.blocks.splice(i, 1);
            block.el.remove();
            if (this.active && this.active.__block === block) this.active = null;
            if (!this.blocks.length) this.insertBlock({ type: 'text' }, 0, { focus: true });
            this.changed();
        }

        /** 追加メニューから選んだ種類のブロックを index に作る */
        addFromItem(item, index, replace) {
            if (replace) this.removeBlock(replace);
            const at = replace ? Math.min(index, this.blocks.length) : index;
            const block = this.insertBlock(
                { type: item.type, columns: item.columns || 1, style: item.style || {} }, at, { focus: RICH.has(item.type) },
            );
            if (item.apply) item.apply(this, block);
            if (item.type === 'button') this.openMenu(block, block.el.querySelector('.bk button'));
            return block;
        }

        // ── ドラッグで並べ替え (⋮⋮) / クリックで設定 ────────────
        enableDrag(block, handle) {
            handle.addEventListener('pointerdown', (e) => {
                if (e.button !== 0) return;
                e.preventDefault();
                const startY = e.clientY;
                // 指は押しただけでも少し動くので、タッチではしきい値を大きめにする
                const threshold = e.pointerType === 'mouse' ? 4 : 10;
                let dragging = false;
                let target = -1;
                const onMove = (ev) => {
                    if (!dragging && Math.abs(ev.clientY - startY) < threshold) return;
                    if (!dragging) {
                        dragging = true;
                        block.el.classList.add('is-dragging');
                        this.closePopover(this.menu);
                    }
                    target = this.blocks.length;
                    for (let i = 0; i < this.blocks.length; i++) {
                        const r = this.blocks[i].el.getBoundingClientRect();
                        if (ev.clientY < r.top + r.height / 2) { target = i; break; }
                    }
                    const refEl = this.blocks[target] ? this.blocks[target].el : null;
                    const rootRect = this.root.getBoundingClientRect();
                    const y = refEl ? refEl.getBoundingClientRect().top - 4 : rootRect.bottom + 4;
                    Object.assign(this.dropLine.style, { top: `${y + window.scrollY}px`, left: `${rootRect.left + window.scrollX}px`, width: `${rootRect.width}px` });
                    this.dropLine.hidden = false;
                };
                const onUp = (ev) => {
                    document.removeEventListener('pointermove', onMove);
                    document.removeEventListener('pointerup', onUp);
                    document.removeEventListener('pointercancel', onUp);
                    this.dropLine.hidden = true;
                    block.el.classList.remove('is-dragging');
                    if (ev.type === 'pointercancel') return;
                    if (dragging) this.moveBlock(block, target);
                    else this.openMenu(block, handle);
                };
                document.addEventListener('pointermove', onMove);
                document.addEventListener('pointerup', onUp);
                document.addEventListener('pointercancel', onUp);
            });
        }

        // ── ポップオーバー ─────────────────────────────────
        buildPopover(className) {
            const el = document.createElement('div');
            el.className = `bk-popover ${className}`;
            el.hidden = true;
            el.setAttribute('role', 'dialog');
            document.body.append(el);
            return el;
        }

        placePopover(pop, anchor) {
            pop.hidden = false;
            const sheet = SHEET_MQ.matches;
            pop.classList.toggle('is-sheet', sheet);
            if (sheet) {
                Object.assign(pop.style, { left: '', top: '' });
                this.backdrop.hidden = false;
                this.fitSheets();
                return;
            }
            const r = anchor.getBoundingClientRect();
            const w = pop.offsetWidth;
            const h = pop.offsetHeight;
            let left = r.left;
            let top = r.bottom + 8;
            if (left + w > window.innerWidth - 12) left = window.innerWidth - w - 12;
            if (top + h > window.innerHeight - 12) top = Math.max(12, r.top - h - 8);
            Object.assign(pop.style, { left: `${Math.max(12, left)}px`, top: `${top}px` });
        }

        closePopover(pop) {
            pop.hidden = true;
            if (this.menu.hidden && this.inserter.hidden) this.backdrop.hidden = true;
        }

        /** シートの下端をキーボードの上に合わせる (iOS は fixed 要素がキーボードの裏に隠れるため) */
        fitSheets() {
            const vv = window.visualViewport;
            const covered = vv ? Math.max(0, window.innerHeight - vv.height - vv.offsetTop) : 0;
            [this.menu, this.inserter].forEach((pop) => {
                pop.style.bottom = pop.classList.contains('is-sheet') && covered ? `${covered}px` : '';
                pop.style.maxHeight = pop.classList.contains('is-sheet') && vv ? `${Math.round(Math.min(vv.height * 0.75, 560))}px` : '';
            });
        }

        /** 追加メニュー (＋ボタン / 「/」) */
        openInserter(anchor, index, replace = null, returnTo = null) {
            const t = this.t;
            const pop = this.inserter;
            pop.innerHTML = `
                <input type="search" class="bk-inserter-search" placeholder="${esc(t.searchBlocks)}" aria-label="${esc(t.searchBlocks)}">
                <ul class="bk-inserter-list" role="listbox"></ul>`;
            const list = pop.querySelector('ul');
            const search = pop.querySelector('input');
            let items = INSERT_ITEMS;
            let cursor = 0;
            const render = () => {
                const q = search.value.trim().toLowerCase();
                items = INSERT_ITEMS.filter((it) => !q || `${t.types[it.key]} ${t.typeDesc[it.key]} ${it.key}`.toLowerCase().includes(q));
                cursor = Math.min(cursor, Math.max(0, items.length - 1));
                list.innerHTML = items.length ? items.map((it, i) => `
                    <li role="option" class="bk-inserter-item${i === cursor ? ' is-active' : ''}" data-i="${i}">
                        <span class="material-symbols-outlined" aria-hidden="true">${it.icon}</span>
                        <span><strong>${esc(t.types[it.key])}</strong><small>${esc(t.typeDesc[it.key])}</small></span>
                    </li>`).join('') : `<li class="bk-inserter-empty">${esc(t.noMatch)}</li>`;
            };
            const choose = (i) => {
                const item = items[i];
                if (!item) return;
                this.closePopover(pop);
                this.addFromItem(item, index, replace);
            };
            search.addEventListener('input', () => { cursor = 0; render(); });
            search.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && returnTo) { this.closePopover(pop); returnTo.focus(); return; }
                if (e.key === 'ArrowDown') { e.preventDefault(); cursor = Math.min(items.length - 1, cursor + 1); render(); }
                if (e.key === 'ArrowUp') { e.preventDefault(); cursor = Math.max(0, cursor - 1); render(); }
                // 日本語入力の確定の Enter では選ばない (Safari は isComposing = false、keyCode 229 で届く)
                if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); choose(cursor); }
            });
            // 押した瞬間ではなく、指を離して「タップ」が確定したときに選ぶ。
            // (pointerdown で選ぶと、スマホでリストをスクロールしようと触れた項目が選ばれてしまう)
            list.addEventListener('pointerdown', (e) => {
                // マウスでは検索欄のフォーカスを保つ。タッチでは既定の動作 (スクロール) を妨げない
                if (e.pointerType === 'mouse' && e.target.closest('[data-i]')) e.preventDefault();
            });
            list.addEventListener('click', (e) => {
                const li = e.target.closest('[data-i]');
                if (li) choose(Number(li.dataset.i));
            });
            render();
            this.closePopover(this.menu);
            this.placePopover(pop, anchor);
            pop.scrollTop = 0;
            // タッチ端末ではキーボードがリストを隠してしまうので、検索欄には自動でフォーカスしない
            // (「/」で開いたときは文字入力の続きなのでフォーカスする)
            if (!COARSE_MQ.matches || returnTo) search.focus();
        }

        /** ブロックの設定メニュー (⋮⋮) */
        openMenu(block, anchor) {
            const t = this.t;
            const s = block.style;
            const pop = this.menu;
            const seg = (name, value, options) => `
                <div class="blog-segmented bk-seg" data-set="${name}">
                    ${options.map(([v, label]) => `<label><input type="radio" name="bk-${name}" value="${v}"${String(v) === String(value) ? ' checked' : ''}><span>${esc(label)}</span></label>`).join('')}
                </div>`;
            const row = (label, control) => `<div class="bk-menu-row"><span class="bk-menu-label">${esc(label)}</span>${control}</div>`;
            const toggle = (name, on, label) => `
                <label class="bk-switch"><input type="checkbox" data-set="${name}"${on ? ' checked' : ''}><span class="bk-switch-track"></span>${esc(label)}</label>`;
            const bgSwatches = `
                <div class="bk-swatches" data-set="bg">
                    ${['none', 'gray', 'tint', 'accent', 'light'].map((v) => `
                        <label title="${esc(t.bg[v])}"><input type="radio" name="bk-bg" value="${v}"${s.bg === v ? ' checked' : ''} aria-label="${esc(t.bg[v])}"><span class="bk-swatch bk-swatch--${v}"></span></label>`).join('')}
                </div>`;

            const parts = [`<p class="bk-menu-title">${esc(t.types[block.type === 'text' ? 'text' : block.type])}</p>`];
            if (RICH.has(block.type)) {
                parts.push(row(t.kind, seg('type', block.type, [['text', t.types.text], ['callout', t.types.callout], ['quote', t.types.quote]])));
                if (block.type !== 'quote') parts.push(row(t.columns, seg('columns', block.columns, [[1, '1'], [2, '2'], [3, '3']])));
                if (block.columns === 2) parts.push(row(t.ratio, seg('ratio', block.ratio, [['equal', '1 : 1'], ['wide-left', '2 : 1'], ['wide-right', '1 : 2']])));
                if (block.type === 'callout') parts.push(row(t.icon, `<input type="text" class="bk-menu-input bk-menu-input--icon" data-set="icon" value="${esc(block.icon)}" maxlength="8">`));
                parts.push(row(t.background, bgSwatches));
                parts.push(row(t.width, seg('width', s.width, [['text', t.widths.text], ['wide', t.widths.wide], ['full', t.widths.full]])));
                parts.push(row(t.spacing, seg('space', s.space, [['none', t.none], ['s', 'S'], ['m', 'M'], ['l', 'L']])));
                if (block.columns > 1) parts.push(row(t.valign, seg('valign', s.valign, [['top', t.valigns.top], ['center', t.valigns.center], ['bottom', t.valigns.bottom]])));
                parts.push(row(t.textSize, seg('size', s.size, [['s', t.sizes.s], ['m', t.sizes.m], ['l', t.sizes.l]])));
                const toggles = [];
                if (block.columns > 1) toggles.push(toggle('rule', s.rule, t.columnRule));
                toggles.push(toggle('animate', s.animate, t.animate));
                parts.push(`<div class="bk-menu-toggles">${toggles.join('')}</div>`);
            } else if (block.type === 'divider') {
                parts.push(row(t.kind, seg('variant', block.variant, [['line', t.dividers.line], ['dots', t.dividers.dots]])));
                parts.push(row(t.width, seg('width', s.width, [['text', t.widths.text], ['wide', t.widths.wide], ['full', t.widths.full]])));
                parts.push(row(t.spacing, seg('space', s.space, [['none', t.none], ['s', 'S'], ['m', 'M'], ['l', 'L']])));
            } else if (block.type === 'spacer') {
                parts.push(row(t.height, seg('height', block.height, [['s', 'S'], ['m', 'M'], ['l', 'L']])));
            } else if (block.type === 'demo') {
                parts.push(row(t.background, seg('bg', block.bg, [['dark', t.demoBg.dark], ['light', t.demoBg.light], ['checker', t.demoBg.checker]])));
                parts.push(row(t.height, seg('height', block.height, [['s', 'S'], ['m', 'M'], ['l', 'L']])));
                parts.push(row(t.align, seg('layout', block.layout, [['center', t.aligns.center], ['top', t.demoTop]])));
                parts.push(`<div class="bk-menu-toggles">${toggle('compare', block.compare, t.demoCompare)}</div>`);
                if (block.compare) {
                    parts.push(row(t.demoBeforeShort, `<input type="text" class="bk-menu-input" data-set="beforeLabel" value="${esc(block.beforeLabel)}" maxlength="24" placeholder="Before">`));
                    parts.push(row(t.demoAfterShort, `<input type="text" class="bk-menu-input" data-set="afterLabel" value="${esc(block.afterLabel)}" maxlength="24" placeholder="After">`));
                }
                parts.push(row(t.width, seg('width', s.width, [['text', t.widths.text], ['wide', t.widths.wide], ['full', t.widths.full]])));
                parts.push(row(t.spacing, seg('space', s.space, [['none', t.none], ['s', 'S'], ['m', 'M'], ['l', 'L']])));
            } else if (block.type === 'button') {
                parts.push(row(t.buttonLabel, `<input type="text" class="bk-menu-input" data-set="label" value="${esc(block.label)}" maxlength="80" placeholder="${esc(t.buttonPlaceholder)}">`));
                parts.push(row(t.buttonUrl, `<input type="url" class="bk-menu-input" data-set="url" value="${esc(block.url)}" placeholder="https://">`));
                parts.push(row(t.kind, seg('variant', block.variant, [['primary', t.buttonVariants.primary], ['secondary', t.buttonVariants.secondary]])));
                parts.push(row(t.align, seg('align', block.align, [['left', t.aligns.left], ['center', t.aligns.center], ['right', t.aligns.right]])));
            }
            const i = this.blocks.indexOf(block);
            parts.push(`
                <div class="bk-menu-actions">
                    <button type="button" data-act="up"${i === 0 ? ' disabled' : ''}><span class="material-symbols-outlined" aria-hidden="true">arrow_upward</span>${esc(t.moveUp)}</button>
                    <button type="button" data-act="down"${i === this.blocks.length - 1 ? ' disabled' : ''}><span class="material-symbols-outlined" aria-hidden="true">arrow_downward</span>${esc(t.moveDown)}</button>
                    <button type="button" data-act="duplicate"><span class="material-symbols-outlined" aria-hidden="true">content_copy</span>${esc(t.duplicate)}</button>
                    <button type="button" data-act="delete" class="is-danger"><span class="material-symbols-outlined" aria-hidden="true">delete</span>${esc(t.remove)}</button>
                </div>`);
            pop.innerHTML = parts.join('');

            pop.onchange = (e) => {
                const el = e.target;
                const key = el.closest('[data-set]') && el.closest('[data-set]').dataset.set;
                if (!key) return;
                const value = el.type === 'checkbox' ? el.checked : el.value;
                // 作り直しても読んでいた位置がずれないよう、メニューのスクロール位置を引き継ぐ
                const reopen = () => { const top = pop.scrollTop; this.openMenu(block, anchor); pop.scrollTop = top; };
                if (key === 'type') { this.convert(block, value); reopen(); return; }
                if (key === 'columns') { this.setColumns(block, Number(value)); reopen(); return; }
                if (block.type === 'demo' && key === 'bg') {
                    block.bg = value; // デモの背景 (ブロックの見た目の背景 style.bg とは別)
                } else if (block.type === 'demo' && key === 'compare') {
                    // 比較をオンにしたとき「変更前」が空なら、今の CSS を写して出発点にする
                    block.compare = value;
                    if (value && !block.beforeCss) block.beforeCss = block.css;
                    this.renderBody(block);
                    this.changed();
                    reopen();
                    return;
                } else if (block.type === 'demo' && (key === 'beforeLabel' || key === 'afterLabel')) {
                    block[key] = value.trim();
                    const el = block.el.querySelector(`.bk-cmp-label--${key === 'beforeLabel' ? 'before' : 'after'}`);
                    if (el) el.textContent = block[key] || (key === 'beforeLabel' ? 'Before' : 'After');
                    this.changed();
                    return;
                } else if (['ratio', 'variant', 'height', 'align', 'label', 'url', 'icon', 'layout'].includes(key)) {
                    block[key] = key === 'icon' ? (value.trim() || '💡') : value.trim();
                } else {
                    block.style[key] = value;
                }
                this.renderBody(block);
                this.changed();
            };
            pop.oninput = (e) => {
                // テキスト入力は入力のたびに反映 (ボタン名・アイコン)
                if (e.target.matches('input[type="text"], input[type="url"]')) pop.onchange(e);
            };
            pop.onclick = (e) => {
                const btn = e.target.closest('[data-act]');
                if (!btn) return;
                const act = btn.dataset.act;
                const idx = this.blocks.indexOf(block);
                this.closePopover(pop);
                if (act === 'up') this.moveBlock(block, idx - 1);
                if (act === 'down') this.moveBlock(block, idx + 2);
                if (act === 'duplicate') this.duplicate(block);
                if (act === 'delete') this.removeBlock(block);
            };
            this.closePopover(this.inserter);
            this.placePopover(pop, anchor);
        }
    }

    return { BlockEditor, INSERT_ITEMS };
})();
