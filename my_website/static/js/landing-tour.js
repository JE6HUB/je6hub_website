// ホームの UI ツアー動画。
// - 画面に近づいたら読み込みを始め、見えている間だけ再生する (帯域と電池の節約)。
// - 再生中は動画の上端・下端の色を読み取り、上下の帯 (--tour-top / --tour-bottom) に
//   反映して、動画の境目をページに溶かす。
// - 「視差効果を減らす」設定の人には再生せず、静止画の端の色だけ合わせる。
(() => {
    const root = document.querySelector('[data-landing-tour]');
    if (!root) return;
    const media = root.querySelector('.landing-tour-media');
    const video = root.querySelector('.landing-tour-video');
    const still = root.querySelector('.landing-tour-still');
    const toggle = root.querySelector('.landing-tour-toggle');

    // ── 端の色を読み取る ─────────────────────────────
    const W = 32, H = 18; // 16:9 の縮小版で十分
    const canvas = document.createElement('canvas');
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });

    const rowColor = (data, y) => {
        let r = 0, g = 0, b = 0;
        for (let x = 0; x < W; x++) {
            const i = (y * W + x) * 4;
            r += data[i]; g += data[i + 1]; b += data[i + 2];
        }
        return `rgb(${Math.round(r / W)}, ${Math.round(g / W)}, ${Math.round(b / W)})`;
    };

    const sampleEdges = (source) => {
        try {
            ctx.drawImage(source, 0, 0, W, H);
            const data = ctx.getImageData(0, 0, W, H).data;
            // object-fit: cover で上下が切り取られている場合は、実際に見えている端の行を読む
            const box = media.getBoundingClientRect();
            const visible = Math.min(1, box.height / (box.width * 9 / 16));
            const inset = Math.round(((1 - visible) / 2) * (H - 1));
            root.style.setProperty('--tour-top', rowColor(data, inset));
            root.style.setProperty('--tour-bottom', rowColor(data, H - 1 - inset));
        } catch {
            // 読み取れない場合 (まだデコード前など) は前の色のまま
        }
    };

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!video || reduceMotion.matches || !('IntersectionObserver' in window)) {
        // 静止画のまま。端の色だけ合わせる
        if (still.complete) sampleEdges(still);
        else still.addEventListener('load', () => sampleEdges(still), { once: true });
        return;
    }

    // ── 動画 ─────────────────────────────────────────
    let pausedByUser = false;
    let inView = false;

    root.classList.add('is-video');
    toggle.hidden = false;

    const setToggle = (paused) => {
        toggle.classList.toggle('is-paused', paused);
        toggle.setAttribute('aria-label', paused ? toggle.dataset.labelPlay : toggle.dataset.labelPause);
    };

    const play = () => {
        if (pausedByUser || !inView) return;
        video.play().catch(() => {
            // 省電力モードなどで自動再生できないときは、再生ボタンで利用者に任せる
            pausedByUser = true;
            setToggle(true);
        });
    };

    // 再生中は約 8 回/秒 端の色を読む (CSS 側で 0.45 秒かけて補間する)
    let lastSample = 0;
    const onFrame = (now) => {
        if (video.paused || video.ended) return;
        if (now - lastSample > 120) {
            lastSample = now;
            sampleEdges(video);
        }
        schedule();
    };
    const schedule = () => {
        if ('requestVideoFrameCallback' in video) video.requestVideoFrameCallback(onFrame);
        else requestAnimationFrame(onFrame);
    };

    video.addEventListener('playing', () => {
        root.classList.add('is-playing');
        schedule();
    });
    // ボタンの表示は「利用者が止めたか」だけを表す (画面外で止まったときは変えない)
    video.addEventListener('play', () => setToggle(false));
    video.addEventListener('pause', () => {
        sampleEdges(video);
        if (pausedByUser) setToggle(true);
    });

    toggle.addEventListener('click', () => {
        pausedByUser = !video.paused;
        if (pausedByUser) video.pause();
        else play();
    });

    // 少し手前 (1 画面分) で読み込みを始める
    new IntersectionObserver((entries, observer) => {
        if (entries.some((e) => e.isIntersecting)) {
            video.preload = 'auto';
            video.load();
            observer.disconnect();
        }
    }, { rootMargin: '100% 0px' }).observe(root);

    // 3 割以上見えている間だけ再生する
    new IntersectionObserver(([entry]) => {
        inView = entry.isIntersecting;
        if (inView) play();
        else video.pause();
    }, { threshold: 0.3 }).observe(media);

    // タブを切り替えたら止め、戻ったら (見えていれば) 再開する
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) video.pause();
        else play();
    });
})();
