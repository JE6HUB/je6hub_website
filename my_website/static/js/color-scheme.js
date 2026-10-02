// サイト全体のカラースキーム。
// 色そのものは style.css の html[data-jh-scheme="..."] にあり、ここでは属性を付け替えるだけ。
// 設定ページで選ぶと、ページを読み込み直さずに滑らかに色を移し、アカウントに保存する。
(function () {
    'use strict';

    const STORAGE_KEY = 'jh-color-scheme'; // base.html の <head> のスクリプトと同じキー
    const root = document.documentElement;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function remember(scheme) {
        try { localStorage.setItem(STORAGE_KEY, scheme); } catch (e) { /* プライベートモードなど */ }
    }

    function syncThemeColor() {
        const meta = document.querySelector('meta[name="theme-color"]');
        const bg = getComputedStyle(root).getPropertyValue('--jh-bg').trim();
        if (meta && bg) meta.setAttribute('content', bg);
    }

    function setScheme(scheme) {
        root.setAttribute('data-jh-scheme', scheme);
        syncThemeColor();
    }

    // 切り替えの演出。対応ブラウザでは View Transitions でページ全体をクロスフェードし、
    // それ以外では色のプロパティだけを一時的にトランジションさせる。
    function applyScheme(scheme) {
        if (root.getAttribute('data-jh-scheme') === scheme) return Promise.resolve();
        remember(scheme);
        if (reduceMotion.matches) {
            setScheme(scheme);
            return Promise.resolve();
        }
        if (document.startViewTransition) {
            root.classList.add('jh-scheme-changing');
            const transition = document.startViewTransition(() => setScheme(scheme));
            return transition.finished.finally(() => root.classList.remove('jh-scheme-changing'));
        }
        root.classList.add('jh-scheme-fallback');
        // クラスを付けたスタイルを先に確定させてから色を変えないと、トランジションが効かない
        void root.offsetWidth;
        setScheme(scheme);
        return new Promise((resolve) => {
            setTimeout(() => { root.classList.remove('jh-scheme-fallback'); resolve(); }, 950);
        });
    }

    window.jhColorScheme = { apply: applyScheme };

    // ログイン中は、アカウントの設定をこの端末にも残す (ログアウト後も同じ色で見られる)
    if (root.hasAttribute('data-jh-scheme-account')) remember(root.getAttribute('data-jh-scheme'));
    syncThemeColor();

    // 設定ページ (プロフィール編集の「カラースキーム」)
    const form = document.getElementById('jh-scheme-form');
    if (!form) return;
    const status = form.querySelector('.jh-scheme-status');
    const submit = form.querySelector('[type="submit"]');
    if (submit) submit.hidden = true; // JavaScript が動くときは選んだ時点で保存する
    let saving = null;

    function showStatus(text, isError) {
        if (!status) return;
        status.textContent = text;
        status.classList.toggle('is-error', !!isError);
        status.classList.add('is-visible');
        clearTimeout(showStatus.timer);
        showStatus.timer = setTimeout(() => status.classList.remove('is-visible'), 2400);
    }

    form.addEventListener('change', (event) => {
        const input = event.target;
        if (!input.matches('input[name="color_scheme"]')) return;
        const scheme = input.value;
        applyScheme(scheme);

        if (saving) saving.abort();
        saving = new AbortController();
        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
            signal: saving.signal,
        })
            .then((response) => {
                if (!response.ok) throw new Error(String(response.status));
                showStatus(form.dataset.savedText);
            })
            .catch((error) => {
                if (error.name === 'AbortError') return;
                showStatus(form.dataset.errorText, true);
            });
    });
})();
