// ヘッダーの通知 (ベルのアイコン)。押すとドロップダウンを開いて最新の通知を読み込み、すべて既読にする。
// 開いていない間は、ページが表示されているときだけ軽く未読数を問い合わせてバッジを更新する (WebSocket は使わない)。
(() => {
    const script = document.currentScript;
    const endpoint = script && script.dataset.url;
    const panel = document.getElementById('jh-notif-panel');
    const toggles = [...document.querySelectorAll('[data-notif-toggle]')];
    if (!endpoint || !panel || !toggles.length) return;

    const list = panel.querySelector('[data-notif-list]');
    const readForm = panel.querySelector('[data-notif-read]');
    const POLL_MS = 60000;
    let opener = null;
    let lastPoll = Date.now();

    const label = (n) => (n > 0
        ? script.dataset.labelUnread.replace('%(count)s', n)
        : script.dataset.label);

    const setUnread = (n) => {
        toggles.forEach((btn) => {
            const badge = btn.querySelector('[data-notif-badge]');
            if (badge) {
                badge.hidden = !(n > 0);
                badge.textContent = n > 99 ? '99+' : String(n);
            }
            btn.setAttribute('aria-label', label(n));
        });
    };

    const fetchJSON = async (url, init) => {
        const res = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' }, ...init });
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
    };

    // ヘッダーの下、ボタンの右端にそろえて出す (スマートフォンは CSS で画面幅いっぱい)
    const position = () => {
        if (!opener) return;
        const rect = opener.getBoundingClientRect();
        panel.style.setProperty('--jh-notif-top', `${Math.round(rect.bottom + 8)}px`);
        panel.style.setProperty('--jh-notif-right', `${Math.max(8, Math.round(window.innerWidth - rect.right - 8))}px`);
    };

    const close = (focusBack = false) => {
        if (panel.hidden) return;
        panel.hidden = true;
        toggles.forEach((btn) => btn.setAttribute('aria-expanded', 'false'));
        document.documentElement.classList.remove('jh-notif-open');
        if (focusBack && opener) opener.focus();
        opener = null;
    };

    const open = async (btn) => {
        // スマートフォンの全画面メニューが開いていれば閉じてから出す
        const menuBtn = document.getElementById('jh-menu-btn');
        if (menuBtn && menuBtn.getAttribute('aria-expanded') === 'true') menuBtn.click();
        opener = btn;
        position();
        panel.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        document.documentElement.classList.add('jh-notif-open');
        try {
            const data = await fetchJSON(`${endpoint}?menu=1`);
            list.innerHTML = data.html;  // サーバーでエスケープ済みのテンプレート
            if (data.unread > 0) {
                // 開いたら既読にする。今回の表示では未読の印を残し、どれが新しいか分かるようにする
                setUnread(0);
                fetchJSON(endpoint, { method: 'POST', body: new FormData(readForm) }).catch(() => {});
            }
        } catch (err) {
            const li = document.createElement('li');
            li.className = 'jh-notif-empty';
            li.textContent = script.dataset.error;
            list.replaceChildren(li);
        }
    };

    toggles.forEach((btn) => btn.addEventListener('click', (e) => {
        e.preventDefault();
        if (!panel.hidden && opener === btn) close();
        else { close(); open(btn); }
    }));

    document.addEventListener('click', (e) => {
        if (panel.hidden || panel.contains(e.target) || e.target.closest('[data-notif-toggle]')) return;
        close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !panel.hidden) close(true);
    });
    window.addEventListener('resize', position);

    const poll = async () => {
        if (document.hidden || !panel.hidden) return;
        lastPoll = Date.now();
        try {
            const data = await fetchJSON(endpoint);
            setUnread(data.unread);
        } catch (err) {
            // 一時的な失敗は次の問い合わせに任せる
        }
    };
    setInterval(poll, POLL_MS);
    // タブに戻ってきたときは、しばらく経っていればすぐに確かめる
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && Date.now() - lastPoll > POLL_MS / 2) poll();
    });
})();
