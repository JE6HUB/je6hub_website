/**
 * WanderLens — 写真 × 地図の旅ジャーナル
 * - 写真マーカー + クラスタ (写真アプリの「場所」風)
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

    // ── 地図 (Mapbox GL JS) ───────────────────────────────
    // スタイルは settings の MAPBOX_STYLE などで Mapbox Studio のものに差し替えられる。
    mapboxgl.accessToken = cfg.mapbox.token;
    const STYLES = { dark: cfg.mapbox.style, satellite: cfg.mapbox.satellite };
    const CLUSTER_MAX_ZOOM = 14; // これより拡大すると、まとめずに 1 件ずつ表示する
    const map = new mapboxgl.Map({
        container: 'wl-map',
        style: STYLES.dark,
        center: [10, 30],
        zoom: 1.3,
        minZoom: 1,
        projection: 'globe',
        language: lang,
    });
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right');
    if (!cfg.mapbox.token) {
        $('#wl-map').append(h('p', { class: 'wl-map-notice', role: 'status', text: t.mapUnavailable }));
    }

    const pinById = new Map(pins.map((p) => [p.id, p]));
    // 訪れた順 (旅のルート・前後移動)
    const ordered = [...pins].sort((a, b) => dateOf(a).localeCompare(dateOf(b)) || a.id - b.id);
    // まとまりの表紙: 写真のあるピンのうち pins の並びで最初のもの (cover が最小のもの)
    const NO_COVER = 1e9;
    const pinsGeoJSON = {
        type: 'FeatureCollection',
        features: pins.map((p, i) => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
            properties: { id: p.id, cover: p.photos.length ? i : NO_COVER },
        })),
    };
    const routeGeoJSON = {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: ordered.map((p) => [p.lng, p.lat]) },
        properties: {},
    };
    let routeOn = false;

    // スタイルを切り替えるとソースとレイヤーが消えるので、読み込むたびに追加し直す
    map.on('style.load', () => {
        if (!map.getFog()) map.setFog({ color: '#1c1c1e', 'high-color': '#0b1a33', 'space-color': '#000', 'star-intensity': 0.25 });
        map.addSource('wl-pins', {
            type: 'geojson',
            data: pinsGeoJSON,
            cluster: true,
            clusterMaxZoom: CLUSTER_MAX_ZOOM,
            clusterRadius: 56,
            clusterProperties: { cover: ['min', ['get', 'cover']] },
        });
        // 写真マーカーは HTML で描くため見えないレイヤー。ソースのタイルを読み込ませるためだけに置く
        map.addLayer({ id: 'wl-pins-hit', type: 'circle', source: 'wl-pins', paint: { 'circle-radius': 0, 'circle-opacity': 0 } });
        map.addSource('wl-route', { type: 'geojson', data: routeGeoJSON });
        map.addLayer({
            id: 'wl-route',
            type: 'line',
            source: 'wl-route',
            layout: { 'line-cap': 'round', 'line-join': 'round', visibility: routeOn ? 'visible' : 'none' },
            paint: { 'line-color': '#2997ff', 'line-width': 3, 'line-opacity': 0.85, 'line-dasharray': [0.1, 2.6] },
        });
    });

    // 写真マーカー (クラスタも同じ見た目で、件数バッジ付き)
    function markerElement({ photo, count = 0, label, onActivate }) {
        const inner = count
            ? h('div', { class: 'wl-marker wl-marker--cluster' },
                photo ? h('img', { src: photo.thumb, alt: '' }) : icon('photo_library'),
                h('span', { class: 'wl-marker-count', text: String(count) }))
            : h('div', { class: `wl-marker${photo ? '' : ' wl-marker--dot'}` },
                photo ? h('img', { src: photo.thumb, alt: '', loading: 'lazy' }) : icon('location_on'));
        const el = h('div', { class: 'wl-marker-wrap', role: 'button', tabindex: '0', 'aria-label': label, title: label }, inner);
        el.addEventListener('click', (e) => { e.stopPropagation(); onActivate(); });
        el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onActivate(); } });
        return el;
    }
    const markerCache = new Map(); // key → mapboxgl.Marker
    let shown = new Map();
    function buildMarker(f) {
        const coords = f.geometry.coordinates;
        const props = f.properties;
        if (props.cluster) {
            const coverPin = props.cover < NO_COVER ? pins[props.cover] : null;
            const el = markerElement({
                photo: coverPin && coverPin.photos[0],
                count: props.point_count,
                label: `${props.point_count} ${t.places}`,
                onActivate: () => map.getSource('wl-pins').getClusterExpansionZoom(props.cluster_id, (err, zoom) => {
                    if (!err) map.easeTo({ center: coords, zoom: Math.min(zoom, CLUSTER_MAX_ZOOM + 1) });
                }),
            });
            return new mapboxgl.Marker({ element: el, anchor: 'bottom' }).setLngLat(coords);
        }
        const p = pinById.get(props.id);
        const el = markerElement({ photo: p.photos[0], label: p.title, onActivate: () => openSheet(p) });
        return new mapboxgl.Marker({ element: el, anchor: 'bottom' }).setLngLat([p.lng, p.lat]);
    }
    function updateMarkers() {
        if (!map.getSource('wl-pins') || !map.isSourceLoaded('wl-pins')) return;
        const next = new Map();
        map.querySourceFeatures('wl-pins').forEach((f) => {
            const key = f.properties.cluster ? `c${f.properties.cluster_id}` : `p${f.properties.id}`;
            if (next.has(key)) return; // タイルの境目で同じ点が重複して返る
            let m = markerCache.get(key);
            if (!m) { m = buildMarker(f); markerCache.set(key, m); }
            next.set(key, m);
            if (!shown.has(key)) m.addTo(map);
        });
        shown.forEach((m, key) => { if (!next.has(key)) m.remove(); });
        shown = next;
    }
    map.on('render', updateMarkers);

    const fitAll = (animate = true) => {
        if (!pins.length) return;
        const bounds = new mapboxgl.LngLatBounds();
        pins.forEach((p) => bounds.extend([p.lng, p.lat]));
        map.fitBounds(bounds, { padding: 60, maxZoom: 12, duration: animate ? 1200 : 0 });
    };
    fitAll(false);
    const focusPin = (p, animate = true) => {
        const opts = { center: [p.lng, p.lat], zoom: Math.max(map.getZoom(), CLUSTER_MAX_ZOOM + 1) };
        if (animate) map.flyTo({ ...opts, duration: 800 }); else map.jumpTo(opts);
    };

    document.querySelectorAll('.wl-ctl').forEach((btn) => btn.addEventListener('click', () => {
        const ctl = btn.dataset.ctl;
        if (ctl === 'fit') fitAll();
        if (ctl === 'route') {
            routeOn = btn.getAttribute('aria-pressed') !== 'true';
            btn.setAttribute('aria-pressed', String(routeOn));
            if (map.getLayer('wl-route')) map.setLayoutProperty('wl-route', 'visibility', routeOn ? 'visible' : 'none');
        }
        if (ctl === 'layer') {
            const sat = btn.getAttribute('aria-pressed') !== 'true';
            btn.setAttribute('aria-pressed', String(sat));
            map.setStyle(sat ? STYLES.satellite : STYLES.dark);
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
        // Nominatim の boundingbox は [南, 北, 西, 東]
        if (bb) map.fitBounds([[bb[2], bb[0]], [bb[3], bb[1]]], { maxZoom: 14, duration: 1200 });
        else map.flyTo({ center: [Number(r.lon), Number(r.lat)], zoom: 12 });
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
            ? photos.map((ph) => h('figure', { class: 'wl-slide' },
                // 縦横比が枠と合わない写真の余白を、同じ写真のぼかしで埋める
                h('img', { class: 'wl-slide-bg', src: ph.thumb, alt: '', 'aria-hidden': 'true', onload: (e) => fitBlur(e.target.parentElement) }),
                h('img', { class: 'wl-slide-img', src: ph.url, alt: p.title, loading: 'lazy' })))
            : [h('div', { class: 'wl-slide wl-slide--empty' }, icon('photo_camera'), h('span', { text: t.noPhoto }))]));
        dots.replaceChildren(...photos.map((_, i) => h('button', {
            type: 'button', class: 'wl-dot', 'aria-label': `${i + 1} / ${photos.length}`, onclick: () => goSlide(i),
        })));
        slide = 0;
        track.scrollLeft = 0;
        updateDots();
    }
    // ぼかしが写真の縁から枠の端に向かってなめらかに黒へ消えるよう、写真の外側の幅 (--edge) と向きを測る
    function fitBlur(slide) {
        const bg = slide.querySelector('.wl-slide-bg');
        const w = slide.clientWidth;
        const hgt = slide.clientHeight;
        if (!bg || !bg.naturalWidth || !w || !hgt) return;
        const ratio = bg.naturalWidth / bg.naturalHeight;
        const tall = ratio < w / hgt;
        const fill = tall ? (hgt * ratio) / w : (w / ratio) / hgt; // 写真が枠を占める割合
        slide.dataset.fit = tall ? 'tall' : 'wide';
        slide.style.setProperty('--edge', `${Math.max(0, (1 - fill) / 2) * 100}%`);
    }
    const fitAllBlur = () => document.querySelectorAll('#wl-gallery-track .wl-slide').forEach(fitBlur);
    window.addEventListener('resize', fitAllBlur, { passive: true });

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
        requestAnimationFrame(fitAllBlur);
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
        focusPin(p);
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
        if (name === 'map') setTimeout(() => map.resize(), 0);
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

        // 小さな地図 (位置の確認・調整)。地図の読み込みは課金対象なので、初めて編集画面を開いたときに作る
        let mini = null;
        let miniMarker = null;
        function ensureMini() {
            if (mini) return;
            mini = new mapboxgl.Map({
                container: 'wl-editor-map',
                style: cfg.mapbox.editorStyle, // 位置合わせ用: 道路や建物まで見えるスタイル
                center: [139.76, 35.68],
                zoom: 4,
                language: lang,
            });
            mini.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right');
            mini.on('click', (e) => setLocation(e.lngLat.lat, e.lngLat.lng, { fly: false }));
        }

        function setLocation(lat, lng, { source = 'manual', fly = true, lookup = true } = {}) {
            f.lat.value = Number(lat).toFixed(6);
            f.lng.value = Number(lng).toFixed(6);
            locationSource = source;
            $('#wl-coords').textContent = `${Number(lat).toFixed(5)}, ${Number(lng).toFixed(5)}`;
            ensureMini();
            if (!miniMarker) {
                const el = h('div', { class: 'wl-marker-wrap wl-marker-wrap--edit' }, h('div', { class: 'wl-marker wl-marker--dot wl-marker--edit' }, icon('location_on')));
                miniMarker = new mapboxgl.Marker({ element: el, anchor: 'bottom', draggable: true }).setLngLat([lng, lat]).addTo(mini);
                miniMarker.on('dragend', () => { const ll = miniMarker.getLngLat(); setLocation(ll.lat, ll.lng, { fly: false }); });
            } else {
                miniMarker.setLngLat([lng, lat]);
            }
            if (fly) mini.jumpTo({ center: [lng, lat], zoom: Math.max(mini.getZoom(), 13) });
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
            ensureMini();
            setTimeout(() => {
                mini.resize();
                const here = { center: map.getCenter(), zoom: Math.max(map.getZoom(), 3) };
                if (pin) setLocation(pin.lat, pin.lng, { lookup: false });
                else if (at) setLocation(at.lat, at.lng);
                else if (miniMarker) { miniMarker.remove(); miniMarker = null; mini.jumpTo(here); }
                else mini.jumpTo(here);
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
        map.on('contextmenu', (e) => open(null, e.lngLat));
        // Mapbox はタッチの長押しで contextmenu を出さないので、自前で判定する
        let pressTimer = null;
        const cancelPress = () => clearTimeout(pressTimer);
        map.on('touchstart', (e) => {
            cancelPress();
            if (e.originalEvent.touches.length !== 1 || e.originalEvent.target.closest('.mapboxgl-marker')) return;
            const at = e.lngLat;
            pressTimer = setTimeout(() => open(null, at), 600);
        });
        ['touchend', 'touchcancel', 'movestart', 'zoomstart'].forEach((ev) => map.on(ev, cancelPress));
    }

    // ── 共有リンク (?pin=ID) で開く ──────────────────────────
    const initial = Number(new URLSearchParams(location.search).get('pin'));
    const initialPin = pins.find((p) => p.id === initial);
    if (initialPin) {
        focusPin(initialPin, false);
        openSheet(initialPin);
    }
})();
