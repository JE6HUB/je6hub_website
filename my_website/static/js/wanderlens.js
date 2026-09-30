/**
 * WanderLens — 写真 × 地図の旅ジャーナル
 * - 写真マーカー + クラスタ (Apple 写真アプリの「場所」風)
 * - スポットの詳細シート (ギャラリー・コメント・前後移動・共有リンク)
 * - タイムライン / 写真グリッド表示、旅のルート線、航空写真
 * - 持ち主はスポットの追加・編集 (写真の位置情報・場所検索・地図で位置調整)
 *
 * ユーザーが入力した文字列は常に textContent で入れ、HTML として解釈させない。
 */
(() => {
    const cfg = JSON.parse(document.getElementById('wl-config').textContent);
    const pins = JSON.parse(document.getElementById('wl-pins').textContent);
    const t = cfg.t;
    const lang = document.documentElement.lang || 'ja';

    // ── 小さなユーティリティ ─────────────────────────────
    const $ = (sel, root = document) => root.querySelector(sel);
    function h(tag, attrs = {}, ...children) {
        const el = document.createElement(tag);
        Object.entries(attrs).forEach(([k, v]) => {
            if (v === null || v === undefined || v === false) return;
            if (k === 'class') el.className = v;
            else if (k === 'text') el.textContent = v;
            else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
            else el.setAttribute(k, v === true ? '' : v);
        });
        children.flat().forEach((c) => c !== null && c !== undefined && el.append(c));
        return el;
    }
    const icon = (name) => h('span', { class: 'material-symbols-outlined', 'aria-hidden': 'true', text: name });
    const url = (tpl, id) => tpl.replace('/0/', `/${id}/`);
    const userUrl = (name) => cfg.urls.userMap.replace('__user__', encodeURIComponent(name));
    const dateOf = (p) => p.visited || p.created;
    const fmtDate = (iso, opts = { year: 'numeric', month: 'long', day: 'numeric' }) =>
        (iso ? new Intl.DateTimeFormat(lang, opts).format(new Date(`${iso}T00:00:00`)) : '');
    const placeLine = (p) => [p.place, p.country].filter(Boolean).join(', ');
    const csrf = () => $('[name=csrfmiddlewaretoken]').value;
    const toast = (msg) => {
        const el = h('div', { class: 'wl-toast', role: 'status', text: msg });
        document.body.append(el);
        setTimeout(() => el.classList.add('is-out'), 1600);
        setTimeout(() => el.remove(), 2000);
    };
    const copy = async (text) => {
        try { await navigator.clipboard.writeText(text); toast(t.copied); } catch (e) { window.prompt('', text); }
    };
    const pinLink = (p) => {
        const u = new URL(userUrl(p.owner), location.origin);
        u.searchParams.set('pin', p.id);
        return u.toString();
    };

    // ── 地図 ─────────────────────────────────────────
    // 地図タイル: API キー不要の Esri ダークグレー (地名は別レイヤーで重ねる)。
    // CARTO の無料タイルは API キー必須になり透かしが入るため使わない。
    const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services';
    const ESRI_ATTR = 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
    const TILES = {
        dark: L.layerGroup([
            L.tileLayer(`${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, { attribution: ESRI_ATTR, maxNativeZoom: 16, maxZoom: 19 }),
            L.tileLayer(`${ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { maxNativeZoom: 16, maxZoom: 19 }),
        ]),
        satellite: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; Esri', maxZoom: 19,
        }),
    };
    const map = L.map('wl-map', { zoomControl: false, worldCopyJump: true, minZoom: 2 }).setView([30, 10], 2);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    TILES.dark.addTo(map);

    function markerIcon(pin) {
        const photo = pin.photos[0];
        const el = h('div', { class: `wl-marker${photo ? '' : ' wl-marker--dot'}` },
            photo ? h('img', { src: photo.thumb, alt: '', loading: 'lazy' }) : icon('location_on'));
        return L.divIcon({ html: el, className: 'wl-marker-wrap', iconSize: [52, 52], iconAnchor: [26, 60] });
    }
    const cluster = L.markerClusterGroup({
        showCoverageOnHover: false,
        maxClusterRadius: 64,
        spiderfyDistanceMultiplier: 1.6,
        iconCreateFunction(c) {
            const children = c.getAllChildMarkers();
            const withPhoto = children.find((m) => m.options.pin.photos.length);
            const el = h('div', { class: 'wl-marker wl-marker--cluster' },
                withPhoto ? h('img', { src: withPhoto.options.pin.photos[0].thumb, alt: '' }) : icon('photo_library'),
                h('span', { class: 'wl-marker-count', text: String(c.getChildCount()) }));
            return L.divIcon({ html: el, className: 'wl-marker-wrap', iconSize: [60, 60], iconAnchor: [30, 68] });
        },
    });
    const markers = new Map();
    pins.forEach((p) => {
        const m = L.marker([p.lat, p.lng], { icon: markerIcon(p), pin: p, title: p.title, riseOnHover: true });
        m.on('click', () => openSheet(p));
        markers.set(p.id, m);
        cluster.addLayer(m);
    });
    map.addLayer(cluster);

    const fitAll = (animate = true) => {
        if (!pins.length) return;
        map.fitBounds(L.latLngBounds(pins.map((p) => [p.lat, p.lng])), { padding: [60, 60], maxZoom: 12, animate });
    };
    fitAll(false);

    // 旅のルート (訪れた順)
    const ordered = [...pins].sort((a, b) => dateOf(a).localeCompare(dateOf(b)) || a.id - b.id);
    const route = L.polyline(ordered.map((p) => [p.lat, p.lng]), {
        color: '#2997ff', weight: 3, opacity: 0.85, dashArray: '2 8', lineCap: 'round',
    });

    document.querySelectorAll('.wl-ctl').forEach((btn) => btn.addEventListener('click', () => {
        const ctl = btn.dataset.ctl;
        if (ctl === 'fit') fitAll();
        if (ctl === 'route') {
            const on = btn.getAttribute('aria-pressed') !== 'true';
            btn.setAttribute('aria-pressed', String(on));
            if (on) route.addTo(map); else route.remove();
        }
        if (ctl === 'layer') {
            const sat = btn.getAttribute('aria-pressed') !== 'true';
            btn.setAttribute('aria-pressed', String(sat));
            map.removeLayer(sat ? TILES.dark : TILES.satellite);
            (sat ? TILES.satellite : TILES.dark).addTo(map);
        }
    }));

    // ── 場所の検索 (OpenStreetMap Nominatim) ───────────────
    const geo = {
        async search(q) {
            const u = `https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&limit=6&accept-language=${lang}&q=${encodeURIComponent(q)}`;
            const res = await fetch(u, { headers: { Accept: 'application/json' } });
            return res.ok ? res.json() : [];
        },
        async reverse(lat, lng) {
            const u = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=14&addressdetails=1&accept-language=${lang}&lat=${lat}&lon=${lng}`;
            const res = await fetch(u, { headers: { Accept: 'application/json' } });
            return res.ok ? res.json() : null;
        },
        label(r) {
            const a = r.address || {};
            return {
                place: r.name || a.attraction || a.tourism || a.suburb || a.city || a.town || a.village || a.county || a.state || '',
                city: a.city || a.town || a.village || a.county || a.state || '',
                country: a.country || '',
            };
        },
    };

    /** 入力欄 + 候補リスト。onPick(result) で選択を通知 */
    function attachSearch(input, list, onPick) {
        let timer = null;
        let seq = 0;
        const close = () => { list.hidden = true; list.replaceChildren(); };
        input.addEventListener('input', () => {
            clearTimeout(timer);
            const q = input.value.trim();
            if (q.length < 2) { close(); return; }
            timer = setTimeout(async () => {
                const my = ++seq;
                let results = [];
                try { results = await geo.search(q); } catch (e) { results = []; }
                if (my !== seq) return;
                list.replaceChildren(...(results.length ? results.map((r) => {
                    const lab = geo.label(r);
                    return h('li', { tabindex: '-1', onmousedown: (e) => { e.preventDefault(); close(); onPick(r); } },
                        h('strong', { text: lab.place || r.display_name.split(',')[0] }),
                        h('small', { text: [lab.city, lab.country].filter((v) => v && v !== lab.place).join(', ') }));
                }) : [h('li', { class: 'is-empty', text: t.noResults })]));
                list.hidden = false;
            }, 450); // Nominatim の利用規約に沿って、入力が止まってから 1 回だけ問い合わせる
        });
        input.addEventListener('keydown', (e) => {
            // 日本語入力の確定の Enter では選ばない (Safari は isComposing = false、keyCode 229 で届く)
            if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
                const first = list.querySelector('li:not(.is-empty)');
                if (first) { e.preventDefault(); first.dispatchEvent(new MouseEvent('mousedown')); }
            }
            if (e.key === 'Escape') close();
        });
        input.addEventListener('blur', () => setTimeout(close, 150));
    }
    attachSearch($('#wl-search'), $('#wl-search-results'), (r) => {
        const bb = r.boundingbox && r.boundingbox.map(Number);
        if (bb) map.flyToBounds([[bb[0], bb[2]], [bb[1], bb[3]]], { maxZoom: 14, duration: 1.2 });
        else map.flyTo([Number(r.lat), Number(r.lon)], 12);
    });

    // ── 詳細シート ───────────────────────────────────────
    const sheet = $('#wl-sheet');
    let current = null;
    let slide = 0;
    let list = ordered; // 前後移動の順番 (訪れた順)

    function renderGallery(p) {
        const track = $('#wl-gallery-track');
        const dots = $('#wl-gallery-dots');
        const photos = p.photos;
        $('#wl-gallery').classList.toggle('is-empty', !photos.length);
        $('#wl-gallery').classList.toggle('is-single', photos.length < 2);
        track.replaceChildren(...(photos.length
            ? photos.map((ph) => h('figure', { class: 'wl-slide' }, h('img', { src: ph.url, alt: p.title, loading: 'lazy' })))
            : [h('div', { class: 'wl-slide wl-slide--empty' }, icon('photo_camera'), h('span', { text: t.noPhoto }))]));
        dots.replaceChildren(...photos.map((_, i) => h('button', {
            type: 'button', class: 'wl-dot', 'aria-label': `${i + 1} / ${photos.length}`, onclick: () => goSlide(i),
        })));
        slide = 0;
        track.scrollLeft = 0;
        updateDots();
    }
    function goSlide(i) {
        const track = $('#wl-gallery-track');
        const n = track.children.length;
        slide = (i + n) % n;
        track.scrollTo({ left: track.clientWidth * slide, behavior: 'smooth' });
        updateDots();
    }
    function updateDots() {
        document.querySelectorAll('#wl-gallery-dots .wl-dot').forEach((d, i) => d.classList.toggle('is-active', i === slide));
    }
    $('#wl-gallery-track').addEventListener('scroll', (e) => {
        const tr = e.currentTarget;
        const i = Math.round(tr.scrollLeft / Math.max(1, tr.clientWidth));
        if (i !== slide) { slide = i; updateDots(); }
    }, { passive: true });
    document.querySelectorAll('.wl-gallery-nav').forEach((b) => b.addEventListener('click', () => goSlide(slide + Number(b.dataset.dir))));

    function openSheet(p, { photoIndex = 0 } = {}) {
        current = p;
        renderGallery(p);
        const meta = [fmtDate(dateOf(p)), placeLine(p)].filter(Boolean).join(' · ');
        $('#wl-sheet-meta').textContent = meta;
        $('#wl-sheet-title').textContent = p.title;
        $('#wl-sheet-desc').textContent = p.desc;
        $('#wl-sheet-desc').hidden = !p.desc;
        const owner = $('#wl-sheet-owner');
        owner.hidden = cfg.mode === 'user';
        owner.textContent = `${t.by} ${p.owner}`;
        owner.href = userUrl(p.owner);
        if (cfg.canEdit) $('#wl-delete-form').action = url(cfg.urls.delete, p.id);
        const report = $('#wl-sheet-report');
        if (report) report.href = url(cfg.urls.reportPin, p.id);
        const idx = list.findIndex((x) => x.id === p.id);
        sheet.querySelector('[data-step="-1"]').disabled = idx <= 0;
        sheet.querySelector('[data-step="1"]').disabled = idx < 0 || idx >= list.length - 1;
        loadComments(p.id);
        const u = new URL(location.href);
        u.searchParams.set('pin', p.id);
        history.replaceState(null, '', u);
        if (!sheet.open) sheet.showModal();
        if (photoIndex) requestAnimationFrame(() => goSlide(photoIndex));
    }
    sheet.addEventListener('close', () => {
        const u = new URL(location.href);
        u.searchParams.delete('pin');
        history.replaceState(null, '', u);
    });
    sheet.addEventListener('click', (e) => { if (e.target === sheet) sheet.close(); }); // 背景クリックで閉じる
    sheet.addEventListener('keydown', (e) => {
        if (e.target.closest('input, textarea')) return;
        if (e.key === 'ArrowLeft') goSlide(slide - 1);
        if (e.key === 'ArrowRight') goSlide(slide + 1);
    });
    sheet.querySelectorAll('[data-step]').forEach((b) => b.addEventListener('click', () => {
        const idx = list.findIndex((x) => x.id === current.id) + Number(b.dataset.step);
        if (list[idx]) openSheet(list[idx]);
    }));
    $('#wl-sheet-locate').addEventListener('click', () => {
        const p = current;
        sheet.close();
        showView('map');
        const m = markers.get(p.id);
        cluster.zoomToShowLayer(m, () => map.flyTo([p.lat, p.lng], Math.max(map.getZoom(), 13), { duration: 0.8 }));
        document.getElementById('wl-map').scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    $('#wl-sheet-copy').addEventListener('click', () => copy(pinLink(current)));
    const del = $('#wl-delete-form');
    if (del) del.addEventListener('submit', (e) => { if (!window.confirm(t.confirmDelete)) e.preventDefault(); });

    // コメント
    async function loadComments(id) {
        const box = $('#wl-comment-list');
        box.replaceChildren(h('p', { class: 'wl-muted', text: t.loading }));
        try {
            const res = await fetch(url(cfg.urls.comments, id), { headers: { Accept: 'application/json' } });
            const data = await res.json();
            if (current.id !== id) return;
            box.replaceChildren(...(data.comments.length ? data.comments.map((c) => h('div', { class: 'wl-comment' },
                h('span', { class: 'wl-avatar wl-avatar--sm', 'aria-hidden': 'true', text: (c.author_name[0] || '?').toUpperCase() }),
                h('div', {},
                    h('p', { class: 'wl-comment-head' }, h('strong', { text: c.author_name }), h('span', { text: c.created_at }),
                        c.id ? h('a', { class: 'wl-comment-report', href: url(cfg.urls.reportComment, c.id), text: t.report }) : null),
                    h('p', { class: 'wl-comment-text', text: c.text })))) : [h('p', { class: 'wl-muted', text: t.noComments })]));
        } catch (e) {
            box.replaceChildren(h('p', { class: 'wl-error', text: t.loadFailed }));
        }
    }
    $('#wl-comment-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = $('#wl-comment-input');
        const err = $('#wl-comment-error');
        const text = input.value.trim();
        if (!text || !current) return;
        err.hidden = true;
        try {
            const res = await fetch(url(cfg.urls.comments, current.id), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), Accept: 'application/json' },
                body: JSON.stringify({ text }),
            });
            if (!res.ok) throw new Error();
            input.value = '';
            current.comments += 1;
            loadComments(current.id);
        } catch (e2) {
            err.textContent = t.sendFailed;
            err.hidden = false;
        }
    });

    // ── 一覧表示 (探索ページの「最近の旅」/ タイムライン / 写真) ─────
    function card(p) {
        const photo = p.photos[0];
        return h('button', { type: 'button', class: 'wl-card', role: 'listitem', onclick: () => openSheet(p) },
            h('span', { class: 'wl-card-media' }, photo ? h('img', { src: photo.thumb, alt: '', loading: 'lazy' }) : icon('photo_camera')),
            h('span', { class: 'wl-card-body' },
                h('strong', { text: p.title }),
                h('small', { text: [placeLine(p), fmtDate(dateOf(p))].filter(Boolean).join(' · ') }),
                cfg.mode === 'discovery' ? h('small', { class: 'wl-card-owner', 'data-profile': p.owner, text: `${t.by} ${p.owner}` }) : null));
    }
    const recent = $('#wl-recent');
    if (recent) {
        list = pins; // 探索ページでは新しい順に移動
        recent.replaceChildren(...pins.slice(0, 8).map(card));
    }

    const timeline = $('#wl-timeline');
    if (timeline) {
        const byMonth = new Map();
        [...ordered].reverse().forEach((p) => {
            const key = dateOf(p).slice(0, 7);
            if (!byMonth.has(key)) byMonth.set(key, []);
            byMonth.get(key).push(p);
        });
        timeline.replaceChildren(...[...byMonth.entries()].map(([key, items]) => h('section', { class: 'wl-tl-group' },
            h('h3', { class: 'wl-tl-month', text: fmtDate(`${key}-01`, { year: 'numeric', month: 'long' }) }),
            h('div', { class: 'wl-tl-items' }, items.map(card)))));
    }

    const grid = $('#wl-photos');
    if (grid) {
        grid.replaceChildren(...ordered.slice().reverse().flatMap((p) => p.photos.map((ph, i) => h('button', {
            type: 'button', class: 'wl-photo', 'aria-label': p.title, onclick: () => openSheet(p, { photoIndex: i }),
        }, h('img', { src: ph.thumb, alt: '', loading: 'lazy' })))));
    }

    // 表示切り替え (マップ / タイムライン / 写真)
    function showView(name) {
        document.querySelectorAll('.wl-view').forEach((v) => { v.hidden = v.dataset.view !== name; });
        const radio = document.querySelector(`input[name="wl-view"][value="${name}"]`);
        if (radio) radio.checked = true;
        if (name === 'map') setTimeout(() => map.invalidateSize(), 0);
    }
    document.querySelectorAll('input[name="wl-view"]').forEach((r) => r.addEventListener('change', () => showView(r.value)));

    const share = $('#wl-share');
    if (share) share.addEventListener('click', () => copy(new URL(userUrl(cfg.username), location.origin).toString()));

    // ── 追加・編集 (持ち主のみ) ─────────────────────────────
    if (cfg.canEdit) setupEditor();

    function setupEditor() {
        const dlg = $('#wl-editor');
        const form = $('#wl-editor-form');
        const fileInput = $('#wl-photos-input');
        const thumbs = $('#wl-thumbs');
        const f = {
            title: $('#wl-title'), date: $('#wl-date'), desc: $('#wl-desc'), place: $('#wl-place'),
            country: $('#wl-country'), lat: $('#wl-lat'), lng: $('#wl-lng'), order: $('#wl-photo-order'),
        };
        let newFiles = [];
        let existing = []; // { id, thumb, removed }
        let placeTouched = false; // 場所名を手入力したら逆ジオコーディングで上書きしない
        let locationSource = null; // 'manual' | 'exif'

        // 小さな地図 (位置の確認・調整)
        // 位置合わせ用: 道路や建物まで見える OpenStreetMap 標準タイル
        const mini = L.map('wl-editor-map', { zoomControl: true }).setView([35.68, 139.76], 4);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(mini);
        const pinIcon = L.divIcon({ html: h('div', { class: 'wl-marker wl-marker--dot wl-marker--edit' }, icon('location_on')), className: 'wl-marker-wrap', iconSize: [40, 40], iconAnchor: [20, 46] });
        let miniMarker = null;

        function setLocation(lat, lng, { source = 'manual', fly = true, lookup = true } = {}) {
            f.lat.value = Number(lat).toFixed(6);
            f.lng.value = Number(lng).toFixed(6);
            locationSource = source;
            $('#wl-coords').textContent = `${Number(lat).toFixed(5)}, ${Number(lng).toFixed(5)}`;
            if (!miniMarker) {
                miniMarker = L.marker([lat, lng], { icon: pinIcon, draggable: true }).addTo(mini);
                miniMarker.on('dragend', () => { const ll = miniMarker.getLatLng(); setLocation(ll.lat, ll.lng, { fly: false }); });
            } else {
                miniMarker.setLatLng([lat, lng]);
            }
            if (fly) mini.setView([lat, lng], Math.max(mini.getZoom(), 13));
            $('#wl-exif-badge').hidden = source !== 'exif';
            if (lookup) reverseLookup(lat, lng);
        }
        async function reverseLookup(lat, lng) {
            try {
                const r = await geo.reverse(lat, lng);
                if (!r) return;
                const lab = geo.label(r);
                f.country.value = lab.country;
                if (!placeTouched) f.place.value = lab.place || lab.city;
            } catch (e) { /* ネットワークエラー時は場所名なしで保存できる */ }
        }
        mini.on('click', (e) => setLocation(e.latlng.lat, e.latlng.lng, { fly: false }));
        f.place.addEventListener('input', () => { placeTouched = true; });
        attachSearch(f.place, $('#wl-place-results'), (r) => {
            const lab = geo.label(r);
            f.place.value = lab.place || r.display_name.split(',')[0];
            placeTouched = true;
            f.country.value = lab.country;
            setLocation(Number(r.lat), Number(r.lon), { lookup: false });
        });

        // 写真
        function renderThumbs() {
            const items = [
                ...existing.map((ph) => h('div', { class: `wl-thumb${ph.removed ? ' is-removed' : ''}` },
                    h('img', { src: ph.thumb, alt: '' }),
                    h('button', {
                        type: 'button', class: 'wl-thumb-x', 'aria-label': ph.removed ? t.restore : t.remove,
                        onclick: () => { ph.removed = !ph.removed; renderThumbs(); },
                    }, icon(ph.removed ? 'undo' : 'close')))),
                ...newFiles.map((file, i) => h('div', { class: 'wl-thumb' },
                    h('img', { src: file.__preview, alt: '' }),
                    h('button', {
                        type: 'button', class: 'wl-thumb-x', 'aria-label': t.remove,
                        onclick: () => { newFiles.splice(i, 1); renderThumbs(); },
                    }, icon('close')))),
            ];
            const first = items.find((el) => !el.classList.contains('is-removed'));
            if (first) first.append(h('span', { class: 'wl-thumb-cover', text: t.cover }));
            thumbs.replaceChildren(...items);
        }
        async function addFiles(files) {
            const imgs = [...files].filter((file) => /^image\/(jpeg|png|webp)$/.test(file.type));
            const room = cfg.maxPhotos - existing.filter((ph) => !ph.removed).length - newFiles.length;
            if (imgs.length > room) toast(t.tooManyPhotos);
            const accepted = imgs.slice(0, Math.max(0, room));
            accepted.forEach((file) => { file.__preview = URL.createObjectURL(file); });
            newFiles.push(...accepted);
            renderThumbs();
            // 位置がまだ決まっていなければ、写真の位置情報・撮影日を使う
            for (const file of accepted) {
                try {
                    // exifr の lite 版はタグ名の指定 (pick) に対応しないため、既定の parse で位置と日付をまとめて読む
                    const meta = await window.exifr.parse(file);
                    if (!meta) continue;
                    if ((!f.lat.value || locationSource === 'exif') && Number.isFinite(meta.latitude) && Number.isFinite(meta.longitude)) {
                        setLocation(meta.latitude, meta.longitude, { source: 'exif' });
                    }
                    // 撮影日時 → 作成日時 → 更新日時 の順に使う (機種やアプリで入るタグが違う)
                    const d = meta.DateTimeOriginal || meta.CreateDate || meta.ModifyDate;
                    if (!f.date.value && d instanceof Date && !Number.isNaN(d.getTime())) {
                        // toISOString() は UTC になり日付がずれるため、撮影地の日付 (ローカル) のまま使う
                        const pad = (n) => String(n).padStart(2, '0');
                        f.date.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
                    }
                } catch (e) { /* 位置情報のない写真 */ }
            }
        }
        const drop = $('#wl-drop');
        drop.addEventListener('click', () => fileInput.click());
        drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
        fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });
        ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('is-over'); }));
        ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('is-over'); }));
        drop.addEventListener('drop', (e) => addFiles(e.dataTransfer.files));

        function open(pin = null, at = null) {
            form.reset();
            newFiles = [];
            existing = [];
            placeTouched = false;
            locationSource = null;
            f.lat.value = f.lng.value = f.country.value = '';
            $('#wl-coords').textContent = '';
            $('#wl-exif-badge').hidden = true;
            form.querySelectorAll('input[name="remove_photos"]').forEach((i) => i.remove());
            const title = $('#wl-editor-title');
            if (pin) {
                title.textContent = title.dataset.edit;
                form.action = url(cfg.urls.edit, pin.id);
                f.title.value = pin.title;
                f.desc.value = pin.desc;
                f.date.value = pin.visited;
                f.place.value = pin.place;
                f.country.value = pin.country;
                placeTouched = !!pin.place;
                existing = pin.photos.map((ph) => ({ ...ph, removed: false }));
            } else {
                title.textContent = title.dataset.add;
                form.action = form.dataset.addUrl;
            }
            renderThumbs();
            dlg.showModal();
            setTimeout(() => {
                mini.invalidateSize();
                if (pin) setLocation(pin.lat, pin.lng, { lookup: false });
                else if (at) setLocation(at.lat, at.lng);
                else if (miniMarker) { miniMarker.remove(); miniMarker = null; mini.setView(map.getCenter(), Math.max(map.getZoom(), 3)); }
                else mini.setView(map.getCenter(), Math.max(map.getZoom(), 3));
                f.title.focus();
            }, 30);
        }
        dlg.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => dlg.close()));

        form.addEventListener('submit', (e) => {
            // 位置が未設定でも写真があれば送信する (サーバー側でも写真の位置情報を読む)
            if (!f.lat.value && !newFiles.length) {
                e.preventDefault();
                toast(t.needLocation);
                return;
            }
            // 選んだ写真を input に入れて送信 (DataTransfer)
            const dt = new DataTransfer();
            newFiles.forEach((file) => dt.items.add(file));
            fileInput.files = dt.files;
            existing.filter((ph) => ph.removed).forEach((ph) => form.append(h('input', { type: 'hidden', name: 'remove_photos', value: String(ph.id) })));
            f.order.value = existing.filter((ph) => !ph.removed).map((ph) => ph.id).join(',');
            $('#wl-editor-submit').disabled = true;
        });

        $('#wl-add').addEventListener('click', () => open());
        const edit = $('#wl-sheet-edit');
        if (edit) edit.addEventListener('click', () => { const p = current; sheet.close(); open(p); });
        // 地図の右クリック / 長押しで、その場所に追加
        map.on('contextmenu', (e) => open(null, e.latlng));
    }

    // ── 共有リンク (?pin=ID) で開く ──────────────────────────
    const initial = Number(new URLSearchParams(location.search).get('pin'));
    const initialPin = pins.find((p) => p.id === initial);
    if (initialPin) {
        const m = markers.get(initialPin.id);
        cluster.zoomToShowLayer(m, () => {});
        openSheet(initialPin);
    }
})();
