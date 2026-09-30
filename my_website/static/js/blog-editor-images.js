/**
 * Blogs エディタ — 本文画像のサイズ変更・移動
 * - 画像をクリック: 選択枠と四隅のハンドルを表示 (配置ボタンはその行に効く)
 * - ハンドルをドラッグ: 幅を変更 (縦横比は維持。保存時は <img width="…">)
 * - 画像本体をドラッグ: 段落の間に挿入位置の線を表示し、離した位置へ移動 (画像は常に独立した行)
 * - ダブルクリック: 元のサイズに戻す / Delete・Backspace: 削除
 * 選択枠は .ql-editor の外 (エディタのコンテナ) に置くので本文には混ざらない。
 */
window.BlogEditorImages = (() => {
    const MIN_WIDTH = 48;
    const DRAG_THRESHOLD = 5;

    function setup(quill, Quill) {
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
            <span class="blog-img-size"></span>`;
        const sizeLabel = overlay.querySelector('.blog-img-size');
        const caret = document.createElement('div');
        caret.className = 'blog-img-drop-caret';
        caret.hidden = true;
        container.append(overlay, caret);

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
            const onMove = (ev) => {
                const dx = (ev.clientX - startX) * (corner.includes('w') ? -1 : 1);
                width = Math.round(Math.min(maxWidth, Math.max(MIN_WIDTH, startWidth + dx)));
                container.style.setProperty('--blog-resize-w', `${width}px`);
                container.classList.add('blog-img-resizing');
                position();
            };
            const onUp = () => {
                handle.removeEventListener('pointermove', onMove);
                handle.removeEventListener('pointerup', onUp);
                overlay.classList.remove('is-resizing');
                container.classList.remove('blog-img-resizing');
                const index = indexOf(img);
                if (index >= 0 && width !== Math.round(startWidth)) {
                    quill.formatText(index, 1, { width: String(width), height: false }, USER);
                }
                requestAnimationFrame(position);
            };
            handle.addEventListener('pointermove', onMove);
            handle.addEventListener('pointerup', onUp);
        });

        // ── 移動 (画像本体をドラッグ) ──────────────
        // 画像は段落の「間」に独立した行として置く。文字の途中に入ると読みにくいため。
        const topBlock = (node) => {
            let el = node && node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
            while (el && el.parentElement !== quill.root) el = el.parentElement;
            return el && el.parentElement === quill.root ? el : null;
        };

        quill.root.addEventListener('pointerdown', (e) => {
            if (e.target.tagName !== 'IMG' || e.button !== 0) return;
            const img = e.target;
            const startX = e.clientX;
            const startY = e.clientY;
            let dragging = false;
            let drop = null; // { block, after }

            const onMove = (ev) => {
                if (!dragging) {
                    if (Math.hypot(ev.clientX - startX, ev.clientY - startY) < DRAG_THRESHOLD) return;
                    dragging = true;
                    select(img);
                    overlay.classList.add('is-moving');
                    document.body.classList.add('blog-img-dragging');
                }
                ev.preventDefault();
                const r0 = quill.root.getBoundingClientRect();
                const x = Math.min(Math.max(ev.clientX, r0.left + 1), r0.right - 1);
                const block = topBlock(document.elementFromPoint(x, ev.clientY));
                if (!block || block.contains(img)) { drop = null; caret.hidden = true; return; }
                const rect = block.getBoundingClientRect();
                const after = ev.clientY > rect.top + rect.height / 2;
                drop = { block, after };
                const c = container.getBoundingClientRect();
                Object.assign(caret.style, {
                    left: `${rect.left - c.left}px`,
                    top: `${(after ? rect.bottom : rect.top) - c.top - 1}px`,
                    width: `${rect.width}px`,
                });
                caret.hidden = false;
            };
            const onUp = () => {
                document.removeEventListener('pointermove', onMove);
                document.removeEventListener('pointerup', onUp);
                caret.hidden = true;
                overlay.classList.remove('is-moving');
                document.body.classList.remove('blog-img-dragging');
                if (!dragging || !drop) return;

                const from = indexOf(img);
                if (from < 0) return;
                const [op] = quill.getContents(from, 1).ops;
                removeImageAt(from);

                const blot = Quill.find(drop.block);
                if (!blot || !quill.root.contains(drop.block)) return;
                let at = quill.getIndex(blot) + (drop.after ? blot.length() : 0);
                if (at >= quill.getLength()) {
                    // 末尾の段落の後ろ: 改行を足してから画像の行を作る
                    at = quill.getLength() - 1;
                    quill.insertText(at, '\n', USER);
                    at += 1;
                    quill.insertEmbed(at, 'image', op.insert.image, USER);
                } else {
                    quill.insertEmbed(at, 'image', op.insert.image, USER);
                    quill.insertText(at + 1, '\n', USER);
                }
                if (op.attributes) quill.formatText(at, 1, op.attributes, USER);
                const moved = quill.getLeaf(at + 1)[0];
                if (moved && moved.domNode && moved.domNode.tagName === 'IMG') select(moved.domNode);
            };
            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onUp);
        });

        return { deselect };
    }

    return { setup };
})();
