/**
 * main.js
 * サイト全体で共通して使用するJavaScriptの初期化処理を記述します。
 */

document.addEventListener('DOMContentLoaded', () => {
    
    // ---------------------------------------------------------
    // 1. Django Messages (Toasts / Snackbar) の自動表示制御
    // ---------------------------------------------------------
    // ページロード時にDOM内に .toast クラスが存在すれば、MDBの機能を使って表示する
    const toastElList = [].slice.call(document.querySelectorAll('.toast'));
    const toastList = toastElList.map((toastEl) => {
        // MDBのToastインスタンスを作成 (5秒後に自動でフェードアウトして消える設定)
        const toast = new mdb.Toast(toastEl, {
            delay: 5000 
        });
        toast.show();
        return toast;
    });

    // ---------------------------------------------------------
    // 2. MDBootstrap のフォーム入力 (Material Design) 初期化
    // ---------------------------------------------------------
    // Djangoの forms.py で生成された input タグに対して、
    // Material Design特有の「文字を入力するとラベルが上にスライドする」
    // アニメーションを確実に動作させるためのスクリプトです。
    document.querySelectorAll('.form-outline').forEach((formOutline) => {
        // MDB Input コンポーネントを初期化
        new mdb.Input(formOutline).init();
    });

    // ---------------------------------------------------------
    // 3. Tooltip の初期化 (将来的なUI拡張用)
    // ---------------------------------------------------------
    // data-mdb-toggle="tooltip" が付与された要素にツールチップを適用
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-mdb-toggle="tooltip"]'));
    tooltipTriggerList.map((tooltipTriggerEl) => {
        return new mdb.Tooltip(tooltipTriggerEl);
    });

});

