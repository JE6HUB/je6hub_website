/**
 * Blogs — HTML / CSS デモブロック (記事ページ)
 * タブ (プレビュー / HTML / CSS)、プレビュー幅の切り替え、コードのコピー、シンタックスハイライト。
 * これらはカードのホバーで現れる丸いメニューボタン (.bk-demo-fab) を押すと展開される。
 * プレビュー自体は sandbox 付き iframe (書き手のスクリプトは動かない) なので、ここでは外側の操作だけを扱う。
 *
 * いじれるデモ: 書き手が公開した CSS 変数をスライダー / 色で動かせる (blog-demo-kit.js)。
 * iframe 内ではページ側の小さなスクリプトだけが動き、postMessage で届いた変数を :root に設定する。
 * Before / After 比較: 2 枚の iframe を重ね、境界をドラッグして見比べる。
 */
(() => {
    const t = window.BLOG_DEMO_I18N || { copy: 'Copy', copied: 'Copied' };

    document.querySelectorAll('[data-demo]').forEach((demo) => {
        const tabs = demo.querySelectorAll('[data-tab]');
        const panels = demo.querySelectorAll('[data-panel]');
        const frames = [...demo.querySelectorAll('.bk-demo-frame')];
        const kit = window.BlogDemoKit;
        const copyBtn = demo.querySelector('[data-copy]');
        const copyLabel = demo.querySelector('[data-copy-label]');
        const code = (lang) => demo.querySelector(`[data-panel="${lang}"] code`).textContent;
        let active = 'preview';

        // メニューの開閉 (外側クリック・Esc で閉じる)
        const menu = demo.querySelector('.bk-demo-menu');
        const fab = demo.querySelector('.bk-demo-fab');
        const setOpen = (open) => {
            menu.classList.toggle('is-open', open);
            fab.setAttribute('aria-expanded', String(open));
        };
        fab.addEventListener('click', () => setOpen(!menu.classList.contains('is-open')));
        document.addEventListener('pointerdown', (e) => { if (!menu.contains(e.target)) setOpen(false); });
        demo.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && menu.classList.contains('is-open')) { setOpen(false); fab.focus(); }
        });

        tabs.forEach((tab) => tab.addEventListener('click', () => {
            active = tab.dataset.tab;
            tabs.forEach((x) => x.setAttribute('aria-selected', String(x === tab)));
            panels.forEach((p) => { p.hidden = p.dataset.panel !== active; });
            demo.querySelector('[data-tool="viewport"]').hidden = active !== 'preview';
            const el = demo.querySelector(`[data-panel="${active}"] code`);
            if (el && window.hljs && !el.dataset.highlighted) window.hljs.highlightElement(el);
        }));

        // プレビューの幅 (全幅 / タブレット / スマホ) — レスポンシブの確認用
        demo.querySelectorAll('[data-tool="viewport"] button').forEach((btn, _, all) => btn.addEventListener('click', () => {
            all.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
            frames.forEach((f) => { f.style.width = btn.dataset.value === 'full' ? '100%' : `${btn.dataset.value}px`; });
        }));

        const stage = demo.querySelector('[data-compare]');
        if (stage && kit) kit.bindCompare(stage);

        // コントロール: 変数は iframe ごとに postMessage で届ける (iframe は別オリジン扱いなので '*')
        const bar = demo.querySelector('[data-controls]');
        let vars = () => ({});
        if (bar && kit) {
            const send = (v) => frames.forEach((f) => f.contentWindow && f.contentWindow.postMessage({ t: 'bk-vars', v }, '*'));
            vars = kit.bindControls(bar, send);
            // 遅延読み込みや再読み込みのあとも、動かした値を保つ
            frames.forEach((f) => f.addEventListener('load', () => { if (bar.classList.contains('is-touched')) send(vars()); }));
        }

        // コピー: コードタブではそのコード、プレビューでは HTML と CSS をまとめて
        copyBtn.addEventListener('click', async () => {
            // プレビューでは、動かしたコントロールの値も :root として含める
            const tuned = bar && bar.classList.contains('is-touched')
                ? `:root {\n${Object.entries(vars()).map(([k, v]) => `  ${k}: ${v};`).join('\n')}\n}\n\n`
                : '';
            const text = active === 'preview'
                ? `<style>\n${code('css')}\n\n${tuned}</style>\n\n${code('html')}`
                : code(active);
            try {
                await navigator.clipboard.writeText(text);
            } catch (e) {
                const area = document.createElement('textarea');
                area.value = text;
                document.body.append(area);
                area.select();
                document.execCommand('copy');
                area.remove();
            }
            copyLabel.textContent = t.copied;
            copyBtn.classList.add('is-done');
            setTimeout(() => { copyLabel.textContent = t.copy; copyBtn.classList.remove('is-done'); }, 1600);
        });
    });
})();
