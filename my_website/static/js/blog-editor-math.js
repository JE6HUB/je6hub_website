/**
 * Blogs エディタ — 数式 (LaTeX / KaTeX)
 * - インライン数式: Quill 標準の formula ブロット (html 出力だけ安全な形に差し替え)
 * - ブロック数式:   独自の math-display ブロット
 * 保存される HTML は <span class="ql-formula" data-value="LaTeX"> / <div class="ql-math-display" ...>
 * で、記事ページ側で KaTeX により描画する。
 */
window.BlogEditorMath = (() => {
    const escapeHtml = (s) => String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

    function renderInto(el, latex, displayMode) {
        try {
            window.katex.render(latex, el, { displayMode, throwOnError: false, trust: false });
        } catch (e) {
            el.textContent = latex;
        }
    }

    /** Quill に数式ブロットを登録する (Quill 生成前に呼ぶ) */
    function register(Quill) {
        const Formula = Quill.import('formats/formula');
        class InlineFormula extends Formula {
            html() {
                const { formula } = this.value();
                return `<span class="ql-formula" data-value="${escapeHtml(formula)}">${escapeHtml(formula)}</span>`;
            }
        }
        Quill.register(InlineFormula, true);

        const BlockEmbed = Quill.import('blots/block/embed');
        class MathDisplay extends BlockEmbed {
            static create(value) {
                const node = super.create();
                node.setAttribute('data-value', value);
                node.setAttribute('contenteditable', 'false');
                renderInto(node, value, true);
                return node;
            }
            static value(node) {
                return node.getAttribute('data-value');
            }
            html() {
                const latex = this.value()['math-display'];
                return `<div class="ql-math-display" data-value="${escapeHtml(latex)}">${escapeHtml(latex)}</div>`;
            }
        }
        MathDisplay.blotName = 'math-display';
        MathDisplay.tagName = 'DIV';
        MathDisplay.className = 'ql-math-display';
        Quill.register(MathDisplay, true);
    }

    /**
     * 数式ダイアログ (新規挿入・既存の編集)。ブロックエディタでは列ごとに Quill があるため、
     * 挿入先は getQuill() (最後にフォーカスした列) で決める。
     */
    function setup(getQuill, Quill) {
        const dialog = document.getElementById('blog-math-dialog');
        const input = dialog.querySelector('textarea');
        const preview = dialog.querySelector('.blog-math-preview');
        const modeInputs = dialog.querySelectorAll('input[name="math-mode"]');
        let target = null; // 編集中の既存数式 { index }
        let insertAt = 0;
        let quill = null;

        const mode = () => dialog.querySelector('input[name="math-mode"]:checked').value;
        const updatePreview = () => {
            const latex = input.value.trim();
            if (!latex) { preview.textContent = ''; return; }
            renderInto(preview, latex, mode() === 'display');
        };
        input.addEventListener('input', updatePreview);
        modeInputs.forEach((r) => r.addEventListener('change', updatePreview));

        function open({ latex = '', displayMode = false, edit = null, into = null } = {}) {
            quill = into || getQuill();
            if (!quill) return;
            target = edit;
            insertAt = (quill.getSelection(true) || { index: quill.getLength() }).index;
            input.value = latex;
            modeInputs.forEach((r) => { r.checked = (r.value === 'display') === displayMode; });
            dialog.querySelector('[data-action="insert"]').textContent =
                edit ? dialog.dataset.labelUpdate : dialog.dataset.labelInsert;
            updatePreview();
            dialog.returnValue = ''; // Esc で閉じたとき前回の「挿入」が残らないように
            dialog.showModal();
            input.focus();
        }

        dialog.addEventListener('close', () => {
            if (dialog.returnValue !== 'insert' || !quill) return;
            const latex = input.value.trim();
            if (!latex) return;
            const blot = mode() === 'display' ? 'math-display' : 'formula';
            let index = insertAt;
            if (target) {
                index = target.index;
                quill.deleteText(index, 1, Quill.sources.USER);
            }
            quill.insertEmbed(index, blot, latex, Quill.sources.USER);
            quill.setSelection(index + 1, Quill.sources.SILENT);
        });
        // ⌘/Ctrl + Enter で確定
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                dialog.close('insert');
            }
        });

        /** 既存の数式をクリックすると編集 (Quill ごとに登録) */
        function attach(q) {
            q.root.addEventListener('click', (e) => {
                const el = e.target.closest('.ql-formula, .ql-math-display');
                if (!el || !q.root.contains(el)) return;
                const blot = Quill.find(el);
                if (!blot) return;
                open({
                    latex: el.getAttribute('data-value') || '',
                    displayMode: el.classList.contains('ql-math-display'),
                    edit: { index: q.getIndex(blot) },
                    into: q,
                });
            });
        }

        return { open, attach };
    }

    /** 記事ページなど、保存済み HTML 内の数式を描画する */
    function renderAll(root) {
        if (!window.katex) return;
        root.querySelectorAll('.ql-formula, .ql-math-display').forEach((el) => {
            renderInto(el, el.getAttribute('data-value') || el.textContent, el.classList.contains('ql-math-display'));
        });
    }

    return { register, setup, renderAll, escapeHtml };
})();
