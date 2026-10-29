/**
 * Blogs — ブロックエディタ: AI の回答などを貼り付けたら、見出し・段落・リストごとのブロックに分ける
 * Claude / ChatGPT / Gemini などの回答は、HTML (画面から選んでコピー) か Markdown (コピーボタン) で
 * クリップボードに入る。どちらも同じ形の「区切り」の並びにしてから、ブロックとして差し込む。
 *
 * - 見出し → 見出しのテキストブロック (いちばん大きい見出しが「見出し」、それより下は「小見出し」)
 * - 続けて並ぶ段落 → 1 つのテキストブロック
 * - リスト・コード・表 → それぞれ 1 つのテキストブロック (表は 1 行ずつ「 | 」区切りの段落)
 * - 引用 → 引用ブロック / 区切り線 → 区切り線ブロック
 * - 数式 (KaTeX の表示や $…$ / \( … \)) → 数式
 * 分けられるのは 1 列のテキストブロックの中だけ。列・コールアウト・引用の中では、整えた中身をその場に貼る。
 * ⌘/Ctrl + Shift + V (書式なしで貼り付け) のときは分けない。
 */
(() => {
    const { BlockEditor } = window.BlogBlocks;
    const SAFE_URL = /^(https?:\/\/|mailto:|\/)/i;
    const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

    // 区切りになる要素 / 行内の要素。どちらでもない要素 (div やサイト独自のタグ) は入れ物として中を見る
    const BLOCK_TAGS = new Set(['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'UL', 'OL', 'PRE', 'BLOCKQUOTE', 'TABLE', 'HR', 'FIGURE']);
    const INLINE_TAGS = new Set(['A', 'B', 'STRONG', 'I', 'EM', 'U', 'S', 'DEL', 'STRIKE', 'CODE', 'KBD', 'SPAN', 'SUB', 'SUP',
        'MARK', 'SMALL', 'BR', 'IMG', 'FONT', 'ABBR', 'CITE', 'Q', 'TIME']);
    // コピーボタン・アイコンなど、本文ではないもの
    const DROP = 'button, svg, style, script, noscript, template, meta, link, title, input, select, textarea, iframe, canvas, video, audio, object, [aria-hidden="true"]';

    // ⌘/Ctrl + Shift + V を押した直後の貼り付けは分けない (paste イベントからは Shift が分からないため)
    let plainPaste = 0;
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'v') plainPaste = Date.now();
    }, true);

    // ── クリップボード → 文書 ────────────────────────────
    /** Markdown らしい書き方 (見出し・コード・表・区切り線・2 行以上のリスト・引用) があるか */
    function looksLikeMarkdown(text) {
        const lines = text.split(/\r?\n/);
        if (lines.filter((l) => l.trim()).length < 2) return false;
        const count = (re) => lines.filter((l) => re.test(l)).length;
        return count(/^#{1,6}\s+\S/) > 0
            || count(/^\s*(```|~~~)/) > 0
            || count(/^\s*\|.*\|\s*$/) > 1
            || count(/^\s*(-{3,}|\*{3,}|_{3,})\s*$/) > 0
            || count(/^\s*([-*+]|\d+[.)])\s+\S/) > 1
            || count(/^>\s?/) > 0;
    }

    /** ChatGPT の \[ … \] / \( … \) を、エディタの Markdown の $$ … $$ / $ … $ にする (コードの中は除く) */
    function normalizeMath(md) {
        return md.split(/(^\s*(?:```|~~~)[\s\S]*?^\s*(?:```|~~~)\s*$)/m).map((part, i) => (i % 2 ? part : part
            .replace(/\\\[([\s\S]+?)\\\]/g, (_, tex) => `\n$$${tex.trim()}$$\n`)
            .replace(/\\\(([\s\S]+?)\\\)/g, (_, tex) => `$${tex.trim()}$`))).join('');
    }

    /** 分けて貼るべき文書 (Document) を返す。普通の貼り付けでよいときは null */
    function readClipboard(data) {
        if (!data || Date.now() - plainPaste < 1000) return null;
        if (data.files && data.files.length) return null; // 画像ファイルは Quill のアップロードに任せる
        const html = data.getData('text/html');
        const text = data.getData('text/plain');
        if (html) {
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const structured = doc.body.querySelector('h1, h2, h3, h4, h5, h6, ul, ol, pre, blockquote, table, hr')
                || doc.body.querySelectorAll('p').length > 1;
            if (structured) return doc;
        }
        // コピーボタンの Markdown や、エディタ (VS Code など) からの Markdown
        if (text && looksLikeMarkdown(text)) {
            const out = window.BlogEditorMarkdown.toHtml(normalizeMath(text), { headings: 'raw' });
            return new DOMParser().parseFromString(out, 'text/html');
        }
        return null;
    }

    /** 数式 (KaTeX) をエディタの数式にし、ボタンや装飾 (style / class) を取り除く */
    function clean(root) {
        const doc = root.ownerDocument;
        const tex = (el) => {
            const a = el.querySelector('annotation[encoding="application/x-tex"]');
            return a ? a.textContent.trim() : '';
        };
        root.querySelectorAll('.katex-display, .katex').forEach((el) => {
            if (!el.isConnected || !root.contains(el)) return;
            const value = tex(el);
            if (!value) return;
            const display = el.classList.contains('katex-display');
            const m = doc.createElement(display ? 'div' : 'span');
            m.className = display ? 'ql-math-display' : 'ql-formula';
            m.dataset.value = value;
            el.replaceWith(m);
        });
        root.querySelectorAll(DROP).forEach((el) => el.remove());
        root.querySelectorAll('*').forEach((el) => {
            const keep = {};
            if (el.tagName === 'A' && SAFE_URL.test(el.getAttribute('href') || '')) keep.href = el.getAttribute('href');
            if (el.tagName === 'IMG') {
                if (!/^https?:\/\//i.test(el.getAttribute('src') || '')) { el.remove(); return; }
                keep.src = el.getAttribute('src');
                if (el.getAttribute('alt')) keep.alt = el.getAttribute('alt');
            }
            const math = el.classList.contains('ql-formula') || el.classList.contains('ql-math-display');
            if (math) Object.assign(keep, { class: el.className, 'data-value': el.dataset.value });
            Array.from(el.attributes).forEach((a) => { if (!(a.name in keep)) el.removeAttribute(a.name); });
        });
        // リスト項目の中の段落は、行として扱う (Quill で余分な空行ができないように)
        root.querySelectorAll('li > p').forEach((p) => {
            if (p.nextElementSibling && p.nextElementSibling.tagName === 'P') p.after(doc.createElement('br'));
            p.replaceWith(...p.childNodes);
        });
    }

    const hasContent = (el) => el.textContent.trim() || el.querySelector('img, .ql-formula, .ql-math-display');
    const hasBlock = (el) => Array.from(el.querySelectorAll('*')).some((c) => BLOCK_TAGS.has(c.tagName) || c.classList.contains('ql-math-display'));

    /** 文書の中身を、区切り { kind, el } の並びにする */
    function segments(root) {
        const out = [];
        const doc = root.ownerDocument;
        let inline = null;
        const flush = () => {
            if (inline && hasContent(inline)) out.push({ kind: 'p', el: inline });
            inline = null;
        };
        const walk = (parent) => {
            Array.from(parent.childNodes).forEach((node) => {
                if (node.nodeType === Node.TEXT_NODE) {
                    if (!node.textContent.trim() && !inline) return;
                    (inline || (inline = doc.createElement('p'))).append(node.cloneNode());
                    return;
                }
                if (node.nodeType !== Node.ELEMENT_NODE) return;
                const tag = node.tagName;
                if (node.classList.contains('ql-math-display')) { flush(); out.push({ kind: 'p', el: node }); return; }
                if (BLOCK_TAGS.has(tag)) {
                    flush();
                    if (tag === 'HR') out.push({ kind: 'divider' });
                    else if (/^H\d$/.test(tag)) { if (hasContent(node)) out.push({ kind: 'heading', level: Number(tag[1]), el: node }); }
                    else if (tag === 'FIGURE') walk(node);
                    else if (hasContent(node)) out.push({ kind: { P: 'p', UL: 'list', OL: 'list', PRE: 'code', BLOCKQUOTE: 'quote', TABLE: 'table' }[tag], el: node });
                    return;
                }
                if (INLINE_TAGS.has(tag) && !hasBlock(node)) {
                    (inline || (inline = doc.createElement('p'))).append(node.cloneNode(true));
                    return;
                }
                // 入れ物。コードの見出し (言語名・コピー) だけを添えたコードなら、コードだけを取り出す
                const pres = node.querySelectorAll('pre');
                if (pres.length === 1 && node.textContent.length - pres[0].textContent.length <= 30) {
                    flush();
                    out.push({ kind: 'code', el: pres[0] });
                    return;
                }
                if (hasBlock(node)) { flush(); walk(node); flush(); return; }
                // 中に区切りがない div は 1 行 (1 段落) として扱う
                flush();
                if (hasContent(node)) {
                    const p = doc.createElement('p');
                    p.append(...Array.from(node.childNodes).map((c) => c.cloneNode(true)));
                    out.push({ kind: 'p', el: p });
                }
            });
        };
        walk(root);
        flush();
        return out;
    }

    /** 表は、1 行ずつ「 | 」でつないだ段落にする (見出しの行は太字) */
    function tableHtml(table) {
        return Array.from(table.querySelectorAll('tr')).map((tr) => {
            const cells = Array.from(tr.children).filter((c) => c.tagName === 'TD' || c.tagName === 'TH');
            const head = cells.length && cells.every((c) => c.tagName === 'TH');
            const html = cells.map((c) => c.innerHTML.trim()).join(' | ');
            return html.replace(/\|/g, '').trim() ? `<p>${head ? `<strong>${html}</strong>` : html}</p>` : '';
        }).join('');
    }

    const codeHtml = (pre) => `<pre>${esc(pre.textContent.replace(/\n+$/, ''))}</pre>`;

    /** いちばん大きい見出しを「見出し (h2)」、それより下を「小見出し (h3)」にする */
    function headingLevels(segs) {
        const top = Math.min(...segs.filter((s) => s.kind === 'heading').map((s) => s.level));
        return (level) => (level === top ? 2 : 3);
    }

    /** 区切り → ブロックのデータ (insertBlock に渡す形) */
    function toBlocks(segs, style) {
        const levelOf = headingLevels(segs);
        const text = (html) => ({ type: 'text', style, cells: [{ html }] });
        const out = [];
        let para = null;
        segs.forEach((s) => {
            if (s.kind === 'p') {
                const html = s.el.tagName === 'P' ? `<p>${s.el.innerHTML}</p>` : s.el.outerHTML;
                if (para) para.cells[0].html += html;
                else out.push(para = text(html));
                return;
            }
            para = null;
            if (s.kind === 'divider') out.push({ type: 'divider' });
            else if (s.kind === 'heading') {
                const l = levelOf(s.level);
                out.push(text(`<h${l}>${s.el.innerHTML}</h${l}>`));
            } else if (s.kind === 'list') out.push(text(s.el.outerHTML));
            else if (s.kind === 'code') out.push(text(codeHtml(s.el)));
            else if (s.kind === 'table') out.push(text(tableHtml(s.el)));
            else if (s.kind === 'quote') {
                // 引用の中は段落・リストとしてそのまま (入れ子の引用は平らにする)
                const inner = segments(s.el).map((q) => (q.kind === 'divider' ? '' : blockHtml(q, levelOf))).join('');
                out.push({ type: 'quote', style, cells: [{ html: inner }] });
            }
        });
        return out.filter((b) => b.type === 'divider' || b.cells[0].html);
    }

    /** 1 つの列にまとめて貼るときの HTML */
    function blockHtml(s, levelOf) {
        if (s.kind === 'divider') return '<hr>';
        if (s.kind === 'heading') { const l = levelOf(s.level); return `<h${l}>${s.el.innerHTML}</h${l}>`; }
        if (s.kind === 'code') return codeHtml(s.el);
        if (s.kind === 'table') return tableHtml(s.el);
        if (s.kind === 'quote') return segments(s.el).map((q) => blockHtml(q, levelOf)).join('');
        if (s.kind === 'p' && s.el.tagName === 'P') return `<p>${s.el.innerHTML}</p>`;
        return s.el.outerHTML;
    }

    // ── エディタへの差し込み ─────────────────────────────
    Object.assign(BlockEditor.prototype, {
        /** 列の Quill の paste (キャプチャ) から呼ばれる。分けて貼ったら Quill の貼り付けを止める */
        pasteBlocks(e, block, quill) {
            const range = quill.getSelection(true);
            if (!range || quill.getFormat(range)['code-block']) return;
            const doc = readClipboard(e.clipboardData);
            if (!doc) return;
            clean(doc.body);
            const segs = segments(doc.body);
            // 段落 1 つだけなら、いつもの貼り付けで十分
            if (!segs.length || (segs.length === 1 && segs[0].kind === 'p')) return;
            e.preventDefault();
            e.stopPropagation();

            const { USER, SILENT } = this.Quill.sources;
            if (block.type !== 'text' || block.columns !== 1) {
                quill.deleteText(range.index, range.length, USER);
                const levelOf = headingLevels(segs);
                quill.clipboard.dangerouslyPasteHTML(range.index, segs.map((s) => blockHtml(s, levelOf)).join(''), USER);
                return;
            }

            // カーソルの前後で元のブロックを分け、そのあいだに貼った中身のブロックを並べる
            const before = quill.getContents(0, range.index);
            const after = quill.getContents(range.index + range.length);
            const hasText = (d) => d.ops.some((op) => typeof op.insert !== 'string' || op.insert.trim());
            const style = { ...block.style };
            const keep = hasText(before);
            let index = this.blocks.indexOf(block);
            if (keep) quill.setContents(before, SILENT);
            let last = null;
            toBlocks(segs, style).forEach((data) => { last = this.insertBlock(data, ++index, { silent: true }); });
            if (hasText(after)) {
                const rest = this.insertBlock({ type: 'text', style, cells: [{ delta: after }] }, ++index, { silent: true });
                if (!last || !last.cells.length) last = rest;
            } else if (!last || !last.cells.length) {
                // 区切り線で終わるときは、続きを書けるよう空のテキストブロックを置く
                last = this.insertBlock({ type: 'text', style }, ++index, { silent: true });
            }
            if (!keep) {
                this.blocks.splice(this.blocks.indexOf(block), 1);
                block.el.remove();
                if (this.active === quill) this.active = null;
            }
            this.focusBlock(last, true);
            last.el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            this.changed();
        },
    });
})();