// Floating Playbar Close Button
document.addEventListener('DOMContentLoaded', () => {
    const floatingPlaybar = document.getElementById('floatingPlaybar');
    const playbar = document.querySelector('.floating-playbar');
    const closePlaybarBtn = document.querySelector('.play-control.close-playbar');
    const toggleBtn = playbar ? playbar.querySelector('[data-music-action="toggle"]') : null;
    const iconEl = toggleBtn ? toggleBtn.querySelector('[data-icon]') : null;
    const audioEl = playbar ? playbar.querySelector('audio.playbar-audio') : null;
    const openTriggers = document.querySelectorAll('[data-playbar-open="1"]');

    let musicKitInstance = null;
    let musicKitInitPromise = null;

    const openPlaybar = () => {
        if (!floatingPlaybar) return;
        floatingPlaybar.classList.remove('is-closed');
    };

    const closePlaybar = () => {
        if (!floatingPlaybar) return;
        floatingPlaybar.classList.add('is-closed');
        if (audioEl) {
            audioEl.pause();
            audioEl.currentTime = 0;
        }
        if (musicKitInstance && musicKitInstance.player) {
            try {
                musicKitInstance.player.stop();
            } catch (e) {
                // ignore
            }
        }
        if (iconEl) iconEl.textContent = 'play_arrow';
    };

    const ensurePreviewSrc = () => {
        if (!toggleBtn || !audioEl) return '';
        const previewUrl = toggleBtn.getAttribute('data-music-preview') || '';
        if (previewUrl && audioEl.src !== previewUrl) {
            audioEl.src = previewUrl;
        }
        return previewUrl;
    };

    const getAppleMusicSongId = () => {
        if (!toggleBtn) return '';
        return (toggleBtn.getAttribute('data-music-id') || '').trim();
    };

    const getMusicKit = async () => {
        if (musicKitInstance) return musicKitInstance;
        if (musicKitInitPromise) return musicKitInitPromise;

        musicKitInitPromise = (async () => {
            if (!window.MusicKit || !floatingPlaybar) return null;

            const tokenUrl = floatingPlaybar.getAttribute('data-apple-music-token-url') || '';
            if (!tokenUrl) return null;

            let token = '';
            try {
                const resp = await fetch(tokenUrl, { headers: { 'Accept': 'application/json' } });
                if (!resp.ok) return null;
                const data = await resp.json();
                token = (data && data.developer_token) ? data.developer_token : '';
            } catch (e) {
                return null;
            }

            if (!token) return null;

            try {
                window.MusicKit.configure({
                    developerToken: token,
                    app: {
                        name: 'JE6HUB.com',
                        build: '1.0.0',
                    },
                });
                const instance = window.MusicKit.getInstance();
                return instance;
            } catch (e) {
                return null;
            }
        })();

        musicKitInstance = await musicKitInitPromise;
        return musicKitInstance;
    };

    const fallbackToAppleMusic = () => {
        if (!toggleBtn) return;
        const directUrl = toggleBtn.getAttribute('data-music-url') || '';
        const artist = toggleBtn.getAttribute('data-music-artists') || '';
        const track = toggleBtn.getAttribute('data-music-track') || '';

        if (directUrl) {
            window.open(directUrl, '_blank');
            return;
        }

        const appleMusicSearchUrl = `https://music.apple.com/search?term=${encodeURIComponent((track + ' ' + artist).trim())}`;
        window.open(appleMusicSearchUrl, '_blank');
    };

    const pausePreviewAudio = () => {
        if (!audioEl) return;
        try {
            audioEl.pause();
        } catch (e) {
            // ignore
        }
    };

    const stopMusicKit = async () => {
        const mk = await getMusicKit();
        if (!mk || !mk.player) return;
        try {
            mk.player.stop();
        } catch (e) {
            // ignore
        }
    };

    const toggleFullTrackWithMusicKit = async () => {
        const mk = await getMusicKit();
        const songId = getAppleMusicSongId();

        if (!mk || !songId) return false;

        // Stop preview audio if switching to full-track
        pausePreviewAudio();

        try {
            if (!mk.isAuthorized) {
                await mk.authorize();
            }

            const player = mk.player;
            const isSameSong = player && player.nowPlayingItem && String(player.nowPlayingItem.id) === String(songId);

            if (player && player.isPlaying) {
                await player.pause();
                if (iconEl) iconEl.textContent = 'play_arrow';
                return true;
            }

            if (!isSameSong) {
                await mk.setQueue({ song: songId });
            }
            await player.play();
            if (iconEl) iconEl.textContent = 'pause';
            return true;
        } catch (e) {
            return false;
        }
    };

    const togglePlayback = async () => {
        // 1) Full track via MusicKit (if configured + id available)
        const fullOk = await toggleFullTrackWithMusicKit();
        if (fullOk) return;

        // 2) Preview audio
        const previewUrl = ensurePreviewSrc();
        if (!audioEl || !previewUrl) {
            // 3) Fallback to Apple Music
            fallbackToAppleMusic();
            return;
        }

        // Stop MusicKit if switching to preview
        await stopMusicKit();

        try {
            if (audioEl.paused) {
                await audioEl.play();
                if (iconEl) iconEl.textContent = 'pause';
            } else {
                audioEl.pause();
                if (iconEl) iconEl.textContent = 'play_arrow';
            }
        } catch (err) {
            fallbackToAppleMusic();
        }
    };

    if (closePlaybarBtn) {
        closePlaybarBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            closePlaybar();
        });
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openPlaybar();
            togglePlayback();
        });
    }

    if (audioEl) {
        audioEl.addEventListener('ended', () => {
            if (iconEl) iconEl.textContent = 'play_arrow';
        });
        audioEl.addEventListener('pause', () => {
            if (iconEl) iconEl.textContent = 'play_arrow';
        });
        audioEl.addEventListener('play', () => {
            if (iconEl) iconEl.textContent = 'pause';
        });
    }

    openTriggers.forEach((trigger) => {
        trigger.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openPlaybar();

            const wantsAutoplay = trigger.getAttribute('data-playbar-autoplay') === '1';
            if (wantsAutoplay) {
                togglePlayback();
            }
        });
    });
});

