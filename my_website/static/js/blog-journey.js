/**
 * Blogs — 旅する記事 (記事ページ)
 * 本文の地図シーン (.bk-scene) に合わせて、横に固定した Mapbox の地図のカメラを動かす。
 *
 * - シーンが画面の中ほどを越えると、その場所へ 3D で飛ぶ (ズーム・傾き・方位は書き手が決めた値)
 * - 最初のシーンより前は、旅全体が収まる俯瞰
 * - 訪れた順にルートを引き、進んだ区間を明るく描く。マーカーを押すとそのシーンへスクロール
 * - 到着後はゆっくり回り込む (動きを減らす設定のとき・地図を触ったときは止める)
 */
(() => {
    const root = document.querySelector('[data-journey]');
    const scenesEl = document.getElementById('journey-scenes');
    const cfgEl = document.getElementById('journey-config');
    if (!root || !scenesEl || !cfgEl) return;
    const scenes = JSON.parse(scenesEl.textContent);
    const cfg = JSON.parse(cfgEl.textContent);
    const cards = scenes.map((s) => document.querySelector(`[data-scene="${CSS.escape(s.id)}"]`));
    const hudNum = root.querySelector('[data-hud-num]');
    const hudLabel = root.querySelector('[data-hud-label]');
    const hudBar = root.querySelector('[data-hud-bar]');
    const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)');
    const pad = (n) => String(n).padStart(2, '0');
    const canvas = document.getElementById('journey-map');

    if (!window.mapboxgl || !cfg.mapbox.token || !scenes.length) {
        canvas.classList.add('is-unavailable');
        canvas.textContent = cfg.t.unavailable;
    }
    const hasMap = !canvas.classList.contains('is-unavailable');
    let map = null;
    const markers = [];

    const coords = scenes.map((s) => [s.lng, s.lat]);
    const overview = () => {
        if (scenes.length === 1) return { center: coords[0], zoom: 3, pitch: 0, bearing: 0 };
        const b = new mapboxgl.LngLatBounds(coords[0], coords[0]);
        coords.forEach((c) => b.extend(c));
        const cam = map.cameraForBounds(b, { padding: 80, maxZoom: 9 }) || { center: coords[0], zoom: 2 };
        return { ...cam, pitch: 0, bearing: 0 };
    };

    if (hasMap) {
        mapboxgl.accessToken = cfg.mapbox.token;
        map = new mapboxgl.Map({
            container: canvas,
            style: cfg.mapbox.style,
            projection: 'globe',
            center: coords[0],
            zoom: 1.4,
            scrollZoom: false, // ページのスクロールを奪わない
            cooperativeGestures: false,
            attributionControl: true,
            language: document.documentElement.lang || undefined,
        });
        map.addControl(new mapboxgl.NavigationControl({ showCompass: true, visualizePitch: true }), 'bottom-right');

        map.on('style.load', () => {
            map.setFog({
                color: 'rgb(24, 24, 28)', 'high-color': 'rgb(36, 52, 92)', 'horizon-blend': 0.08,
                'space-color': 'rgb(6, 6, 10)', 'star-intensity': 0.35,
            });
            if (!map.getSource('journey-dem')) {
                map.addSource('journey-dem', { type: 'raster-dem', url: 'mapbox://mapbox.mapbox-terrain-dem-v1', tileSize: 512, maxzoom: 14 });
            }
            map.setTerrain({ source: 'journey-dem', exaggeration: 1.25 });
            const line = (c) => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: c } });
            map.addSource('journey-route', { type: 'geojson', data: line(coords) });
            map.addSource('journey-done', { type: 'geojson', data: line(coords.slice(0, 1)) });
            map.addLayer({
                id: 'journey-route', type: 'line', source: 'journey-route',
                layout: { 'line-cap': 'round', 'line-join': 'round' },
                paint: { 'line-color': '#ffffff', 'line-opacity': 0.28, 'line-width': 2, 'line-dasharray': [0.5, 2] },
            });
            map.addLayer({
                id: 'journey-done', type: 'line', source: 'journey-done',
                layout: { 'line-cap': 'round', 'line-join': 'round' },
                paint: { 'line-color': cfg.accent, 'line-width': 3.5, 'line-blur': 0.5 },
            });
            map.jumpTo(overview());
            update(true);
        });

        scenes.forEach((s, i) => {
            const el = document.createElement('button');
            el.type = 'button';
            el.className = 'journey-marker';
            el.setAttribute('aria-label', `${pad(i + 1)} ${s.label || ''}`);
            el.innerHTML = s.thumb
                ? `<img src="${encodeURI(s.thumb)}" alt=""><span class="journey-marker-num">${i + 1}</span>`
                : `<span class="journey-marker-num">${i + 1}</span>`;
            el.addEventListener('click', () => {
                if (cards[i]) cards[i].scrollIntoView({ behavior: REDUCED.matches ? 'auto' : 'smooth', block: 'center' });
            });
            markers.push(new mapboxgl.Marker({ element: el, anchor: 'bottom' }).setLngLat(coords[i]).addTo(map));
        });

        // 触ったら自動の回り込みを止める
        ['dragstart', 'rotatestart', 'pitchstart', 'zoomstart'].forEach((ev) => map.on(ev, (e) => {
            if (e.originalEvent) userTouched = true;
        }));
    }

    let active = -2; // -1 = 俯瞰
    let userTouched = false;
    let orbitTimer = 0;

    const orbit = (s) => {
        clearTimeout(orbitTimer);
        if (REDUCED.matches) return;
        map.once('moveend', () => {
            orbitTimer = setTimeout(() => {
                if (userTouched || active < 0 || scenes[active] !== s) return;
                map.easeTo({ bearing: s.bearing + 18, duration: 30000, easing: (t) => t });
            }, 400);
        });
    };

    const go = (index, instant) => {
        if (!map || !map.isStyleLoaded()) return;
        userTouched = false;
        const s = scenes[index];
        const cam = index < 0 ? overview() : { center: [s.lng, s.lat], zoom: s.zoom, pitch: s.pitch, bearing: s.bearing };
        if (instant || REDUCED.matches) map.jumpTo(cam);
        else map.flyTo({ ...cam, duration: 2800, curve: 1.5, essential: true });
        const done = map.getSource('journey-done');
        if (done) done.setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: coords.slice(0, Math.max(1, index + 1)) } });
        markers.forEach((m, i) => {
            m.getElement().classList.toggle('is-active', i === index);
            m.getElement().classList.toggle('is-past', i < index);
        });
        if (index >= 0) orbit(s);
    };

    // 画面の 55% の高さを越えたシーンのうち最後のものを「今いる場所」にする
    function update(force = false) {
        const line = window.innerHeight * 0.55;
        let current = -1;
        cards.forEach((c, i) => { if (c && c.getBoundingClientRect().top < line) current = i; });
        cards.forEach((c, i) => c && c.classList.toggle('is-current', i === current));
        if (current !== active || force) {
            const instant = active === -2;
            active = current;
            hudNum.textContent = current < 0 ? '—' : `${pad(current + 1)} / ${pad(scenes.length)}`;
            hudLabel.textContent = current < 0 ? cfg.t.start : (scenes[current].label || cfg.t.here);
            go(current, instant);
        }
        // 旅全体 (最初のシーン〜記事の終わり) のうち、どこまで読んだか
        const first = cards.find(Boolean);
        if (first) {
            const top = first.getBoundingClientRect().top + window.scrollY - line;
            const rect = root.getBoundingClientRect();
            const end = rect.bottom + window.scrollY - window.innerHeight;
            const p = end > top ? (window.scrollY - top) / (end - top) : 1;
            hudBar.style.transform = `scaleX(${Math.max(0, Math.min(1, p)).toFixed(4)})`;
        }
    }

    let ticking = false;
    window.addEventListener('scroll', () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => { ticking = false; update(); });
    }, { passive: true });
    window.addEventListener('resize', () => { if (map) map.resize(); update(); });
    if (!hasMap) update(true);
})();
