/**
 * Blogs — 記事エディタ
 * Quill 2 をサイトのデザインに合わせて初期化し、本文画像のアップロード、
 * カバー画像、テンプレート/アクセントの即時反映、未保存警告を扱う。
 * 本文はブロックエディタ (blog-blocks.js)。各列の Quill に、数式・Markdown・画像の
 * サイズ変更/移動 (blog-editor-{math,markdown,images}.js) を組み込む。
 */
(() => {
    const form = document.getElementById('blog-post-form');
    if (!form || typeof Quill === 'undefined') return;

    const t = window.BLOG_EDITOR_I18N || {};
    const csrfToken = form.querySelector('input[name="csrfmiddlewaretoken"]').value;
    const uploadUrl = form.dataset.uploadUrl;
    const bodyHtmlInput = document.getElementById('id_body_html');
    const bodyDeltaInput = document.getElementById('id_body_delta');
    const bodyBlocksInput = document.getElementById('id_body_blocks');
    const statusEl = document.getElementById('blog-save-status');

    let dirty = false;
    const markDirty = () => {
        dirty = true;
        statusEl.textContent = t.unsaved || '';
    };

    // ── 区切り線 (hr) ブロック ─────────────────────────
    const BlockEmbed = Quill.import('blots/block/embed');
    class DividerBlot extends BlockEmbed {}
    DividerBlot.blotName = 'divider';
    DividerBlot.tagName = 'hr';
    Quill.register(DividerBlot);

    // ── 数式ブロット (Quill 生成前に登録) ──────────────
    const { BlogEditorMath, BlogEditorMarkdown, BlogEditorImages, BlogBlocks } = window;
    BlogEditorMath.register(Quill);

    // ── 画像アップロード ──────────────────────────────
    async function uploadImage(file) {
        const data = new FormData();
        data.append('image', file);
        const res = await fetch(uploadUrl, {
            method: 'POST',
            body: data,
            headers: { 'X-CSRFToken': csrfToken },
            credentials: 'same-origin',
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok || !json.url) throw new Error(json.error || t.uploadFailed);
        return json.url;
    }

    async function insertImages(quill, files, index) {
        let pos = index;
        for (const file of files) {
            if (!file.type.startsWith('image/')) continue;
            statusEl.textContent = t.uploading || '';
            try {
                const url = await uploadImage(file);
                quill.insertEmbed(pos, 'image', url, Quill.sources.USER);
                pos += 1;
                quill.setSelection(pos, Quill.sources.SILENT);
            } catch (err) {
                alert(err.message || t.uploadFailed);
            }
        }
        statusEl.textContent = dirty ? (t.unsaved || '') : '';
    }

    function pickImage(quill) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/jpeg,image/png,image/gif,image/webp,image/svg+xml';
        input.multiple = true;
        input.addEventListener('change', () => {
            const range = quill.getSelection(true) || { index: quill.getLength() - 1 };
            insertImages(quill, Array.from(input.files), range.index);
        });
        input.click();
    }

    // ── ブロックエディタ ───────────────────────────────
    const getActive = () => blocks.active || (blocks.blocks.find((b) => b.cells.length) || { cells: [{}] }).cells[0].quill;
    const math = BlogEditorMath.setup(getActive, Quill);
    const markdownImport = BlogEditorMarkdown.setupImport(getActive, Quill);

    const blocks = new BlogBlocks.BlockEditor(document.getElementById('blog-blocks'), {
        Quill,
        t: t.blocks,
        quillOptions: () => ({
            theme: 'snow',
            placeholder: t.placeholder || '',
            modules: {
                toolbar: false, // ツールバーは全ブロック共通 (最後にフォーカスした列に効く)
                keyboard: { bindings: BlogEditorMarkdown.bindings(Quill, () => math) },
                // ドラッグ＆ドロップ / 貼り付けされた画像も base64 埋め込みではなくサーバーへアップロード
                uploader: {
                    mimetypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'],
                    handler(range, files) { insertImages(this.quill, files, range.index); },
                },
            },
        }),
        onQuill(quill) {
            BlogEditorImages.setup(quill, Quill);
            math.attach(quill);
            quill.on('selection-change', () => toolbar.refresh());
            quill.on('text-change', () => toolbar.refresh());
        },
        onChange: markDirty,
        pickImage,
        openMath: (quill) => math.open({ displayMode: true, into: quill }),
    });

    let initialBlocks = null;
    let legacyDelta = null;
    try { initialBlocks = bodyBlocksInput.value ? JSON.parse(bodyBlocksInput.value) : null; } catch (e) { /* 無視 */ }
    try { legacyDelta = bodyDeltaInput.value ? JSON.parse(bodyDeltaInput.value) : null; } catch (e) { /* 無視 */ }
    blocks.load(initialBlocks, { delta: legacyDelta, html: bodyHtmlInput.value });

    document.getElementById('blog-add-block').addEventListener('click', (e) => {
        blocks.openInserter(e.currentTarget, blocks.blocks.length);
    });

    // ── 共通ツールバー (最後にフォーカスした列に適用) ─────────
    const toolbar = (() => {
        const el = document.getElementById('blog-toolbar');
        const linkDialog = document.getElementById('blog-link-dialog');
        const linkInput = linkDialog.querySelector('input');
        let linkTarget = null;

        function apply(btn) {
            const quill = blocks.active;
            if (!quill) return;
            const cmd = btn.dataset.cmd;
            const value = btn.dataset.value;
            const range = quill.getSelection(true);
            const f = range ? quill.getFormat(range) : {};
            switch (cmd) {
            case 'header': quill.formatLine(range.index, range.length, 'header', value ? Number(value) : false, 'user'); break;
            case 'align': quill.format('align', value || false, 'user'); break;
            case 'list': quill.format('list', f.list === value ? false : value, 'user'); break;
            case 'indent': {
                const cur = Number(f.indent || 0);
                const next = Math.max(0, Math.min(8, cur + (value === '+1' ? 1 : -1)));
                quill.format('indent', next || false, 'user');
                break;
            }
            case 'link': {
                linkTarget = { quill, range };
                linkInput.value = f.link || '';
                linkDialog.returnValue = '';
                linkDialog.showModal();
                linkInput.focus();
                break;
            }
            case 'image': pickImage(quill); break;
            case 'formula': math.open({ into: quill }); break;
            case 'markdown': markdownImport.open(); break;
            case 'clean': if (range) quill.removeFormat(range.index, range.length, 'user'); break;
            default: quill.format(cmd, !f[cmd], 'user'); // bold / italic / underline / strike / blockquote / code-block
            }
            refresh();
        }

        linkDialog.addEventListener('close', () => {
            if (!linkTarget || linkDialog.returnValue === 'cancel' || linkDialog.returnValue === '') return;
            const { quill, range } = linkTarget;
            const url = linkInput.value.trim();
            if (linkDialog.returnValue === 'remove' || !url) {
                quill.formatText(range.index, Math.max(range.length, 0), 'link', false, 'user');
            } else if (/^(https?:\/\/|mailto:|\/)/i.test(url)) {
                if (range.length) quill.formatText(range.index, range.length, 'link', url, 'user');
                else quill.insertText(range.index, url, { link: url }, 'user');
            } else {
                alert(t.invalidUrl);
            }
            linkTarget = null;
        });

        el.addEventListener('mousedown', (e) => { if (e.target.closest('button')) e.preventDefault(); }); // 選択を保つ
        el.addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-cmd]');
            if (btn) apply(btn);
        });

        function refresh() {
            const quill = blocks.active;
            const range = quill && quill.getSelection();
            const f = range ? quill.getFormat(range) : {};
            el.querySelectorAll('button[data-cmd]').forEach((btn) => {
                const { cmd, value } = btn.dataset;
                let on = false;
                if (cmd === 'header') on = String(f.header || '') === (value || '');
                else if (cmd === 'align') on = (f.align || '') === (value || '');
                else if (cmd === 'list') on = f.list === value;
                else if (['bold', 'italic', 'underline', 'strike', 'blockquote', 'code-block', 'link'].includes(cmd)) on = !!f[cmd];
                btn.classList.toggle('is-active', on);
            });
        }
        return { refresh };
    })();

    // ── タイトル: 自動リサイズ・Enter で本文へ ───────────
    // 日本語入力の変換を確定する Enter は無視する。Safari などでは確定の keydown が
    // isComposing = false で届くため、keyCode 229 (IME 処理中) も見る
    const isImeEnter = (e) => e.isComposing || e.keyCode === 229;
    const title = document.getElementById('id_title');
    const autosize = () => {
        title.style.height = 'auto';
        title.style.height = `${title.scrollHeight}px`;
    };
    title.addEventListener('input', autosize);
    title.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !isImeEnter(e)) {
            e.preventDefault();
            document.getElementById('id_subtitle').focus();
        }
    });
    document.getElementById('id_subtitle').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !isImeEnter(e)) {
            e.preventDefault();
            blocks.focusBlock(blocks.blocks[0]);
        }
    });
    autosize();

    // ── カバー画像 ─────────────────────────────────────
    const coverDrop = document.getElementById('blog-cover-drop');
    const coverInput = document.getElementById('id_cover_image');
    const coverPreview = document.getElementById('blog-cover-preview');
    const coverClear = document.getElementById('cover_image-clear_id');

    function setCoverFile(file) {
        if (!file || !file.type.startsWith('image/')) return;
        const dt = new DataTransfer();
        dt.items.add(file);
        coverInput.files = dt.files;
        coverClear.checked = false;
        coverPreview.src = URL.createObjectURL(file);
        coverDrop.classList.add('has-image');
        markDirty();
    }

    coverDrop.addEventListener('click', (e) => {
        if (e.target.closest('#blog-cover-remove')) return;
        coverInput.click();
    });
    coverDrop.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            coverInput.click();
        }
    });
    coverInput.addEventListener('change', () => setCoverFile(coverInput.files[0]));
    ['dragenter', 'dragover'].forEach((type) => coverDrop.addEventListener(type, (e) => {
        e.preventDefault();
        coverDrop.classList.add('is-dragover');
    }));
    ['dragleave', 'drop'].forEach((type) => coverDrop.addEventListener(type, (e) => {
        e.preventDefault();
        coverDrop.classList.remove('is-dragover');
    }));
    coverDrop.addEventListener('drop', (e) => setCoverFile(e.dataTransfer.files[0]));
    document.getElementById('blog-cover-remove').addEventListener('click', () => {
        coverInput.value = '';
        coverClear.checked = true;
        coverPreview.removeAttribute('src');
        coverDrop.classList.remove('has-image');
        markDirty();
    });

    // ── テンプレート・アクセントの即時反映 ──────────────
    form.addEventListener('change', (e) => {
        if (e.target.name === 'accent') {
            // 'none' はアクセントなし: 中立の白にして、派生色をモノトーンに切り替える
            const none = e.target.value === 'none';
            form.style.setProperty('--blog-accent', none ? '#f5f5f7' : e.target.value);
            form.classList.toggle('blog-accent-none', none);
        }
        if (e.target.name === 'display_width') {
            // 幅は CSS の @property 変数で滑らかに変わる (blog.css「表示幅」)
            form.dataset.width = e.target.value;
        }
        if (['accent', 'template', 'display_width'].includes(e.target.name)) markDirty();
    });
    // 幅のアニメーションが終わったら、画像の選択枠などを新しいレイアウトに合わせる
    form.addEventListener('transitionend', (e) => {
        if (e.target === form && e.propertyName === '--blog-canvas') window.dispatchEvent(new Event('resize'));
    });
    title.addEventListener('input', markDirty);
    document.getElementById('id_subtitle').addEventListener('input', markDirty);

    // ── 送信 ───────────────────────────────────────────
    form.addEventListener('submit', () => {
        const data = blocks.serialize();
        bodyBlocksInput.value = JSON.stringify(data);
        bodyHtmlInput.value = blocks.combinedHtml(data); // サーバー側でもブロックから作り直す
        bodyDeltaInput.value = '{}'; // 旧形式の本文データはブロックに移行済み
        dirty = false;
        statusEl.textContent = t.saving || '';
    });

    // ⌘/Ctrl + S で下書き保存 (公開済み記事は「更新」)
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            const btn = document.getElementById('blog-save-draft')
                || form.querySelector('button[name="action"][value="publish"]');
            form.requestSubmit(btn);
        }
    });

    window.addEventListener('beforeunload', (e) => {
        if (dirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
})();
