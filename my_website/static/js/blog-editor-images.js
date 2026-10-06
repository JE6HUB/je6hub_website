/**
 * Blogs エディタ — 本文画像のサイズ変更・移動
 * - 画像をクリック: 選択枠と四隅のハンドルを表示 (配置ボタンはその行に効く)
 * - ハンドルをドラッグ: 幅を変更 (縦横比は維持。列幅の 25 / 33 / 50 / 66 / 75 / 100% に吸い付く。保存時は <img width="…">)
 * - 画像本体 (タッチでは選択枠の上の移動つまみ) をドラッグ: 段落の間に挿入位置の線を表示し、離した位置へ移動。
 *   別のブロックや列にも移せ、ブロックの間に落とすと新しいブロックになる (落とし先の判定は blog-editor-dnd.js)
 * - ダブルクリック: 元のサイズに戻す / Delete・Backspace: 削除
 * 選択枠は .ql-editor の外 (エディタのコンテナ) に置くので本文には混ざらない。
 */
window.BlogEditorImages = (() => {
    const MIN_WIDTH = 48;
    const DRAG_THRESHOLD = 5;
    const SNAPS = [0.25, 1 / 3, 0.5, 2 / 3, 0.75, 1];
    const SNAP_RANGE = 0.018;

    /** @param dnd blog-editor-dnd.js の create() の戻り値 (落とし先の判定・挿入・自動スクロール) */
    function setup(quill, Quill, dnd) {
        const USER = Quill.sources.USER;
        const container = quill.container;
        const overlay = document.createElement('div');
        overlay.className = 'blog-img-overlay';
        overlay.hidden = true;
        overlay.innerHTML = `
            <span class="blog-img-handle" data-corner="nw"></span>
            <span class="blog-img-handle" data-corner="ne"></span>
            <span class="blog-img-handle" data-corner="sw"></span>
            <span class="blog-img-handle" data-corner="se"></span>
            <button type="button" class="blog-img-move" aria-label="${(dnd.t && dnd.t.moveImage) || ''}" title="${(dnd.t && dnd.t.moveImage) || ''}">
                <span class="material-symbols-outlined" aria-hidden="true">open_with</span></button>
            <span class="blog-img-size"></span>`;
        const sizeLabel = overlay.querySelector('.blog-img-size');
        container.append(overlay);

        let selected = null;

        const indexOf = (img) => {
            const blot = Quill.find(img);
            return blot ? quill.getIndex(blot) : -1;
        };

        function position() {
            if (!selected || !quill.root.contains(selected)) { deselect(); return; }
            const c = container.getBoundingClientRect();
            const r = selected.getBoundingClientRect();
            Object.assign(overlay.style, {
                left: `${r.left - c.left}px`,
                top: `${r.top - c.top}px`,
                width: `${r.width}px`,
                height: `${r.height}px`,
            });
            sizeLabel.textContent = `${Math.round(r.width)} × ${Math.round(r.height)}`;
        }

        function select(img) {
            if (selected && selected !== img) selected.classList.remove('blog-img-selected');
            selected = img;
            img.classList.add('blog-img-selected'); // class は Delta に含まれないので本文は変わらない
            overlay.hidden = false;
            position();
            // 配置ボタン (左・中央・右) がこの行に効くよう、カーソルを画像の直前に置く。
            // 画像そのものを選択範囲にすると、ブラウザの選択色で画像が青く塗られるため。
            const index = indexOf(img);
            if (index >= 0) quill.setSelection(index, 0, Quill.sources.SILENT);
        }

        function deselect() {
            if (selected) selected.classList.remove('blog-img-selected');
            selected = null;
            overlay.hidden = true;
        }

        // ── 選択 ─────────────────────────────
        quill.root.addEventListener('click', (e) => {
            if (e.target.tagName === 'IMG') select(e.target);
            else deselect();
        });
        document.addEventListener('pointerdown', (e) => {
            if (selected && !container.contains(e.target)) deselect();
        });
        quill.on('text-change', () => requestAnimationFrame(position));
        window.addEventListener('resize', () => requestAnimationFrame(position));
        window.addEventListener('scroll', () => requestAnimationFrame(position), { passive: true });
        // Quill より先に処理するため capture で登録
        quill.root.addEventListener('keydown', (e) => {
            if (!selected) return;
            if (e.key === 'Escape') {
                deselect();
            } else if (e.key === 'Backspace' || e.key === 'Delete') {
                e.preventDefault();
                e.stopPropagation();
                const index = indexOf(selected);
                deselect();
                if (index >= 0) removeImageAt(index);
            } else {
                deselect(); // 文字入力などは通常どおり (カーソルは画像の直前)
            }
        }, true);

        /** 画像を削除。その行が画像だけなら行ごと消して空行を残さない */
        function removeImageAt(index) {
            const [line] = quill.getLine(index);
            const onlyImage = line && line.length() === 2 && index === quill.getIndex(line);
            quill.deleteText(index, onlyImage ? 2 : 1, USER);
            quill.setSelection(Math.min(index, quill.getLength() - 1), Quill.sources.SILENT);
        }

        // ネイティブのドラッグ (Quill の drop 処理と衝突する) は使わない
        quill.root.addEventListener('dragstart', (e) => {
            if (e.target.tagName === 'IMG') e.preventDefault();
        });

        // ── ダブルクリックで元のサイズ ─────────────
        quill.root.addEventListener('dblclick', (e) => {
            if (e.target.tagName !== 'IMG') return;
            const index = indexOf(e.target);
            if (index < 0) return;
            quill.formatText(index, 1, { width: false, height: false }, USER);
            requestAnimationFrame(position);
        });

        // ── サイズ変更 (四隅のハンドル) ────────────
        overlay.addEventListener('pointerdown', (e) => {
            const handle = e.target.closest('.blog-img-handle');
            if (!handle || !selected) return;
            e.preventDefault();
            e.stopPropagation();
            const img = selected;
            const corner = handle.dataset.corner;
            const startX = e.clientX;
            const startWidth = img.getBoundingClientRect().width;
            const maxWidth = quill.root.clientWidth;
            handle.setPointerCapture(e.pointerId);
            overlay.classList.add('is-resizing');
            let width = Math.round(startWidth);

            // ドラッグ中は本文の DOM を触らず (Quill が変更として記録するため)、
            // 監視対象外のコンテナに置いた CSS 変数で見た目だけ変える。確定は離したときの 1 回。
            const ratio = img.naturalWidth ? img.naturalHeight / img.naturalWidth : startWidth ? img.getBoundingClientRect().height / startWidth : 1;
            let frame = 0;
            let lastEv = null;
            const update = () => {
                frame = 0;
                const ev = lastEv;
                const dx = (ev.clientX - startX) * (corner.includes('w') ? -1 : 1);
                let w = Math.min(maxWidth, Math.max(MIN_WIDTH, startWidth + dx));
                // 列幅のきりのよい割合に吸い付く (Alt / Option を押している間は吸い付かない)
                const snap = ev.altKey ? null : SNAPS.find((p) => Math.abs(w / maxWidth - p) < SNAP_RANGE);
                if (snap) w = maxWidth * snap;
                width = Math.round(w);
                container.style.setProperty('--blog-resize-w', `${width}px`);
                container.classList.add('blog-img-resizing');
                overlay.classList.toggle('is-snapped', !!snap);
                position();
                sizeLabel.textContent = `${width} × ${Math.round(width * ratio)} · ${Math.round((width / maxWidth) * 100)}%`;
            };
            const onMove = (ev) => {
                lastEv = ev;
                if (!frame) frame = requestAnimationFrame(update);
            };
            const onUp = () => {
                if (frame) { cancelAnimationFrame(frame); update(); }
                handle.removeEventListener('pointermove', onMove);
                handle.removeEventListener('pointerup', onUp);
                handle.removeEventListener('pointercancel', onUp);
                overlay.classList.remove('is-resizing', 'is-snapped');
                container.classList.remove('blog-img-resizing');
                const index = indexOf(img);
                if (index >= 0 && width !== Math.round(startWidth)) {
                    quill.formatText(index, 1, { width: String(width), height: false }, USER);
                }
                requestAnimationFrame(position);
            };
            handle.addEventListener('pointermove', onMove);
            handle.addEventListener('pointerup', onUp);
            handle.addEventListener('pointercancel', onUp);
        });

        // ── 移動 (画像本体、またはタッチでは移動つまみをドラッグ) ──────
        // 画像は段落の「間」に独立した行として置く。文字の途中に入ると読みにくいため。
        // 落とし先は同じ列に限らず、別のブロック・別の列・ブロックの間 (新しいブロック) でもよい。
        function startMove(img, e, immediate) {
            const startX = e.clientX;
            const startY = e.clientY;
            const scroller = dnd.autoScroller();
            let dragging = false;
            let drop = null;
            let ghost = null;
            let last = e;
            let frame = 0;

            const begin = () => {
                dragging = true;
                select(img);
                overlay.classList.add('is-moving');
                document.body.classList.add('blog-img-dragging');
                // 指 (マウス) についてくる小さな画像
                const r = img.getBoundingClientRect();
                const w = Math.min(160, r.width);
                ghost = document.createElement('div');
                ghost.className = 'blog-img-ghost';
                ghost.style.width = `${w}px`;
                ghost.style.height = `${r.height * (w / r.width)}px`;
                ghost.style.backgroundImage = `url("${img.src.replace(/"/g, '%22')}")`;
                (container.closest('form') || document.body).append(ghost);
                requestAnimationFrame(() => ghost && ghost.classList.add('is-lifted'));
            };
            const track = () => {
                frame = 0;
                if (!dragging) return;
                if (ghost) {
                    // 指で操作しているときは指に隠れないよう、指の上に出す
                    const touch = last.pointerType === 'touch';
                    const gx = touch ? last.clientX - ghost.offsetWidth / 2 : last.clientX + 14;
                    const gy = touch ? last.clientY - ghost.offsetHeight - 28 : last.clientY + 14;
                    ghost.style.transform = `translate3d(${gx}px, ${gy}px, 0)`;
                }
                drop = dnd.resolve(last.clientX, last.clientY, { exclude: img });
                dnd.show(drop);
            };
            const onMove = (ev) => {
                if (!dragging) {
                    if (Math.hypot(ev.clientX - startX, ev.clientY - startY) < DRAG_THRESHOLD) return;
                    begin();
                }
                ev.preventDefault();
                last = ev;
                if (!frame) frame = requestAnimationFrame(track);
                scroller.update(ev.clientY, track);
            };
            const onUp = (ev) => {
                document.removeEventListener('pointermove', onMove);
                document.removeEventListener('pointerup', onUp);
                document.removeEventListener('pointercancel', onUp);
                if (frame) cancelAnimationFrame(frame);
                scroller.stop();
                dnd.hide();
                overlay.classList.remove('is-moving');
                document.body.classList.remove('blog-img-dragging');
                if (ghost) {
                    const g = ghost;
                    ghost = null;
                    g.classList.remove('is-lifted');
                    g.classList.add('is-dropped');
                    setTimeout(() => g.remove(), 200);
                }
                if (!dragging || ev.type === 'pointercancel' || !drop) return;
                deselect();
                const moved = dnd.moveImage(quill, img, drop);
                if (moved && moved.quill.__images) moved.quill.__images.select(moved.img);
            };
            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onUp);
            document.addEventListener('pointercancel', onUp);
            if (immediate) begin();
        }

        quill.root.addEventListener('pointerdown', (e) => {
            // タッチでは画像に触れてもスクロールできるように、移動は選択枠の移動つまみから
            if (e.target.tagName !== 'IMG' || e.button !== 0 || e.pointerType === 'touch') return;
            startMove(e.target, e, false);
        });
        overlay.querySelector('.blog-img-move').addEventListener('pointerdown', (e) => {
            if (!selected || e.button !== 0) return;
            e.preventDefault();
            e.stopPropagation();
            startMove(selected, e, true);
        });

        return { select, deselect };
    }

    return { setup };
})();
