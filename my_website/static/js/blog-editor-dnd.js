/**
 * Blogs エディタ — ドラッグ＆ドロップの共通部品
 * - パソコンから画像ファイルをドロップ: 段落の間、またはブロックの間 (新しいブロック) にアップロードして挿入
 * - 本文の画像を別のブロック (別の列) へ移動するときの落とし先の判定と挿入 (blog-editor-images.js から使う)
 * - ドラッグ中に画面の端へ近づいたときの自動スクロール
 * 落とし先は 2 種類:
 *   { kind: 'line', quill, line, after }  … ある列 (Quill) の段落の前後
 *   { kind: 'block', before }             … ブロックの間 (before の直前。null なら末尾) に新しいテキストブロック
 * どちらも DOM / ブロックへの参照で持ち、挿入する瞬間に位置を数え直す (アップロード中に本文が変わってもずれない)。
 */
window.BlogEditorDnd = (() => {
    const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'];
    const PARALLEL = 3;
    const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)');

    /** 画面の上下の端に近づくと、近さに応じた速さでスクロールし続ける */
    function autoScroller() {
        // 上はヘッダーとツールバー、下は保存バーに隠れる分だけ広めに取る
        const TOP = 110;
        const BOTTOM = 130;
        const MAX = 22;
        let y = null;
        let frame = 0;
        let onTick = null;
        const step = () => {
            frame = 0;
            if (y === null) return;
            const h = window.visualViewport ? window.visualViewport.height : window.innerHeight;
            let v = 0;
            if (y < TOP) v = -MAX * (Math.min(TOP, TOP - y) / TOP) ** 2;
            else if (y > h - BOTTOM) v = MAX * (Math.min(BOTTOM, y - (h - BOTTOM)) / BOTTOM) ** 2;
            if (!v) return;
            const before = window.scrollY;
            window.scrollBy(0, v);
            if (window.scrollY !== before && onTick) onTick();
            frame = requestAnimationFrame(step);
        };
        return {
            update(clientY, tick) {
                y = clientY;
                onTick = tick;
                if (!frame) frame = requestAnimationFrame(step);
            },
            stop() {
                y = null;
                if (frame) cancelAnimationFrame(frame);
                frame = 0;
            },
        };
    }

    function create({ Quill, root, getBlocks, upload, t = {} }) {
        const USER = Quill.sources.USER;
        const Delta = Quill.import('delta');

        // 落とし先の線 (段落の間は細く、ブロックの間は太く左端に丸)。position: fixed で滑らかに動かす
        // フォームの中に置き、記事のアクセント色 (--blog-accent) を受け継ぐ
        const host = root.closest('form') || document.body;
        const caret = document.createElement('div');
        caret.className = 'bk-drop-caret';
        caret.hidden = true;
        host.append(caret);

        // アップロードの進み具合 (画面下)
        const toast = document.createElement('div');
        toast.className = 'bk-upload-toast';
        toast.setAttribute('role', 'status');
        toast.hidden = true;
        toast.innerHTML = `<span class="bk-upload-spinner" aria-hidden="true"></span>
            <span class="bk-upload-text"></span><span class="bk-upload-bar" aria-hidden="true"><i></i></span>`;
        host.append(toast);

        const cellOf = (el) => {
            const editor = getBlocks();
            for (const block of editor.blocks) {
                for (const cell of block.cells) {
                    if (cell.el.contains(el)) return { block, cell };
                }
            }
            return null;
        };

        /** ある列の中で、y に一番近い段落 (Quill の最上位の行) */
        function nearestLine(quill, y) {
            const lines = [...quill.root.children];
            let best = null;
            let bestDist = Infinity;
            for (const line of lines) {
                const r = line.getBoundingClientRect();
                if (!r.height) continue;
                if (y >= r.top && y <= r.bottom) return line;
                const d = Math.min(Math.abs(y - r.top), Math.abs(y - r.bottom));
                if (d < bestDist) { bestDist = d; best = line; }
            }
            return best;
        }

        /** 座標 (x, y) に落としたときの挿入先。exclude (移動中の画像) の行そのものは除く */
        function resolve(x, y, { exclude = null } = {}) {
            const editor = getBlocks();
            const el = document.elementFromPoint(x, y);
            if (!el) return null;
            const hit = cellOf(el);
            if (hit) {
                const { quill } = hit.cell;
                const line = nearestLine(quill, y);
                if (!line) return null;
                if (exclude && line.contains(exclude)) return null;
                const r = line.getBoundingClientRect();
                return { kind: 'line', quill, line, after: y > r.top + r.height / 2 };
            }
            // 列の外: ブロックの帯の近く (左右のガターと上下の余白を含む) ならブロックの間
            const rr = root.getBoundingClientRect();
            const addBtn = document.getElementById('blog-add-block');
            const bottom = addBtn ? addBtn.getBoundingClientRect().bottom : rr.bottom;
            if (x < rr.left - 80 || x > rr.right + 80 || y < rr.top - 40 || y > bottom + 40) return null;
            let before = null;
            for (const b of editor.blocks) {
                const r = b.el.getBoundingClientRect();
                if (y < r.top + r.height / 2) { before = b; break; }
            }
            return { kind: 'block', before };
        }

        function show(target) {
            if (!target) { hide(); return; }
            let rect;
            if (target.kind === 'line') {
                const r = target.line.getBoundingClientRect();
                const c = target.quill.root.getBoundingClientRect();
                rect = { left: c.left, width: c.width, top: (target.after ? r.bottom : r.top) - 1.5 };
            } else {
                const editor = getBlocks();
                const rr = root.getBoundingClientRect();
                let y;
                if (target.before) {
                    const i = editor.blocks.indexOf(target.before);
                    const r = target.before.el.getBoundingClientRect();
                    const prev = editor.blocks[i - 1];
                    y = prev ? (prev.el.getBoundingClientRect().bottom + r.top) / 2 : r.top - 4;
                } else {
                    const last = editor.blocks[editor.blocks.length - 1];
                    y = last ? last.el.getBoundingClientRect().bottom + 4 : rr.top;
                }
                rect = { left: rr.left + 20, width: rr.width - 40, top: y - 1.5 };
            }
            caret.classList.toggle('is-block', target.kind === 'block');
            const first = caret.hidden;
            caret.hidden = false;
            if (first) caret.classList.add('is-instant'); // 現れた瞬間は滑らせない
            Object.assign(caret.style, { transform: `translate3d(${rect.left}px, ${rect.top}px, 0)`, width: `${rect.width}px` });
            if (first) requestAnimationFrame(() => caret.classList.remove('is-instant'));
        }

        function hide() { caret.hidden = true; }

        // ── 挿入 ─────────────────────────────────────
        /** quill の at (行の先頭) に画像だけの行を作る。at が末尾 (getLength) なら最後の行の後ろ */
        function insertImageLine(quill, at, image, attributes) {
            const len = quill.getLength();
            if (len <= 1) {
                // 空の列: 空行を画像の行にする
                quill.updateContents(new Delta().insert({ image }, attributes || undefined), USER);
                return 0;
            }
            if (at >= len) {
                // 最後の行の後ろ: 最後の改行 (行の書式を持つ) を前の行に残し、画像の行は書式なしにする
                const [line] = quill.getLine(len - 1);
                const formats = line ? line.formats() : {};
                const clear = Object.fromEntries(Object.keys(formats).map((k) => [k, null]));
                quill.updateContents(new Delta().retain(len - 1).insert('\n', formats)
                    .insert({ image }, attributes || undefined).retain(1, clear), USER);
                return len;
            }
            // 行の前: 画像 + 書式なしの改行を差し込む (元の行の書式は変えない)
            quill.updateContents(new Delta().retain(at).insert({ image }, attributes || undefined).insert('\n'), USER);
            return at;
        }

        /** 挿入先 target に画像 (images: [{ image, attributes }]) を順に並べる。最後に入れた画像の { quill, index } */
        function insertImages(target, images) {
            const editor = getBlocks();
            let quill;
            let at;
            if (target.kind === 'line' && target.quill.root.contains(target.line)) {
                quill = target.quill;
                const blot = Quill.find(target.line);
                at = blot ? quill.getIndex(blot) + (target.after ? blot.length() : 0) : quill.getLength();
            } else if (target.kind === 'line' && target.quill.root.isConnected) {
                quill = target.quill; // 行が消えていたら列の末尾へ
                at = quill.getLength();
            } else {
                const index = target.before && editor.blocks.includes(target.before)
                    ? editor.blocks.indexOf(target.before) : editor.blocks.length;
                const block = editor.insertBlock({ type: 'text' }, index);
                quill = block.cells[0].quill;
                at = 0;
            }
            let last = null;
            images.forEach(({ image, attributes }) => {
                const index = insertImageLine(quill, at, image, attributes);
                last = index;
                at = index + 2; // 画像 + 改行
            });
            if (last !== null) quill.setSelection(Math.min(last + 1, quill.getLength() - 1), 0, Quill.sources.SILENT);
            return last === null ? null : { quill, index: last };
        }

        /** 画像を削除。その行が画像だけなら行ごと消して空行を残さない */
        function removeImageAt(quill, index) {
            const [line] = quill.getLine(index);
            const onlyImage = line && line.length() === 2 && index === quill.getIndex(line);
            quill.deleteText(index, onlyImage ? 2 : 1, USER);
        }

        /** 本文の画像を別の場所へ移す。移した先の <img> を返す */
        function moveImage(quill, img, target) {
            const blot = Quill.find(img);
            if (!blot) return null;
            const from = quill.getIndex(blot);
            const [op] = quill.getContents(from, 1).ops;
            if (!op || !op.insert || !op.insert.image) return null;
            const editor = getBlocks();
            const source = quill.__block;
            removeImageAt(quill, from);
            const placed = insertImages(target, [{ image: op.insert.image, attributes: op.attributes }]);
            // 画像だけが入っていたブロックは、画像を持ち出したら空のまま残さない
            if (source && source !== (placed && placed.quill.__block) && source.type === 'text'
                && source.cells.length === 1 && quill.getLength() <= 1 && editor.blocks.length > 1) {
                editor.removeBlock(source);
            }
            if (!placed) return null;
            const [leaf] = placed.quill.getLeaf(placed.index + 1);
            const el = leaf && leaf.domNode && leaf.domNode.tagName === 'IMG' ? leaf.domNode : null;
            if (el && !REDUCED_MOTION.matches) {
                el.animate([{ opacity: 0.2, transform: 'scale(0.96)' }, { opacity: 1, transform: 'none' }],
                { duration: 320, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' })
                .finished.then(() => window.dispatchEvent(new Event('resize'))); // 選択枠を最終的な大きさに合わせる
            }
            return el ? { quill: placed.quill, img: el } : null;
        }

        // ── ファイルのドロップ (パソコンから) ───────────────
        const hasFiles = (e) => e.dataTransfer && [...e.dataTransfer.types].includes('Files');
        const hasImage = (e) => {
            const items = [...(e.dataTransfer.items || [])];
            // ドラッグ中は種類が分からないブラウザもあるので、分からなければ画像とみなす
            return !items.length || items.some((it) => it.kind === 'file' && (!it.type || it.type.startsWith('image/')));
        };
        const canvas = root.closest('.blog-editor-canvas') || root;
        const cover = document.getElementById('blog-cover-drop');
        // ファイルを持ってきている間、本文の上に出す案内 (レイアウトをずらさないよう fixed)
        const hint = document.createElement('div');
        hint.className = 'bk-drop-hint';
        hint.hidden = true;
        hint.textContent = t.dropHint || '';
        host.append(hint);
        const scroller = autoScroller();
        let depth = 0;
        let target = null;
        let last = null;

        const endFileDrag = () => {
            depth = 0;
            target = null;
            hide();
            scroller.stop();
            canvas.classList.remove('is-file-dragging');
            hint.hidden = true;
        };
        const track = (x, y) => {
            target = resolve(x, y);
            show(target);
        };

        document.addEventListener('dragenter', (e) => {
            if (!hasFiles(e)) return;
            depth += 1;
            if (!canvas.classList.contains('is-file-dragging')) {
                canvas.classList.add('is-file-dragging');
                const r = root.getBoundingClientRect();
                hint.style.left = `${r.left + r.width / 2}px`;
                hint.hidden = !t.dropHint;
            }
        });
        document.addEventListener('dragleave', (e) => {
            if (!hasFiles(e)) return;
            depth = Math.max(0, depth - 1);
            if (!depth) endFileDrag();
        });
        document.addEventListener('dragover', (e) => {
            if (!hasFiles(e)) return;
            e.preventDefault(); // ページの外へ落としてもブラウザが画像を開いて移動しないように
            if (cover && cover.contains(e.target)) { hide(); return; } // カバー画像は専用の受け皿
            if (!hasImage(e)) { e.dataTransfer.dropEffect = 'none'; hide(); return; }
            e.dataTransfer.dropEffect = 'copy';
            last = { x: e.clientX, y: e.clientY };
            track(e.clientX, e.clientY);
            scroller.update(e.clientY, () => track(last.x, last.y));
        });
        // Quill 自身のドロップ処理 (カーソル位置へ挿入) より先に受け取る
        document.addEventListener('drop', (e) => {
            if (!hasFiles(e)) return;
            if (cover && cover.contains(e.target)) { endFileDrag(); return; }
            e.preventDefault();
            e.stopPropagation();
            const dropTo = target || resolve(e.clientX, e.clientY);
            endFileDrag();
            const files = [...e.dataTransfer.files].filter((f) => IMAGE_TYPES.includes(f.type));
            if (!dropTo || !files.length) return;
            uploadAll(files, dropTo);
        }, true);
        window.addEventListener('blur', endFileDrag);

        // ── アップロード (並列・進み具合つき) ───────────────
        let jobs = 0;
        let loaded = 0;
        let total = 0;
        let doneCount = 0;
        let fileCount = 0;
        const renderToast = () => {
            toast.hidden = !jobs;
            if (!jobs) return;
            toast.querySelector('.bk-upload-text').textContent = `${t.uploading || ''} ${doneCount} / ${fileCount}`;
            toast.querySelector('.bk-upload-bar i').style.transform = `scaleX(${total ? Math.min(1, loaded / total) : 0})`;
        };

        async function uploadAll(files, dropTo) {
            jobs += 1;
            fileCount += files.length;
            total += files.reduce((s, f) => s + f.size, 0);
            renderToast();
            const results = new Array(files.length);
            const progress = new Array(files.length).fill(0);
            let next = 0;
            const worker = async () => {
                while (next < files.length) {
                    const i = next++;
                    try {
                        results[i] = await upload(files[i], (n) => {
                            loaded += n - progress[i];
                            progress[i] = n;
                            renderToast();
                        });
                    } catch (err) {
                        results[i] = null;
                        alert(err.message || t.uploadFailed);
                    }
                    loaded += files[i].size - progress[i];
                    progress[i] = files[i].size;
                    doneCount += 1;
                    renderToast();
                }
            };
            await Promise.all(Array.from({ length: Math.min(PARALLEL, files.length) }, worker));
            const images = results.filter(Boolean).map((image) => ({ image }));
            if (images.length) insertImages(dropTo, images);
            jobs -= 1;
            if (!jobs) { loaded = total = doneCount = fileCount = 0; }
            renderToast();
        }

        return { resolve, show, hide, insertImages, moveImage, autoScroller, t };
    }

    return { create, autoScroller };
})();