// Chip Button & Expandable Panel Toggle
document.addEventListener('DOMContentLoaded', () => {
    const bottomNav = document.getElementById('mobileBottomNav');
    const bottomNavToggle = document.querySelector('.bottom-nav-toggle-chip');
    const bottomNavToggleIcon = document.querySelector('.bottom-nav-toggle-icon');
    const bottomNavToggleLabel = document.querySelector('.bottom-nav-toggle-label');

    const syncBottomNavToggle = (isOpen) => {
        if (!bottomNavToggle || !bottomNavToggleIcon || !bottomNavToggleLabel) {
            return;
        }
        bottomNavToggleIcon.textContent = isOpen ? 'close' : 'menu';
        bottomNavToggleLabel.textContent = isOpen ? 'Close' : 'Menu';
        bottomNavToggle.setAttribute('aria-label', isOpen ? 'Close menu' : 'Open menu');
    };

    const closeBottomNav = () => {
        if (!bottomNav || !bottomNavToggle) {
            return;
        }
        bottomNav.classList.remove('is-open');
        bottomNav.classList.add('is-collapsed');
        bottomNavToggle.setAttribute('aria-expanded', 'false');
        bottomNav.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('bottom-nav-open');
        syncBottomNavToggle(false);
    };

    const openBottomNav = () => {
        if (!bottomNav || !bottomNavToggle) {
            return;
        }
        bottomNav.classList.add('is-open');
        bottomNav.classList.remove('is-collapsed');
        bottomNavToggle.setAttribute('aria-expanded', 'true');
        bottomNav.setAttribute('aria-hidden', 'false');
        document.body.classList.add('bottom-nav-open');
        syncBottomNavToggle(true);
    };

    if (bottomNav && bottomNavToggle) {
        closeBottomNav();
        bottomNavToggle.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (bottomNav.classList.contains('is-open')) {
                closeBottomNav();
            } else {
                openBottomNav();
            }
        });
    }

    const chipButtons = document.querySelectorAll('.nav-item-expandable');

    const collapseAllPanels = (exceptButton) => {
        chipButtons.forEach((btn) => {
            if (btn === exceptButton) return;
            btn.setAttribute('aria-expanded', 'false');
        });
        document.querySelectorAll('.expandable-panel.show').forEach((openPanel) => {
            const panelId = openPanel.getAttribute('data-panel');
            const ownerButton = document.querySelector(`.nav-item-expandable[data-panel="${panelId}"]`);
            if (ownerButton === exceptButton) return;
            openPanel.classList.remove('show');
        });
    };

    chipButtons.forEach((button) => {
        button.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const panelId = button.getAttribute('data-panel');
            const panel = document.querySelector(`.expandable-panel[data-panel="${panelId}"]`);
            if (panel) {
                const isShowing = panel.classList.contains('show');
                collapseAllPanels(button);
                if (isShowing) {
                    panel.classList.remove('show');
                    button.setAttribute('aria-expanded', 'false');
                } else {
                    panel.classList.add('show');
                    button.setAttribute('aria-expanded', 'true');
                }
            }
        });
    });

    document.addEventListener('click', (e) => {
            if (bottomNav && bottomNavToggle && !e.target.closest('#mobileBottomNav') && !e.target.closest('.bottom-nav-toggle-chip')) {
                closeBottomNav();
            }

        if (e.target.closest('.nav-item-expandable') || e.target.closest('.expandable-panel')) {
            return;
        }
        collapseAllPanels(null);
    });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeBottomNav();
                collapseAllPanels(null);
            }
        });
});

// Scroll-collapsing Nav → Condensed Glass Nav
document.addEventListener('DOMContentLoaded', () => {
    const fullNav = document.getElementById('jh-globalnav');
    const glassNav = document.getElementById('jh-glass-navbar');
    if (!fullNav || !glassNav) return;

    const SCROLL_THRESHOLD = 80;
    let lastState = null;
    let ticking = false;

    const syncNav = () => {
        const isScrolled = window.scrollY > SCROLL_THRESHOLD;
        if (isScrolled !== lastState) {
            fullNav.classList.toggle('jh-globalnav-hidden', isScrolled);
            glassNav.classList.toggle('jh-glass-navbar-visible', isScrolled);
            lastState = isScrolled;
        }
        ticking = false;
    };

    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(syncNav);
            ticking = true;
        }
    }, { passive: true });

    syncNav();
});

// Mobile Menu (734px 以下で表示される全画面メニュー)
document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('jh-menu-btn');
    const menu = document.getElementById('jh-mobile-menu');
    if (!button || !menu) return;

    const setOpen = (open) => {
        menu.hidden = !open;
        button.setAttribute('aria-expanded', String(open));
        document.body.classList.toggle('jh-menu-open', open);
    };

    button.addEventListener('click', () => setOpen(menu.hidden));
    menu.addEventListener('click', (e) => {
        if (e.target.closest('a')) setOpen(false);
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !menu.hidden) {
            setOpen(false);
            button.focus();
        }
    });
    // 画面を回転・拡大してデスクトップ幅になったら閉じる
    window.matchMedia('(max-width: 734px)').addEventListener('change', (e) => {
        if (!e.matches) setOpen(false);
    });
});

