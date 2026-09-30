/**
 * Blogs — 最新記事カルーセル
 * 一定間隔で次のスライドへ自動スクロールする。進行はアクティブなドットの
 * 進捗アニメーション (CSS) が終わったタイミングで行うため、一時停止は
 * animation-play-state を止めるだけで済む。
 * 停止条件: 再生ボタンで停止 / キーボードフォーカス中 / 画面外 / タブ非表示。
 * (ホバーでは止めない: 動いた先にマウスがあるだけで止まり、壊れて見えるため)
 */
(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function initCarousel(root) {
        const track = root.querySelector('.blog-carousel-track');
        const slides = Array.from(track.querySelectorAll('.blog-slide'));
        const dots = Array.from(root.querySelectorAll('.blog-dot'));
        const playBtn = root.querySelector('.blog-carousel-play');
        if (slides.length < 2 || !playBtn) return;

        root.style.setProperty('--carousel-interval', `${Number(root.dataset.interval) || 5000}ms`);

        let index = 0;
        let userPaused = reduceMotion; // 視差効果を減らす設定の場合は停止状態で開始
        let focused = false;
        let inView = false;

        const scrollTargetFor = (i) => slides[i].offsetLeft - parseFloat(getComputedStyle(track).paddingLeft);

        function updatePlaying() {
            const playing = !userPaused && !focused && inView && !document.hidden;
            root.classList.toggle('is-playing', playing);
        }

        function setActive(i) {
            index = i;
            dots.forEach((dot, n) => {
                const active = n === i;
                // クラスを付け直して進捗アニメーションを最初から再生させる
                dot.classList.remove('is-active');
                if (active) {
                    void dot.offsetWidth;
                    dot.classList.add('is-active');
                    dot.setAttribute('aria-current', 'true');
                } else {
                    dot.removeAttribute('aria-current');
                }
            });
        }

        function goTo(i) {
            const next = (i + slides.length) % slides.length;
            setActive(next);
            track.scrollTo({ left: scrollTargetFor(next), behavior: reduceMotion ? 'auto' : 'smooth' });
        }

        // 進捗が満了したら次へ
        root.addEventListener('animationend', (e) => {
            if (e.target.classList.contains('blog-dot-fill')) goTo(index + 1);
        });

        dots.forEach((dot, n) => dot.addEventListener('click', () => goTo(n)));

        function renderPlayButton() {
            playBtn.classList.toggle('is-paused', userPaused);
            playBtn.setAttribute('aria-label', userPaused ? playBtn.dataset.labelPlay : playBtn.dataset.labelPause);
        }

        playBtn.addEventListener('click', () => {
            userPaused = !userPaused;
            renderPlayButton();
            updatePlaying();
        });

        // 手動スクロール (スワイプ・トラックパッド) 後は、最も近いスライドをアクティブに
        let scrollTimer;
        track.addEventListener('scroll', () => {
            clearTimeout(scrollTimer);
            scrollTimer = setTimeout(() => {
                let nearest = 0;
                let best = Infinity;
                slides.forEach((_, n) => {
                    const d = Math.abs(scrollTargetFor(n) - track.scrollLeft);
                    if (d < best) { best = d; nearest = n; }
                });
                if (nearest !== index) setActive(nearest);
            }, 120);
        }, { passive: true });

        track.addEventListener('focusin', () => { focused = true; updatePlaying(); });
        track.addEventListener('focusout', () => { focused = false; updatePlaying(); });
        document.addEventListener('visibilitychange', updatePlaying);

        new IntersectionObserver(([entry]) => {
            inView = entry.isIntersecting;
            updatePlaying();
        }, { threshold: 0.35 }).observe(root);

        renderPlayButton();
        updatePlaying();
    }

    document.querySelectorAll('[data-carousel]').forEach(initCarousel);
})();
