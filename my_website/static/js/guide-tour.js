// 使い方ガイド: 実際の画面の上に吹き出しを出して、一歩ずつ使い方を案内する。
// - 手順は章 (chapter) ごと。中身は core/guide_tour.py が /guide/tour.json で渡す。
// - 案内された操作 (押す・入力する・選ぶ) をすると次の手順へ進む。説明だけの手順は「次へ」で進む。
// - ページをまたぐ章もあるので、進み具合は localStorage に保存し、移動先のページで続きを出す。
// - スマートフォン (734px 以下) では吹き出しを画面の上下に固定したシートにし、対象を空いている側へスクロールする。
(() => {
    const script = document.currentScript;
    const DATA_URL = script && script.dataset.url;
    if (!DATA_URL) return;

    const KEY = 'jh-guide';
    const DONE_KEY = 'jh-guide-done';
    const MAX_AGE = 3 * 24 * 60 * 60 * 1000; // 3 日以上前の途中経過は捨てる
    const mobileMQ = window.matchMedia('(max-width: 734px)');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const GAP = 14;     // 対象と吹き出しの間隔
    const PAD = 8;      // スポットライトの余白
    const EDGE = 12;    // 画面端の余白
    const NAV_H = 48;   // 固定ヘッダーの高さ

    const store = {
        get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } },
        set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* 保存できなくてもこのページ内では続けられる */ } },
        remove(key) { try { localStorage.removeItem(key); } catch { /* noop */ } },
    };
    const fmt = (text, vars) => String(text).replace(/%\((\w+)\)s/g, (_, k) => (k in vars ? vars[k] : ''));
    const icon = (name) => `<span class="material-symbols-outlined" aria-hidden="true">${name}</span>`;
    const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

    // ── 設定の読み込み ───────────────────────────────
    let config = null;
    let configPromise = null;
    const loadConfig = () => {
        configPromise = configPromise || fetch(DATA_URL, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
            .then((res) => { if (!res.ok) throw new Error(res.status); return res.json(); })
            .then((data) => { config = data; return data; })
            .catch((err) => { configPromise = null; throw err; });
        return configPromise;
    };
    const L = (key) => (config && config.labels[key]) || '';
    const chapterById = (id) => config && config.chapters.find((c) => c.id === id);

    // ── 手順の判定 ───────────────────────────────────
    const device = () => (mobileMQ.matches ? 'mobile' : 'desktop');
    const applies = (step) => (!step.device || step.device === device())
        && (!step.auth || step.auth === (config.authenticated ? 'user' : 'guest'));
    const onPage = (step) => !step.page || new RegExp(step.page).test(location.pathname);
    const visibleSteps = (chapter) => chapter.steps.filter(applies);

    const nextApplicable = (chapter, from) => {
        for (let i = from; i < chapter.steps.length; i++) if (applies(chapter.steps[i])) return i;
        return -1;
    };

    // 保存されている位置から、このページで出す手順を決める。
    // 予定の手順がこのページのものでなければ、このページ用の手順 (先にあるもの → 前にあるもの) へ移る。
    const resolve = (chapter, index) => {
        const i = nextApplicable(chapter, index);
        if (i < 0) return { done: true };
        if (onPage(chapter.steps[i])) return { index: i };
        for (let j = i + 1; j < chapter.steps.length; j++) {
            const s = chapter.steps[j];
            if (applies(s) && s.page && onPage(s)) return { index: j };
        }
        for (let j = i - 1; j >= 0; j--) {
            const s = chapter.steps[j];
            if (applies(s) && s.page && onPage(s)) return { index: j };
        }
        return { index: i, offPage: true };
    };

    // ── 要素の可視判定と検索 ──────────────────────────
    const isVisible = (el) => {
        if (!el || !el.isConnected || el.closest('[hidden]')) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) return false;
        if (rect.right <= 0 || rect.left >= window.innerWidth) return false; // 横に流れて画面外 (カルーセルなど)
        for (let node = el; node && node !== document.body; node = node.parentElement) {
            const cs = getComputedStyle(node);
            if (cs.visibility === 'hidden' || cs.display === 'none') return false;
            // スクロールで現れる .jh-reveal は、まだ画面外なら透明なだけなので見えている扱い
            if (parseFloat(cs.opacity) < 0.05 && !node.classList.contains('jh-reveal')) return false;
        }
        return true;
    };
    const queryTarget = (selectors) => {
        for (const sel of selectors || []) {
            let nodes;
            try { nodes = document.querySelectorAll(sel); } catch { continue; }
            for (const el of nodes) if (isVisible(el)) return el;
        }
        return null;
    };
    const waitForTarget = (selectors, timeout = 2500) => new Promise((resolveTarget) => {
        const started = performance.now();
        const poll = () => {
            const el = queryTarget(selectors);
            if (el) return resolveTarget(el);
            if (performance.now() - started > timeout) return resolveTarget(null);
            setTimeout(poll, 120);
        };
        poll();
    });
    const isFixed = (el) => {
        for (let node = el; node && node !== document.body; node = node.parentElement) {
            const pos = getComputedStyle(node).position;
            if (pos === 'fixed' || pos === 'sticky') return true;
        }
        return false;
    };

    // ── DOM ─────────────────────────────────────────
    let root, spot, card, pill, toast;
    const build = () => {
        if (root) return;
        root = document.createElement('div');
        root.className = 'jh-guide';
        root.hidden = true;
        root.innerHTML = `
            <div class="jh-guide-dim"></div>
            <div class="jh-guide-spot">${icon('check')}</div>
            <section class="jh-guide-card" role="dialog" aria-modal="false" aria-labelledby="jh-guide-title" aria-describedby="jh-guide-body">
                <span class="jh-guide-arrow" aria-hidden="true"></span>
                <header class="jh-guide-head">
                    <span class="jh-guide-chapter-name"></span>
                    <span class="jh-guide-count" aria-live="polite"></span>
                    <button type="button" class="jh-guide-x" data-guide-close>${icon('close')}</button>
                </header>
                <div class="jh-guide-progress" aria-hidden="true"><i></i></div>
                <h3 class="jh-guide-title" id="jh-guide-title"></h3>
                <p class="jh-guide-body" id="jh-guide-body"></p>
                <p class="jh-guide-hint"></p>
                <div class="jh-guide-actions">
                    <button type="button" class="jh-guide-btn jh-guide-btn--ghost" data-guide-back></button>
                    <span class="jh-guide-spacer"></span>
                    <button type="button" class="jh-guide-btn jh-guide-btn--text" data-guide-skip></button>
                    <button type="button" class="jh-guide-btn jh-guide-btn--primary" data-guide-next></button>
                </div>
            </section>`;
        document.body.appendChild(root);
        spot = root.querySelector('.jh-guide-spot');
        card = root.querySelector('.jh-guide-card');

        pill = document.createElement('div');
        pill.className = 'jh-guide-pill';
        pill.hidden = true;
        pill.innerHTML = `
            <span class="jh-guide-pill-icon">${icon('school')}</span>
            <span class="jh-guide-pill-text"></span>
            <a class="jh-guide-pill-go" href="#"></a>
            <button type="button" class="jh-guide-pill-x" data-guide-close>${icon('close')}</button>`;
        document.body.appendChild(pill);

        toast = document.createElement('div');
        toast.className = 'jh-guide-toast';
        toast.setAttribute('role', 'status');
        toast.hidden = true;
        document.body.appendChild(toast);

        document.addEventListener('click', (e) => {
            if (e.target.closest('[data-guide-close]')) { e.preventDefault(); stop(true); }
        });
        card.querySelector('[data-guide-next]').addEventListener('click', () => onNext());
        card.querySelector('[data-guide-back]').addEventListener('click', () => onBack());
        card.querySelector('[data-guide-skip]').addEventListener('click', () => {
            if (finishedMode) { leaveFinished(); hideAll(); } else advance();
        });
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') { e.preventDefault(); stop(true); }
        });
    };

    // ── 状態 ─────────────────────────────────────────
    let state = null;      // { chapter, index, ts }
    let chapter = null;
    let current = null;    // 表示中の手順 { index, step, el, placement }
    let cleanup = [];      // 手順ごとのイベント解除
    let loopId = 0;
    let leaving = false;   // ページ移動中
    let finishedMode = false; // 完了画面を表示中
    let finishedNext = null;  // 完了画面で勧める次の章

    const save = () => { state.ts = Date.now(); store.set(KEY, state); };
    const doneList = () => store.get(DONE_KEY) || [];
    const markDone = (id) => { const list = doneList(); if (!list.includes(id)) store.set(DONE_KEY, [...list, id]); };

    const clearStep = () => {
        cleanup.forEach((fn) => fn());
        cleanup = [];
        cancelAnimationFrame(loopId);
        current = null;
    };
    const on = (target, type, fn, opts) => {
        target.addEventListener(type, fn, opts);
        cleanup.push(() => target.removeEventListener(type, fn, opts));
    };

    const hideAll = () => {
        clearStep();
        if (root) {
            root.classList.remove('is-visible');
            root.hidden = true;
        }
        if (pill) pill.hidden = true;
    };

    const stop = (showToast) => {
        if (finishedMode) { leaveFinished(); showToast = false; }
        hideAll();
        store.remove(KEY);
        state = null;
        if (showToast) flash(L('closed_toast'));
    };

    const flash = (text) => {
        build();
        toast.textContent = text;
        toast.hidden = false;
        requestAnimationFrame(() => toast.classList.add('is-visible'));
        clearTimeout(flash.timer);
        flash.timer = setTimeout(() => {
            toast.classList.remove('is-visible');
            setTimeout(() => { toast.hidden = true; }, 300);
        }, 3600);
    };

    // ── 開始・再開 ───────────────────────────────────
    const start = async (id) => {
        try { await loadConfig(); } catch { return; }
        if (!chapterById(id)) return;
        state = { chapter: id, index: 0, ts: Date.now() };
        save();
        run();
    };

    const run = () => {
        build();
        if (finishedMode) leaveFinished();
        hideAll();
        if (!state) return;
        if (state.finished) {
            const finished = state.finished;
            store.remove(KEY);
            state = null;
            showFinished(finished);
            return;
        }
        chapter = chapterById(state.chapter);
        if (!chapter) { stop(false); return; }
        const r = resolve(chapter, state.index);
        if (r.done) { finish(); return; }
        state.index = r.index;
        save();
        if (r.offPage) showPill(chapter.steps[r.index]);
        else showStep(r.index);
    };

    const showPill = (step) => {
        pill.querySelector('.jh-guide-pill-text').textContent = fmt(L('resume_hint'), { chapter: chapter.title });
        const go = pill.querySelector('.jh-guide-pill-go');
        go.textContent = L('resume');
        go.href = step.url || '/';
        pill.querySelector('.jh-guide-pill-x').setAttribute('aria-label', L('close'));
        pill.hidden = false;
    };

    // ── 手順の表示 ───────────────────────────────────
    const setMenu = (want) => {
        if (!want || !mobileMQ.matches) return;
        const menu = document.getElementById('jh-mobile-menu');
        const btn = document.getElementById('jh-menu-btn');
        if (!menu || !btn) return;
        if ((want === 'open') === menu.hidden) btn.click();
    };

    const hintIcon = (action) => ({
        click: mobileMQ.matches ? 'touch_app' : 'ads_click',
        change: mobileMQ.matches ? 'touch_app' : 'ads_click',
        input: 'keyboard',
        wait: 'login',
    }[action] || 'info');

    const showStep = async (index) => {
        clearStep();
        const step = chapter.steps[index];
        const token = {};
        current = { index, step, el: null, token };
        state.index = index;
        save();

        setMenu(step.menu);
        if (step.scroll_top && window.scrollY > 0) window.scrollTo({ top: 0, behavior: 'auto' });

        root.hidden = false;
        card.classList.add('is-switching');
        const el = step.target ? await waitForTarget(step.target) : null;
        if (!current || current.token !== token) return; // 待っている間に別の手順へ移った
        current.el = el;

        if (step.set_next && el) {
            el.querySelectorAll('input[name="next"]').forEach((input) => { input.value = step.set_next; });
        }

        fillCard(index, step, !el);
        root.classList.toggle('is-missing', !el);
        root.classList.remove('is-finished');
        root.classList.add('is-visible');
        root.classList.remove('is-done');

        if (el) {
            scrollToTarget(el);
            bindAction(step, el);
        }
        // 位置を合わせてから表示する (2 フレーム後: 吹き出しの高さが確定してから)
        loop();
        requestAnimationFrame(() => requestAnimationFrame(() => card.classList.remove('is-switching')));

        // 説明だけの手順はキーボードでそのまま進めるように「次へ」へフォーカス。
        // 入力の手順では、入力欄のフォーカスを奪わない。
        if (!step.action || !el) {
            card.querySelector('[data-guide-next]').focus({ preventScroll: true });
        }
    };

    const fillCard = (index, step, missing) => {
        const steps = visibleSteps(chapter);
        const pos = Math.max(0, steps.indexOf(step)) + 1;
        const isLast = nextApplicable(chapter, index + 1) < 0;

        card.querySelector('.jh-guide-chapter-name').innerHTML = `${icon(chapter.icon)}<span></span>`;
        card.querySelector('.jh-guide-chapter-name span:last-child').textContent = chapter.title;
        card.style.setProperty('--guide-color', chapter.color);
        root.style.setProperty('--guide-color', chapter.color);
        card.querySelector('.jh-guide-count').textContent = fmt(L('step'), { current: pos, total: steps.length });
        card.querySelector('.jh-guide-progress i').style.width = `${(pos / steps.length) * 100}%`;
        card.querySelector('.jh-guide-title').textContent = step.title;
        card.querySelector('.jh-guide-body').textContent = missing ? (step.missing || L('missing')) : step.body;
        card.querySelector('.jh-guide-x').setAttribute('aria-label', L('close'));
        card.querySelector('.jh-guide-x').title = L('close');

        const hint = card.querySelector('.jh-guide-hint');
        const showHint = !missing && step.action && step.action !== 'wait' && step.hint;
        hint.hidden = !showHint;
        if (showHint) hint.innerHTML = `${icon(hintIcon(step.action))}<span></span>`, hint.lastChild.textContent = step.hint;

        // 戻る: 同じページにある前の手順だけ (別のページへは戻さない)
        const back = card.querySelector('[data-guide-back]');
        const prev = prevOnPage(index);
        back.hidden = prev < 0;
        back.textContent = L('back');

        // 操作で進む手順は「次へ」の代わりに「この手順を飛ばす」。説明の手順・見つからない手順は「次へ」/「完了」
        const next = card.querySelector('[data-guide-next]');
        const skip = card.querySelector('[data-guide-skip]');
        const actionStep = step.action && !missing;
        const finalClick = actionStep && isLast && step.action === 'click';
        next.hidden = actionStep && !finalClick;
        next.textContent = isLast ? L('done') : L('next');
        skip.hidden = !actionStep || isLast;
        skip.textContent = L('skip_step');
        card.dataset.action = actionStep ? step.action : 'info';
    };

    const prevOnPage = (index) => {
        for (let j = index - 1; j >= 0; j--) {
            const s = chapter.steps[j];
            if (!applies(s)) continue;
            if (s.action === 'wait' || s.navigates || s.menu) return -1;
            return onPage(s) ? j : -1;
        }
        return -1;
    };

    // ── 操作の検出 ───────────────────────────────────
    const bindAction = (step, target) => {
        const el = (step.listen && document.querySelector(step.listen)) || target;
        if (step.action === 'click') {
            on(document, 'click', (e) => {
                if (!el.contains(e.target)) return;
                if (step.navigates) {
                    // 実際にページを移動するボタン・リンクを押したときだけ進む (余白のクリックは無視)
                    if (!e.target.closest('a[href], button, [role="button"], input[type="submit"]')) return;
                    advanceAcrossPage();
                } else {
                    succeed();
                }
            }, true);
        } else if (step.action === 'change') {
            on(el, 'change', () => succeed());
        } else if (step.action === 'input') {
            let timer = 0;
            const filled = () => {
                const field = el.matches('input, textarea') ? el : null;
                return (field ? field.value : el.textContent).trim().length > 0;
            };
            on(el, 'input', () => {
                clearTimeout(timer);
                // 打ち終わって少し経ってから進む (1 文字目で吹き出しが動くと入力の邪魔になる)
                if (filled()) timer = setTimeout(() => succeed(), 1100);
            });
            cleanup.push(() => clearTimeout(timer));
        }
    };

    const succeed = () => {
        if (!current) return;
        const index = current.index;
        current.token = {}; // 二重に進まないように
        root.classList.add('is-done');
        const hint = card.querySelector('.jh-guide-hint');
        hint.hidden = false;
        hint.innerHTML = `${icon('check_circle')}<span></span>`;
        hint.lastChild.textContent = L('nice');
        setTimeout(() => {
            if (!state || state.index !== index) return;
            advance();
        }, reduceMotion.matches ? 250 : 700);
    };

    // ページ移動を伴う操作: 移動先で続きを出せるよう、先に進捗を進めて保存する。
    // 入力チェックなどで移動しなかったら元に戻す。
    const advanceAcrossPage = () => {
        const prevIndex = current.index;
        const next = nextApplicable(chapter, prevIndex + 1);
        if (next < 0) state.finished = chapter.id;
        else state.index = next;
        save();
        const id = chapter.id;
        clearStep();
        root.classList.remove('is-visible');
        setTimeout(() => {
            if (leaving || !state || state.chapter !== id) return;
            delete state.finished;
            state.index = prevIndex;
            save();
            run();
        }, 1600);
    };

    const advance = () => {
        if (!state || !chapter) return;
        const next = nextApplicable(chapter, state.index + 1);
        if (next < 0) { finish(); return; }
        state.index = next;
        save();
        const step = chapter.steps[next];
        if (onPage(step)) showStep(next);
        else { hideAll(); showPill(step); }
    };

    const leaveFinished = () => {
        finishedMode = false;
        root.classList.remove('is-finished');
        card.querySelector('.jh-guide-hint').style.removeProperty('--guide-next-color');
    };

    const onNext = () => {
        if (finishedMode) {
            const nextChapter = finishedNext;
            leaveFinished();
            if (nextChapter) start(nextChapter.id);
            else hideAll();
            return;
        }
        if (!current) return;
        const { step, el } = current;
        // 最後の「押して完了」の手順で「完了」を押したとき、または見つからない手順
        if (!el && step.navigates) { finish(); return; }
        advance();
    };

    const onBack = () => {
        if (!current) return;
        const prev = prevOnPage(current.index);
        if (prev >= 0) showStep(prev);
    };

    // ── 完了 ─────────────────────────────────────────
    const finish = () => {
        const id = chapter && chapter.id;
        hideAll();
        store.remove(KEY);
        state = null;
        if (id) showFinished(id);
    };

    const showFinished = async (id) => {
        try { await loadConfig(); } catch { return; }
        const done = chapterById(id);
        if (!done) return;
        markDone(id);
        build();
        clearStep();
        const finishedIds = doneList();
        const order = config.chapters.map((c) => c.id);
        const startAt = order.indexOf(id);
        const nextChapter = [...order.slice(startAt + 1), ...order.slice(0, startAt)]
            .map(chapterById).find((c) => !finishedIds.includes(c.id));

        root.hidden = false;
        root.classList.add('is-visible', 'is-missing', 'is-finished');
        root.classList.remove('is-done');
        root.style.setProperty('--guide-color', done.color);
        card.style.setProperty('--guide-color', done.color);
        card.dataset.action = 'finished';
        card.querySelector('.jh-guide-chapter-name').innerHTML = `${icon('celebration')}`;
        card.querySelector('.jh-guide-count').textContent = '';
        card.querySelector('.jh-guide-progress i').style.width = '100%';
        card.querySelector('.jh-guide-title').textContent = fmt(L('finished_title'), { chapter: done.title });
        card.querySelector('.jh-guide-body').textContent = nextChapter ? L('finished_body') : L('finished_all');
        const hint = card.querySelector('.jh-guide-hint');
        hint.hidden = !nextChapter;
        if (nextChapter) {
            hint.innerHTML = `${icon(nextChapter.icon)}<span></span>`;
            hint.lastChild.textContent = nextChapter.title;
            hint.style.setProperty('--guide-next-color', nextChapter.color);
        }
        card.querySelector('[data-guide-back]').hidden = true;
        const skip = card.querySelector('[data-guide-skip]');
        skip.hidden = !nextChapter;
        skip.textContent = L('close');
        const next = card.querySelector('[data-guide-next]');
        next.hidden = false;
        next.textContent = nextChapter ? L('start_next') : L('done');

        finishedNext = nextChapter || null;
        finishedMode = true;
        current = { index: -1, step: {}, el: null, token: {} };
        loop();
        requestAnimationFrame(() => card.classList.remove('is-switching'));
        next.focus({ preventScroll: true });
        updatePickerDone();
    };

    // ── スクロールと配置 ─────────────────────────────
    const dockHeight = () => card.offsetHeight + EDGE * 2;

    const scrollToTarget = (el) => {
        if (isFixed(el)) return;
        const rect = el.getBoundingClientRect();
        const vh = window.innerHeight;
        let top;
        let bottom;
        if (mobileMQ.matches) {
            // 吹き出しは下に固定するので、対象はその上の空いている所に置く
            top = NAV_H + 12;
            bottom = vh - dockHeight();
        } else {
            top = NAV_H + 24;
            bottom = vh - 24;
        }
        if (rect.top >= top && rect.bottom <= bottom && !mobileMQ.matches) return;
        const room = bottom - top;
        const offset = rect.height + PAD * 2 <= room ? top + (room - rect.height) / 2 : top + PAD;
        const y = window.scrollY + rect.top - offset;
        if (Math.abs(y - window.scrollY) < 4) return;
        window.scrollTo({ top: Math.max(0, y), behavior: reduceMotion.matches ? 'auto' : 'smooth' });
    };

    const loop = () => {
        cancelAnimationFrame(loopId);
        const tick = () => {
            if (!current) return;
            position();
            loopId = requestAnimationFrame(tick);
        };
        tick();
    };

    const position = () => {
        const vw = document.documentElement.clientWidth;
        const vh = window.innerHeight;
        let el = current.el;
        if (el && !el.isConnected) {
            // 再描画で要素が差し替わったら探し直す
            el = current.el = queryTarget(current.step.target);
        }
        const rect = el ? el.getBoundingClientRect() : null;

        if (rect) {
            const radius = Math.min(parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0, 24) + PAD / 2;
            // 画面の端にある対象 (ヘッダーなど) でも枠が切れないよう、画面内に収める
            const x1 = Math.max(rect.left - PAD, 3);
            const y1 = Math.max(rect.top - PAD, 3);
            const x2 = Math.min(rect.right + PAD, vw - 3);
            const y2 = Math.min(rect.bottom + PAD, vh - 3);
            spot.style.transform = `translate(${x1}px, ${y1}px)`;
            spot.style.width = `${Math.max(0, x2 - x1)}px`;
            spot.style.height = `${Math.max(0, y2 - y1)}px`;
            spot.style.borderRadius = `${radius}px`;
        }

        const w = card.offsetWidth;
        const h = card.offsetHeight;
        let placement;
        let left;
        let top;

        if (!rect || mobileMQ.matches) {
            // シート: 対象が下半分にあれば上、そうでなければ下に固定
            const targetLow = rect && rect.top + rect.height / 2 > vh * 0.55 && rect.top > h + NAV_H;
            placement = !rect ? 'center' : (targetLow ? 'dock-top' : 'dock-bottom');
        } else {
            const fits = {
                bottom: rect.bottom + PAD + GAP + h <= vh - EDGE,
                top: rect.top - PAD - GAP - h >= NAV_H / 2,
                right: rect.right + PAD + GAP + w <= vw - EDGE,
                left: rect.left - PAD - GAP - w >= EDGE,
            };
            const prefer = current.placement && fits[current.placement] ? [current.placement] : [];
            placement = [...prefer, 'bottom', 'top', 'right', 'left'].find((p) => fits[p]) || 'dock-bottom';
        }
        current.placement = placement;

        if (placement === 'bottom' || placement === 'top') {
            left = clamp(rect.left + rect.width / 2 - w / 2, EDGE, vw - w - EDGE);
            top = placement === 'bottom' ? rect.bottom + PAD + GAP : rect.top - PAD - GAP - h;
            card.style.setProperty('--arrow-x', `${clamp(rect.left + rect.width / 2 - left, 22, w - 22)}px`);
        } else if (placement === 'right' || placement === 'left') {
            top = clamp(rect.top + rect.height / 2 - h / 2, NAV_H / 2, vh - h - EDGE);
            left = placement === 'right' ? rect.right + PAD + GAP : rect.left - PAD - GAP - w;
            card.style.setProperty('--arrow-y', `${clamp(rect.top + rect.height / 2 - top, 22, h - 22)}px`);
        } else if (placement === 'dock-top') {
            left = (vw - w) / 2;
            top = NAV_H + EDGE;
        } else if (placement === 'dock-bottom') {
            left = (vw - w) / 2;
            top = vh - h - EDGE;
        } else {
            left = (vw - w) / 2;
            top = (vh - h) / 2;
        }
        card.dataset.placement = placement;
        card.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
    };

    // ── ホームのガイド選択 ───────────────────────────
    const picker = document.getElementById('jh-guide-picker');
    const updatePickerDone = () => {
        if (!picker) return;
        const done = doneList();
        picker.querySelectorAll('[data-guide-start]').forEach((btn) => {
            const mark = btn.querySelector('[data-guide-done]');
            if (mark) mark.hidden = !done.includes(btn.dataset.guideStart);
        });
    };
    if (picker) {
        const closePicker = () => {
            picker.classList.remove('is-open');
            setTimeout(() => { if (picker.open) picker.close(); }, reduceMotion.matches ? 0 : 220);
        };
        document.addEventListener('click', (e) => {
            const opener = e.target.closest('[data-guide-open]');
            if (opener) {
                e.preventDefault();
                updatePickerDone();
                loadConfig().catch(() => {}); // 選んでいる間に読み込んでおく
                if (!picker.open) picker.showModal();
                requestAnimationFrame(() => picker.classList.add('is-open'));
                return;
            }
            const chooser = e.target.closest('[data-guide-start]');
            if (chooser) {
                closePicker();
                start(chooser.dataset.guideStart);
                return;
            }
            if (e.target.closest('[data-guide-picker-close]') || e.target === picker) closePicker();
        });
        picker.addEventListener('cancel', (e) => { e.preventDefault(); closePicker(); });
        updatePickerDone();
    }

    // ── 起動 ─────────────────────────────────────────
    window.addEventListener('pagehide', () => { leaving = true; });
    window.addEventListener('beforeunload', () => { leaving = true; });
    window.addEventListener('pageshow', (e) => {
        // 戻る/進むでキャッシュから復元されたページでは、保存されている進み具合から出し直す
        if (!e.persisted) return;
        leaving = false;
        resume();
    });
    // 画面幅が PC ⇔ スマートフォンをまたいだら、その画面用の手順で出し直す
    mobileMQ.addEventListener('change', () => { if (state && config) run(); });

    const resume = () => {
        const saved = store.get(KEY);
        if (!saved || !saved.chapter || Date.now() - (saved.ts || 0) > MAX_AGE) {
            if (saved) store.remove(KEY);
            return;
        }
        state = saved;
        loadConfig().then(run).catch(() => {});
    };

    const boot = () => resume();
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})();
