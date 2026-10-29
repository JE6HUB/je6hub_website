// Liquid Glass ボタンの動き。
// ばね (spring) で拡大・押し込み・離したときのぷるんとした揺れを付け、
// ポインタの位置に光 (::after) を追従させる。WebGL ガラス (.liquid-glass-btn) は
// data-config の明るさ・ベベル・影も同じばねで連続的に変える (ライブラリの button
// モードは hover/press で値が瞬時に切り替わるため、こちらで置き換える)。
// 縮小版ナビ (.jh-glass-navbar) では、ホバー中のリンクへガラスのしずくが滑っていく。
// prefers-reduced-motion では揺れ・移動・波紋を出さず、状態だけを即座に切り替える。
(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const BUTTONS = '.liquid-glass-btn, .lounge-btn--glass, .jh-glass-navbar-link';

    // 減衰振動するばね。stiffness が大きいほど速く、damping が小さいほどよく揺れる
    class Spring {
        constructor(value, stiffness = 380, damping = 22) {
            this.value = value;
            this.target = value;
            this.velocity = 0;
            this.stiffness = stiffness;
            this.damping = damping;
        }
        step(dt) {
            const force = -this.stiffness * (this.value - this.target) - this.damping * this.velocity;
            this.velocity += force * dt;
            this.value += this.velocity * dt;
        }
        snap() { this.value = this.target; this.velocity = 0; }
        get settled() {
            return Math.abs(this.value - this.target) < 0.0005 && Math.abs(this.velocity) < 0.005;
        }
    }

    // 動いているものだけを 1 本の requestAnimationFrame で進める
    const active = new Set();
    let rafId = 0;
    let last = 0;
    const frame = (now) => {
        const dt = Math.min((now - last) / 1000 || 1 / 60, 1 / 20);
        last = now;
        for (const item of active) {
            // 固定刻みで積分し、フレームレートが落ちても揺れ方を変えない
            const steps = Math.ceil(dt / (1 / 240));
            for (let i = 0; i < steps; i++) item.springs.forEach((s) => s.step(dt / steps));
            item.render();
            if (item.springs.every((s) => s.settled)) {
                item.springs.forEach((s) => s.snap());
                item.render();
                active.delete(item);
            }
        }
        rafId = active.size ? requestAnimationFrame(frame) : 0;
    };
    const wake = (item) => {
        if (reduceMotion.matches) {
            item.springs.forEach((s) => s.snap());
            item.render();
            return;
        }
        active.add(item);
        if (!rafId) {
            last = performance.now();
            rafId = requestAnimationFrame(frame);
        }
    };

    const round = (n) => Math.round(n * 1000) / 1000;

    // LiquidGlass.init より前に呼ぶ。button モードを外し、元の設定を控えておく
    const prepareGlassConfig = (el) => {
        if (el.jhGlassBase || !el.dataset.config) return;
        let config;
        try { config = JSON.parse(el.dataset.config); } catch (_e) { return; }
        if (!config.button) return;
        delete config.button;
        el.jhGlassBase = {
            ...config,
            brightness: config.brightness ?? 0,
            zRadius: config.zRadius ?? 40,
            refraction: config.refraction ?? 0.69,
            shadowOpacity: config.shadowOpacity ?? 0.3,
            shadowSpread: config.shadowSpread ?? 10,
            shadowOffsetY: config.shadowOffsetY ?? 1,
        };
        el.dataset.config = JSON.stringify(config);
    };

    const attachButton = (el) => {
        if (el.jhGlassMotion) return;
        const isNavLink = el.classList.contains('jh-glass-navbar-link');
        const springs = {
            hover: new Spring(0, 260, 24),
            press: new Spring(0, 520, 20),
            // 拡大率と横長のつぶれは揺れやすく (ぷるん)
            scale: new Spring(1, 420, 14),
            squash: new Spring(0, 360, 13),
            x: new Spring(0, 220, 20),
            y: new Spring(0, 220, 20),
        };
        let lastConfig = '';
        const item = {
            springs: Object.values(springs),
            render() {
                const { hover, press, scale, squash, x, y } = springs;
                const sx = scale.value * (1 + squash.value);
                const sy = scale.value * (1 - squash.value);
                // ホバー中だけ、ポインタの方へ少し吸い寄せられる
                const pull = isNavLink ? 0 : Math.max(0, hover.value);
                const mx = x.value * 4 * pull;
                const my = y.value * 3 * pull;
                el.style.transform = reduceMotion.matches ? ''
                    : `translate(${mx.toFixed(2)}px, ${my.toFixed(2)}px) scale(${sx.toFixed(4)}, ${sy.toFixed(4)})`;
                el.style.setProperty('--jh-glass-x', `${((x.value + 1) * 50).toFixed(1)}%`);
                el.style.setProperty('--jh-glass-y', `${((y.value + 1) * 50).toFixed(1)}%`);
                el.style.setProperty('--jh-glass-glow', Math.max(0, hover.value + press.value * 0.6).toFixed(3));

                const base = el.jhGlassBase;
                if (!base) return;
                // WebGL ガラス: 浮くと明るく影が広がり、押すとベベルが平たく屈折が強まる
                const config = JSON.stringify({
                    ...base,
                    brightness: round(base.brightness + hover.value * 0.16 - press.value * 0.06),
                    zRadius: round(base.zRadius * (1 - press.value * 0.35)),
                    refraction: round(base.refraction * (1 + press.value * 0.3)),
                    shadowOpacity: round(base.shadowOpacity * (1 + hover.value * 0.4)),
                    shadowSpread: round(base.shadowSpread * (1 + hover.value * 0.6 - press.value * 0.3)),
                    shadowOffsetY: round(base.shadowOffsetY + hover.value * 5 - press.value * 3),
                });
                if (config !== lastConfig) {
                    lastConfig = config;
                    el.dataset.config = config;
                }
                // 位置 (transform) だけが動いたときも、背後の屈折を描き直させる
                el.jhGlassInstance?.markChanged(el);
            },
        };
        el.jhGlassMotion = item;
        el.classList.add('jh-glass-motion');

        const restTargets = () => {
            const { hover, press, scale, squash } = springs;
            scale.target = 1 + hover.target * (isNavLink ? 0.04 : 0.035) - press.target * 0.07;
            squash.target = press.target * 0.045;
        };
        const aim = (event) => {
            const rect = el.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const px = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            const py = ((event.clientY - rect.top) / rect.height) * 2 - 1;
            springs.x.target = Math.max(-1, Math.min(1, px));
            springs.y.target = Math.max(-1, Math.min(1, py));
        };
        const settle = () => {
            springs.x.target = 0;
            springs.y.target = -0.6; // 光は少し上で待つ
        };
        settle();
        springs.y.snap();

        const pressDown = () => {
            springs.press.target = 1;
            restTargets();
            wake(item);
        };
        const release = (bounce) => {
            if (springs.press.target === 0) return;
            springs.press.target = 0;
            restTargets();
            // 指を離した瞬間に少し弾ませる
            if (bounce && !reduceMotion.matches) {
                springs.scale.velocity += 1.0;
                springs.squash.velocity -= 0.7;
            }
            wake(item);
        };
        const ripple = (event) => {
            if (reduceMotion.matches) return;
            const rect = el.getBoundingClientRect();
            const rx = event && event.clientX !== undefined && rect.width
                ? ((event.clientX - rect.left) / rect.width) * 100 : 50;
            const ry = event && event.clientY !== undefined && rect.height
                ? ((event.clientY - rect.top) / rect.height) * 100 : 50;
            el.style.setProperty('--jh-ripple-x', `${rx.toFixed(1)}%`);
            el.style.setProperty('--jh-ripple-y', `${ry.toFixed(1)}%`);
            el.classList.remove('jh-glass-rippling');
            void el.offsetWidth; // アニメーションを最初からやり直す
            el.classList.add('jh-glass-rippling');
        };
        el.addEventListener('animationend', (event) => {
            if (event.animationName === 'jh-glass-ripple') el.classList.remove('jh-glass-rippling');
        });

        el.addEventListener('pointerenter', (event) => {
            if (event.pointerType === 'mouse' || event.pointerType === 'pen') {
                springs.hover.target = 1;
                restTargets();
            }
            aim(event);
            wake(item);
        });
        el.addEventListener('pointermove', (event) => {
            aim(event);
            wake(item);
        });
        el.addEventListener('pointerleave', () => {
            springs.hover.target = 0;
            release(false);
            settle();
            restTargets();
            wake(item);
        });
        el.addEventListener('pointerdown', (event) => {
            if (event.button !== 0) return;
            aim(event);
            pressDown();
            ripple(event);
        });
        el.addEventListener('pointerup', (event) => {
            release(true);
            // タッチはホバーが残らないので、離したら光を戻す
            if (event.pointerType === 'touch') {
                springs.hover.target = 0;
                settle();
                restTargets();
            }
        });
        el.addEventListener('pointercancel', () => {
            springs.hover.target = 0;
            release(false);
            settle();
            restTargets();
            wake(item);
        });

        // キーボードでも同じ手ごたえ (Enter / Space)
        el.addEventListener('keydown', (event) => {
            if ((event.key === 'Enter' || event.key === ' ') && !event.repeat) {
                springs.x.target = 0;
                springs.y.target = 0;
                pressDown();
                ripple(null);
            }
        });
        el.addEventListener('keyup', (event) => {
            if (event.key === 'Enter' || event.key === ' ') release(true);
        });
        el.addEventListener('focus', () => {
            if (!el.matches(':focus-visible')) return;
            springs.hover.target = 1;
            restTargets();
            wake(item);
        });
        el.addEventListener('blur', () => {
            springs.hover.target = 0;
            release(false);
            settle();
            restTargets();
            wake(item);
        });

        item.render();
    };

    // 縮小版ナビ: ホバー中のリンクの下へ、ガラスのしずくが伸び縮みしながら移動する
    const attachNavbarDrop = (nav) => {
        if (nav.jhGlassDrop) return;
        const drop = document.createElement('span');
        drop.className = 'jh-glass-navbar-drop';
        drop.setAttribute('aria-hidden', 'true');
        nav.prepend(drop);
        nav.classList.add('jh-glass-navbar--drop');
        const springs = {
            x: new Spring(0, 300, 24),
            w: new Spring(0, 300, 26),
            opacity: new Spring(0, 260, 26),
        };
        const item = {
            springs: Object.values(springs),
            render() {
                const { x, w, opacity } = springs;
                // 速く動いているほど横に伸び、縦に縮む
                const stretch = reduceMotion.matches ? 0 : Math.min(Math.abs(x.velocity) / 4000, 0.35);
                drop.style.width = `${Math.max(0, w.value).toFixed(2)}px`;
                drop.style.transform = `translate(${x.value.toFixed(2)}px, -50%) scale(${(1 + stretch).toFixed(4)}, ${(1 - stretch * 0.5).toFixed(4)})`;
                drop.style.opacity = Math.max(0, Math.min(1, opacity.value)).toFixed(3);
            },
        };
        nav.jhGlassDrop = item;
        const moveTo = (link) => {
            const navRect = nav.getBoundingClientRect();
            const rect = link.getBoundingClientRect();
            const x = rect.left - navRect.left - nav.clientLeft;
            const appearing = springs.opacity.target === 0 && springs.opacity.value < 0.05;
            springs.x.target = x;
            springs.w.target = rect.width;
            springs.opacity.target = 1;
            if (appearing) {
                // 見えていない状態からは、その場でふくらむ
                springs.x.value = x + rect.width / 2;
                springs.w.value = 0;
                springs.x.velocity = 0;
                springs.w.velocity = 0;
                springs.x.target = x;
            }
            wake(item);
        };
        nav.addEventListener('pointerover', (event) => {
            const link = event.target.closest('.jh-glass-navbar-link');
            if (link && nav.contains(link)) moveTo(link);
        });
        nav.addEventListener('focusin', (event) => {
            const link = event.target.closest('.jh-glass-navbar-link');
            if (link && link.matches(':focus-visible')) moveTo(link);
        });
        const hide = () => {
            springs.opacity.target = 0;
            wake(item);
        };
        nav.addEventListener('pointerleave', hide);
        nav.addEventListener('focusout', (event) => {
            if (!nav.contains(event.relatedTarget)) hide();
        });
        item.render();
    };

    const init = () => {
        document.querySelectorAll('.liquid-glass-btn').forEach(prepareGlassConfig);
        document.querySelectorAll(BUTTONS).forEach(attachButton);
        document.querySelectorAll('.jh-glass-navbar').forEach(attachNavbarDrop);
    };
    init();

    reduceMotion.addEventListener?.('change', () => {
        document.querySelectorAll('.jh-glass-motion').forEach((el) => el.jhGlassMotion.render());
    });

    // LiquidGlass.init の後に呼ぶ。移動中のボタンを再描画できるよう instance を覚える
    const bind = (instance, elements) => {
        elements.forEach((el) => { el.jhGlassInstance = instance; });
    };

    window.jhGlassMotion = { init, bind };
})();
