/**
 * Blogs エディタ — Markdown
 * 1) 入力中のショートカット (すべて keyboard バインディングで同期的に処理)
 *    行頭:  "# " 見出し / "## " 小見出し / "> " 引用 / "- " "1. " リスト (Quill 標準)
 *    Enter: "---" 区切り線 / "```" コード / "$$…$$" ブロック数式 / "$$" 数式ダイアログ
 *    行内:  **太字** *斜体* ~~取り消し~~ `コード` [リンク](URL) $数式$
 * 2) Markdown 文書の読み込み (marked で HTML に変換して挿入。数式も対応)
 */
window.BlogEditorMarkdown = (() => {
    const SAFE_URL = /^(https?:\/\/|mailto:|\/)/i;

    /** Quill 生成時の keyboard.bindings に渡す (既定の Enter 処理より先に評価される) */
    function bindings(Quill, getMath) {
        const USER = Quill.sources.USER;
        return {
            ...inlineBindings(Quill),
            // 空の引用行で Enter → 引用を抜ける (リストと同じ挙動)
            'md-quote-exit': {
                key: 'Enter',
                collapsed: true,
                format: ['blockquote'],
                empty: true,
                handler(range) {
                    this.quill.formatLine(range.index, 1, 'blockquote', false, USER);
                    return false;
                },
            },
            'md-block-prefix': {
                key: ' ',
                collapsed: true,
                format: { 'code-block': false },
                prefix: /^(#{1,3}|>)$/,
                handler(range, context) {
                    const p = context.prefix;
                    const start = range.index - p.length;
                    const fmt = p === '>' ? { blockquote: true } : { header: p.length === 1 ? 2 : 3 };
                    this.quill.deleteText(start, p.length, USER);
                    this.quill.formatLine(start, 1, fmt, USER);
                    this.quill.setSelection(start, Quill.sources.SILENT);
                    return false;
                },
            },
            'md-enter': {
                key: 'Enter',
                collapsed: true,
                format: { 'code-block': false },
                prefix: /^(---|\*\*\*|```[\w-]*|\$\$|\$\$.+\$\$)$/,
                suffix: /^$/,
                handler(range, context) {
                    const p = context.prefix;
                    const start = range.index - p.length;
                    const q = this.quill;
                    q.deleteText(start, p.length, USER);
                    if (p === '---' || p === '***') {
                        q.insertEmbed(start, 'divider', true, USER);
                        q.setSelection(start + 1, Quill.sources.SILENT);
                    } else if (p.startsWith('```')) {
                        q.formatLine(start, 1, { 'code-block': true }, USER);
                    } else if (p === '$$') {
                        q.setSelection(start, Quill.sources.SILENT);
                        getMath().open({ displayMode: true });
                    } else {
                        q.insertEmbed(start, 'math-display', p.slice(2, -2).trim(), USER);
                        q.setSelection(start + 1, Quill.sources.SILENT);
                    }
                    return false;
                },
            },
        };
    }

    // 行内パターン: 閉じる文字を入力した瞬間 (挿入前) に、直前のテキスト + その文字で判定する。
    // 挿入後に非同期で置き換えると、速く入力したときに位置がずれて本文が壊れるため。
    const INLINE_RULES = [
        { re: /\*\*([^*\n]+?)\*\*$/, fmt: { bold: true } },
        { re: /~~([^~\n]+?)~~$/, fmt: { strike: true } },
        { re: /`([^`\n]+?)`$/, fmt: { code: true } },
        { re: /(?:^|[^*\w])(\*([^*\s][^*\n]*?)\*)$/, fmt: { italic: true }, group: 1, inner: 2 },
        { re: /(?:^|[^$\\\w])(\$([^\s$](?:[^$\n]*?[^\s$])?)\$)$/, embed: 'formula', group: 1, inner: 2 },
        { re: /\[([^\]\n]+)\]\(([^)\s]+)\)$/, link: true },
    ];

    function inlineBindings(Quill) {
        const USER = Quill.sources.USER;
        const binding = (key) => ({
            key,
            shiftKey: null, // * や $ は Shift 付きで入力されるため修飾キーを問わない
            collapsed: true,
            format: { 'code-block': false, code: false },
            handler(range, context) {
                const text = context.prefix + key;
                for (const rule of INLINE_RULES) {
                    const m = text.match(rule.re);
                    if (!m) continue;
                    const token = rule.group ? m[rule.group] : m[0];
                    // 閉じる文字はまだ挿入されていないので、その 1 文字分を除いた範囲を置き換える
                    const start = range.index - context.prefix.length + (m.index + m[0].length - token.length);
                    const length = token.length - 1;
                    if (apply(this.quill, rule, m, start, length)) return false;
                }
                return true; // 該当なし: 通常どおり文字を入力
            },
        });
        const bindings = {};
        ['*', '~', '`', '$', ')'].forEach((k, i) => { bindings[`md-inline-${i}`] = binding(k); });

        function apply(quill, rule, m, start, length) {
            if (rule.link) {
                const [, label, url] = m;
                if (!SAFE_URL.test(url)) return false;
                quill.deleteText(start, length, USER);
                quill.insertText(start, label, { link: url }, USER);
                quill.setSelection(start + label.length, Quill.sources.SILENT);
                quill.format('link', false, USER);
                return true;
            }
            const inner = m[rule.inner || 1];
            quill.deleteText(start, length, USER);
            if (rule.embed) {
                quill.insertEmbed(start, rule.embed, inner, USER);
                quill.setSelection(start + 1, Quill.sources.SILENT);
                return true;
            }
            quill.insertText(start, inner, rule.fmt, USER);
            quill.setSelection(start + inner.length, Quill.sources.SILENT);
            // 続けて入力する文字には書式を引き継がない
            Object.keys(rule.fmt).forEach((k) => quill.format(k, false, USER));
            return true;
        }
        return bindings;
    }

    /** Markdown → HTML (見出しは本文の見出しレベルに合わせ、数式は数式ブロットの形で出力) */
    function toHtml(markdown) {
        const esc = window.BlogEditorMath.escapeHtml;
        const md = new window.marked.Marked({
            gfm: true,
            breaks: false,
            extensions: [
                {
                    name: 'mathBlock',
                    level: 'block',
                    start(src) { const i = src.indexOf('$$'); return i < 0 ? undefined : i; },
                    tokenizer(src) {
                        const m = /^\$\$\s*([\s\S]+?)\s*\$\$[^\S\n]*(?:\n+|$)/.exec(src);
                        if (m) return { type: 'mathBlock', raw: m[0], text: m[1].trim() };
                        return undefined;
                    },
                    renderer(tok) { return `<div class="ql-math-display" data-value="${esc(tok.text)}"></div>`; },
                },
                {
                    name: 'mathInline',
                    level: 'inline',
                    start(src) { const i = src.indexOf('$'); return i < 0 ? undefined : i; },
                    tokenizer(src) {
                        const m = /^\$([^\s$](?:[^$\n]*?[^\s$])?)\$/.exec(src);
                        if (m) return { type: 'mathInline', raw: m[0], text: m[1] };
                        return undefined;
                    },
                    renderer(tok) { return `<span class="ql-formula" data-value="${esc(tok.text)}"></span>`; },
                },
            ],
            renderer: {
                heading(text, level) {
                    const l = Math.min(level + 1, 3); // # → 見出し(h2), ## 以降 → 小見出し(h3)
                    return `<h${l}>${text}</h${l}>\n`;
                },
            },
        });
        return md.parse(markdown);
    }

    /** Markdown 読み込みダイアログ。挿入先は getQuill() (最後にフォーカスした列) */
    function setupImport(getQuill, Quill) {
        const dialog = document.getElementById('blog-md-dialog');
        const input = dialog.querySelector('textarea');
        let quill = null;
        let insertAt = 0;

        function open() {
            quill = getQuill();
            if (!quill) return;
            insertAt = (quill.getSelection(true) || { index: quill.getLength() }).index;
            input.value = '';
            dialog.returnValue = '';
            dialog.showModal();
            input.focus();
        }
        dialog.addEventListener('close', () => {
            if (dialog.returnValue !== 'insert' || !quill || !input.value.trim()) return;
            quill.clipboard.dangerouslyPasteHTML(insertAt, toHtml(input.value), Quill.sources.USER);
        });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                dialog.close('insert');
            }
        });
        return { open };
    }

    return { bindings, setupImport, toHtml };
})();
