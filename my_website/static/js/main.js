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
                        name: 'Y.K. Nexus',
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