// お気に入りの曲のプレビュー再生 (.pf-play[data-track-src])
// ページ内のどの再生ボタンでも 1 つの <audio> を共有し、同時に 2 曲鳴らないようにする。
const TrackPreview = (() => {
    const audio = new Audio();
    audio.preload = 'none';
    let activeButton = null;

    const setState = (button, playing) => {
        if (!button) return;
        button.classList.toggle('is-playing', playing);
        const icon = button.querySelector('.pf-play-icon');
        if (icon) icon.textContent = playing ? 'pause' : 'play_arrow';
        const label = playing ? button.dataset.labelPause : button.dataset.labelPlay;
        if (label) button.setAttribute('aria-label', label);
        if (!playing) button.style.removeProperty('--pf-progress');
    };

    const stop = () => {
        audio.pause();
        setState(activeButton, false);
        activeButton = null;
    };

    const toggle = (button) => {
        if (button === activeButton && !audio.paused) {
            stop();
            return;
        }
        stop();
        activeButton = button;
        audio.src = button.dataset.trackSrc;
        setState(button, true);
        audio.play().catch(() => stop());
    };

    audio.addEventListener('timeupdate', () => {
        if (activeButton && audio.duration) {
            activeButton.style.setProperty('--pf-progress', `${(audio.currentTime / audio.duration) * 360}deg`);
        }
    });
    audio.addEventListener('ended', stop);

    document.addEventListener('click', (e) => {
        const button = e.target.closest('.pf-play[data-track-src]');
        if (!button) return;
        e.preventDefault();
        toggle(button);
    });

    return { stop };
})();

// プロフィールのモーダル: [data-profile="username"] をクリックすると開く
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('pf-modal');
    const body = document.getElementById('pf-modal-body');
    if (!modal || !body || typeof modal.showModal !== 'function') return;

    const cache = new Map();
    let opener = null;
    let closeTimer = null;

    const cardUrl = (username) => modal.dataset.cardUrl.replace('__username__', encodeURIComponent(username));

    const loadCard = async (username) => {
        if (!cache.has(username)) {
            cache.set(username, fetch(cardUrl(username), { headers: { 'X-Requested-With': 'fetch' } })
                .then((r) => { if (!r.ok) throw new Error(r.status); return r.text(); })
                .catch((err) => { cache.delete(username); throw err; }));
        }
        return cache.get(username);
    };

    const open = async (username, trigger) => {
        clearTimeout(closeTimer);
        opener = trigger;
        body.innerHTML = '<div class="pf-card pf-card--loading" aria-busy="true"><span class="pf-spinner"></span></div>';
        if (!modal.open) modal.showModal();
        // 次のフレームでクラスを付けて、表示アニメーションを走らせる
        requestAnimationFrame(() => modal.classList.add('is-open'));
        try {
            const html = await loadCard(username);
            if (!modal.open) return;
            body.innerHTML = html;
            body.firstElementChild?.classList.add('pf-card--enter');
        } catch {
            body.innerHTML = `<div class="pf-card pf-card--error"><p>${modal.dataset.error}</p></div>`;
        }
    };

    const close = () => {
        if (!modal.open) return;
        TrackPreview.stop();
        modal.classList.remove('is-open');
        // CSS のトランジションが終わってから閉じる
        closeTimer = setTimeout(() => {
            modal.close();
            if (opener && document.contains(opener)) opener.focus({ preventScroll: true });
        }, 250);
    };

    const triggerOf = (e) => e.target.closest('[data-profile]');

    // リンクやカードの中にあるトリガーも拾えるよう、キャプチャ段階で処理する
    document.addEventListener('click', (e) => {
        const trigger = triggerOf(e);
        if (!trigger || modal.contains(trigger)) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return; // 新しいタブで開く操作はそのまま
        e.preventDefault();
        e.stopPropagation();
        open(trigger.dataset.profile, trigger);
    }, true);

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const trigger = triggerOf(e);
        if (!trigger || trigger.tagName === 'A' || modal.contains(trigger)) return;
        e.preventDefault();
        e.stopPropagation();
        open(trigger.dataset.profile, trigger);
    }, true);

    modal.addEventListener('click', (e) => {
        // 背景 (dialog 自身) か閉じるボタンのクリックで閉じる
        if (e.target === modal || e.target.closest('[data-pf-close]')) close();
    });
    modal.addEventListener('cancel', (e) => {
        e.preventDefault();
        close();
    });
});

