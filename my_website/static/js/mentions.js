// @ユーザー名 の入力補完。[data-mention-input] の入力欄で「@」に続けて入力すると、候補のユーザーを出す。
// ↑↓ で選び、Enter / Tab で確定、Esc で閉じる。候補は /api/mentions/?q= から取得する。
(() => {
    const script = document.currentScript;
    const endpoint = script && script.dataset.url;
    if (!endpoint) return;

    // 日本語のユーザー名もあるため、@ のあとは空白と記号以外の文字を候補の検索に使う
    const TOKEN_RE = /(?:^|[^\p{L}\p{N}_@])@([\p{L}\p{N}_.+-]{0,30})$/u;
    let menu = null;
    let field = null;
    let items = [];
    let active = 0;
    let range = null;   // 置き換える範囲 [start, end]
    let timer = null;
    let seq = 0;

    const close = () => {
        if (menu) menu.hidden = true;
        items = [];
        range = null;
        if (field) field.removeAttribute('aria-activedescendant');
    };

    const ensureMenu = () => {
        if (menu) return menu;
        menu = document.createElement('ul');
        menu.className = 'jh-mention-menu';
        menu.id = 'jh-mention-menu';
        menu.setAttribute('role', 'listbox');
        menu.hidden = true;
        // mousedown で入力欄のフォーカスが外れないようにする
        menu.addEventListener('mousedown', (e) => e.preventDefault());
        menu.addEventListener('click', (e) => {
            const li = e.target.closest('li[data-index]');
            if (li) choose(Number(li.dataset.index));
        });
        document.body.appendChild(menu);
        return menu;
    };

    const position = () => {
        const rect = field.getBoundingClientRect();
        const width = Math.min(320, Math.max(220, rect.width));
        menu.style.width = `${width}px`;
        menu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)) + window.scrollX}px`;
        // 下に入りきらなければ入力欄の上に出す (チャットの入力欄は画面の下端にある)
        const below = window.innerHeight - rect.bottom;
        const height = menu.offsetHeight || 240;
        menu.style.top = below < height + 12 && rect.top > below
            ? `${rect.top + window.scrollY - height - 6}px`
            : `${rect.bottom + window.scrollY + 6}px`;
    };

    const render = () => {
        ensureMenu();
        menu.replaceChildren(...items.map((u, i) => {
            const li = document.createElement('li');
            li.id = `jh-mention-opt-${i}`;
            li.dataset.index = i;
            li.setAttribute('role', 'option');
            li.setAttribute('aria-selected', String(i === active));
            const avatar = document.createElement('span');
            avatar.className = 'jh-mention-avatar';
            if (u.avatar) {
                const img = document.createElement('img');
                img.src = u.avatar;
                img.alt = '';
                avatar.appendChild(img);
            } else {
                avatar.textContent = (u.name || u.username).slice(0, 1).toUpperCase();
            }
            const text = document.createElement('span');
            text.className = 'jh-mention-text';
            const name = document.createElement('strong');
            name.textContent = u.name;
            const handle = document.createElement('span');
            handle.textContent = `@${u.username}`;
            text.append(name, handle);
            li.append(avatar, text);
            return li;
        }));
        menu.hidden = !items.length;
        if (items.length) {
            field.setAttribute('aria-controls', menu.id);
            field.setAttribute('aria-activedescendant', `jh-mention-opt-${active}`);
            position();
        }
    };

    const choose = (index) => {
        const user = items[index];
        if (!user || !range || !field) return;
        const [start, end] = range;
        const insert = `@${user.username} `;
        field.value = field.value.slice(0, start) + insert + field.value.slice(end);
        const caret = start + insert.length;
        field.setSelectionRange(caret, caret);
        field.dispatchEvent(new Event('input', { bubbles: true }));
        close();
        field.focus();
    };

    const lookup = (el) => {
        if (el.selectionStart !== el.selectionEnd) return close();
        const before = el.value.slice(0, el.selectionStart);
        const match = before.match(TOKEN_RE);
        if (!match) return close();
        field = el;
        const query = match[1];
        range = [el.selectionStart - query.length - 1, el.selectionStart];
        clearTimeout(timer);
        const mine = ++seq;
        timer = setTimeout(async () => {
            try {
                const res = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`, { headers: { Accept: 'application/json' } });
                if (!res.ok || mine !== seq) return;
                const data = await res.json();
                if (mine !== seq || !range) return;
                items = data.users || [];
                active = 0;
                render();
            } catch (err) {
                close();
            }
        }, 150);
    };

    document.addEventListener('input', (e) => {
        const el = e.target;
        if (el instanceof HTMLElement && el.matches('[data-mention-input]')) lookup(el);
    });

    // チャットの入力欄などは Enter で送信するため、候補が出ている間は先に (キャプチャで) 受け取る
    document.addEventListener('keydown', (e) => {
        if (!menu || menu.hidden || e.target !== field || e.isComposing) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            active = (active + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
            render();
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            choose(active);
        } else if (e.key === 'Escape') {
            close();
        } else {
            return;
        }
        e.preventDefault();
        e.stopImmediatePropagation();
    }, true);

    document.addEventListener('focusout', (e) => { if (e.target === field) close(); });
    window.addEventListener('resize', () => { if (menu && !menu.hidden) position(); });
})();