// サインアップ直後のプロフィール作成モーダル (accounts/_onboarding_modal.html)
// 「続ける」で枠はそのまま中身だけを入力画面に切り替え、同時に枠の大きさを中身に合わせて変える。
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('ob-modal');
    if (!modal || typeof modal.showModal !== 'function') return;

    const panel = document.getElementById('ob-panel');
    const intro = modal.querySelector('[data-ob-step="intro"]');
    const formStep = modal.querySelector('[data-ob-step="form"]');
    const form = document.getElementById('ob-form');
    const submitButton = form.querySelector('button[type="submit"]');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, reduceMotion ? 0 : ms));

    let morphTimer = null;
    let closing = false;

    // 中身を変えて、枠の大きさを変更前から変更後へトランジションさせる
    const morph = (change) => {
        const from = panel.getBoundingClientRect();
        change();
        panel.style.width = '';
        panel.style.height = '';
        const to = panel.getBoundingClientRect();
        panel.style.width = `${from.width}px`;
        panel.style.height = `${from.height}px`;
        void panel.offsetWidth; // 変更前の大きさを確定させてから、変更後の大きさを指定する
        panel.style.width = `${to.width}px`;
        panel.style.height = `${to.height}px`;
        clearTimeout(morphTimer);
        // 終わったら固定を外し、エラー表示などで中身が変わっても追従できるようにする
        morphTimer = setTimeout(() => {
            panel.style.width = '';
            panel.style.height = '';
        }, reduceMotion ? 0 : 550);
    };

    const close = async () => {
        if (closing) return;
        closing = true;
        modal.classList.add('is-leaving');
        await wait(400);
        modal.close();
        modal.remove();
    };

    const showForm = async () => {
        if (closing || !formStep.hidden) return;
        morph(() => {
            intro.classList.add('is-exiting');
            formStep.classList.add('is-entering');
            formStep.hidden = false;
        });
        modal.setAttribute('aria-labelledby', 'ob-form-title');
        await wait(120); // 出ていく文字が薄くなり始めてから、新しい文字を浮かび上がらせる
        formStep.classList.remove('is-entering');
        await wait(400);
        intro.hidden = true;
        intro.classList.remove('is-exiting');
        form.querySelector('input, textarea')?.focus({ preventScroll: true });
    };

    const showErrors = (errors) => {
        morph(() => {
            form.querySelectorAll('[data-ob-error]').forEach((el) => {
                const messages = errors[el.dataset.obError] || [];
                el.textContent = messages.join(' ');
                el.closest('.ob-field')?.classList.toggle('has-error', messages.length > 0);
            });
        });
    };

    const showToast = (message) => {
        const container = document.querySelector('.toast-container');
        if (!container || typeof mdb === 'undefined') return;
        const toast = document.createElement('div');
        toast.className = 'toast align-items-center text-bg-dark border-0 mb-2';
        toast.setAttribute('role', 'status');
        toast.style.cssText = 'background: rgba(28,28,30,0.8)!important; backdrop-filter: blur(20px); border-radius: 12px;';
        toast.innerHTML = '<div class="d-flex"><div class="toast-body fw-bold text-light"></div></div>';
        toast.querySelector('.toast-body').textContent = message;
        container.appendChild(toast);
        new mdb.Toast(toast, { delay: 5000 }).show();
    };

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        submitButton.disabled = true;
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' },
                credentials: 'same-origin',
            });
            const data = await response.json().catch(() => ({}));
            if (response.ok) {
                showErrors({});
                close();
                if (data.message) showToast(data.message);
                return;
            }
            showErrors(data.errors || { __all__: [form.dataset.error] });
        } catch {
            showErrors({ __all__: [form.dataset.error] });
        }
        submitButton.disabled = false;
    });

    modal.addEventListener('click', (e) => {
        if (e.target.closest('[data-ob-skip]')) close();
        else if (e.target.closest('[data-ob-continue]')) showForm();
    });
    // Esc はスキップと同じ扱いにする (いきなり消さず、アニメーションさせる)
    modal.addEventListener('cancel', (e) => {
        e.preventDefault();
        close();
    });

    modal.showModal();
    modal.querySelector('[data-ob-continue]').focus({ preventScroll: true });
    requestAnimationFrame(() => requestAnimationFrame(() => modal.classList.add('is-open')));
});

// Reveal Animations
document.addEventListener('DOMContentLoaded', () => {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15, rootMargin: '0px 0px -50px 0px' });

    document.querySelectorAll('.jh-reveal').forEach(el => observer.observe(el));
});
