# LiquidGlass — WebGL Glass Effects for the Web

> **公式サイト**: [https://liquid-glass.ybouane.com](https://liquid-glass.ybouane.com)  
> **GitHub**: [https://github.com/ybouane/liquidglass](https://github.com/ybouane/liquidglass)  
> **npm**: `@ybouane/liquidglass`

リアルな屈折・ぼかし・色収差・ライティング効果を、WebGLシェーダーを用いて任意のHTML要素に適用するJavaScript/TypeScriptライブラリ。

---

## インストール

### npm

```bash
npm install @ybouane/liquidglass
```

### CDN（インストール不要）

```javascript
import { LiquidGlass } from 'https://cdn.jsdelivr.net/npm/@ybouane/liquidglass/dist/index.js';
```

---

## 基本的な使い方

```javascript
import { LiquidGlass } from '@ybouane/liquidglass';

const instance = await LiquidGlass.init({
    root: document.querySelector('#my-root'),
    glassElements: document.querySelectorAll('.glass'),
});

// 後で破棄:
instance.destroy();
```

---

## HTML構造の要件

### 必須ルール

| ルール | 説明 |
|--------|------|
| **root は positioned container** | `position: relative` が必要 |
| **glass要素はrootの直接の子** | ネストされたglass要素は`init()`時に警告が出て拒否される |
| **rootの背景は見えない** | シェーダーはrootの*子要素*をサンプリングするため、root自体の背景画像やパディングは無視される |
| **`<canvas>`が自動注入される** | glass要素の最初の子として挿入されるため、`:first-child`セレクタは避けること |

### 正しい構造の例

```html
<!-- root: positioned container -->
<div id="my-root" style="position: relative; overflow: hidden;">

    <!-- 背景要素（rootの直接の子、glass が屈折する対象） -->
    <img src="background.jpg" alt="" style="position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;">

    <!-- テキストなどの非glass要素 -->
    <div style="position: relative; z-index: 2; pointer-events: none;">
        <h1>タイトル</h1>
    </div>

    <!-- Glass要素（rootの直接の子！） -->
    <a href="#" class="glass-btn" id="glass-btn-1">
        <span class="label">ボタン</span>
    </a>
</div>
```

### `.label` パターン

公式サイトではすべてのglass要素のテキストを `<span class="label">` で囲み、以下のCSSを適用している：

```css
.glass-element .label {
    position: relative;
    z-index: 2;
    pointer-events: none;
    display: flex;
    align-items: center;
    gap: 8px;
    filter: drop-shadow(0px 0px 6px #000000); /* 暗い背景での視認性 */
}
```

---

## 設定オプション（data-config）

各glass要素は `data-config`（JSON文字列）で個別設定するか、`defaults` オプションでグローバル設定できる。

### 全パラメータ一覧

| オプション | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `blurAmount` | number | `0` | 背景ぼかしの強さ（0 = シャープ、1 = 最大ブラー） |
| `refraction` | number | `0.69` | 光の屈折量 |
| `chromAberration` | number | `0.05` | エッジの色収差（にじみ） |
| `edgeHighlight` | number | `0.05` | 内側の光彩／リムライティング |
| `specular` | number | `0` | スペキュラーハイライト（Blinn-Phong） |
| `fresnel` | number | `1` | 視射角でのフレネル反射 |
| `cornerRadius` | number | `65` | 角丸の半径（CSS px） |
| `zRadius` | number | `40` | ベベルの深さ（曲率） |
| `brightness` | number | `0` | 明るさ調整（-0.5 〜 0.5） |
| `saturation` | number | `0` | 彩度（-1 〜 1） |
| `shadowOpacity` | number | `0.3` | ドロップシャドウの不透明度 |
| `floating` | boolean | `false` | ドラッグ移動を有効化 |
| `button` | boolean | `false` | ボタンモード（ホバー/プレスのシェーダーフィードバック） |
| `bevelMode` | number | `0` | 0 = 両凸ピル、1 = ドーム（平底） |

### HTMLでの設定方法

```html
<div class="glass-element" 
     data-config='{"button":true, "cornerRadius":28, "blurAmount":0.25, "brightness":-0.15}'>
    <span class="label">テキスト</span>
</div>
```

### JavaScriptでの設定方法

```javascript
element.dataset.config = JSON.stringify({
    button: true,
    cornerRadius: 28,
    blurAmount: 0.25,
    brightness: -0.15,
});
```

---

## プリセット例

### フロストガラス（すりガラス）

```javascript
element.dataset.config = JSON.stringify({
    blurAmount: 0.25,
    cornerRadius: 30,
});
```

### ダークガラス

```javascript
element.dataset.config = JSON.stringify({
    brightness: -0.3,
    blurAmount: 0.25,
    cornerRadius: 50,
});
```

### ボタンモード

ホバーで明るくなり、プレスでベベルが平坦化しシャドウが深くなる：

```javascript
element.dataset.config = JSON.stringify({
    button: true,
    cornerRadius: 24,
});
```

### ドーム拡大鏡

```javascript
element.dataset.config = JSON.stringify({
    bevelMode: 1,
    cornerRadius: 50,
    zRadius: 50,
    floating: true,
    blurAmount: 0,
    refraction: 1.2,
});
```

---

## 複数ルートの使い方

公式サイトのHEROセクションでは3つのルートを使用：

```javascript
// メインルート（ボタン、フローティングパネル、タブインジケータ）
const heroInstance = await LiquidGlass.init({
    root: document.getElementById('hero-root'),
    glassElements: document.querySelectorAll(
        '.hero-title, #glass-btn-1, #glass-btn-2, #glass-fp1, #glass-fp2, #glass-fp3, #glass-tab-indicator'
    ),
});

// ビデオコントロール（独自ルート）
await LiquidGlass.init({
    root: document.getElementById('video-root'),
    glassElements: [document.getElementById('glass-video-ctrl')],
});

// ドーム拡大鏡（独自ルート）
await LiquidGlass.init({
    root: document.getElementById('magnifier-root'),
    glassElements: [document.getElementById('glass-magnifier')],
});
```

> [!IMPORTANT]
> 複数のLiquidGlassルートは屈折を共有できない。あるルートのglass要素は、別のルートのglass要素が描画しているものを見ることはできない。

---

## APIリファレンス

### `LiquidGlass.init(options)` — 初期化

```javascript
const instance = await LiquidGlass.init({
    root: HTMLElement,           // positioned container
    glassElements: NodeList,     // rootの直接の子要素
    defaults: { ... },           // オプション: グローバルデフォルト設定
});
```

- **非同期**（async） — フォントCSSのプリフェッチ、glassコンテンツのプリキャプチャ、静的コンテンツのプリウォームがすべて完了してから解決される
- 遅い接続では100–500ms

### `instance.destroy()` — 破棄

```javascript
instance.destroy();
```

### `instance.markChanged(element?)` — 変更通知

```javascript
// 特定の要素が変更されたことを通知
instance.markChanged(element);

// 引数なし: すべてを無効化
instance.markChanged();
```

ライブラリが自動検知できない変更（`<canvas>`の再描画、`<img>`の差し替え、CSSプロパティのトグル）の後に呼び出す。指定した要素と重なるglassのみ再レンダリングされる。

### `instance.fps` — FPS取得

```javascript
setInterval(() => {
    console.log(instance.fps + ' FPS');
}, 500);
```

### `invalidateFontEmbedCache()` — フォントキャッシュクリア

動的にフォントスタイルシートを読み込んだ後に呼び出し、次の `init()` でフォント埋め込みキャッシュを再構築させる。

---

## 動的コンテンツの処理

### `data-dynamic` 属性

毎フレーム変化するコンテンツ（アニメーション、カウンター、チャート）には `data-dynamic` を付与：

```html
<div class="hero-video-wrap" id="video-root" data-dynamic>
    <video src="video.mp4" autoplay muted loop playsinline></video>
    <!-- ... -->
</div>
```

> [!WARNING]
> - `data-dynamic` はrootの直接の子要素のみ有効
> - `<video>` 要素はライブラリが自動検出するため `data-dynamic` 不要
> - ワンショットの更新には `data-dynamic` ではなく `instance.markChanged()` を使用すること（アイドルフレームでのコスト無し）

---

## 制約事項と注意点

### 構造

- Glass要素はrootの**直接の子**でなければならない
- root自体はキャプチャされない → 背景はroot内のsibling要素に配置する
- `<canvas>`がglass要素の最初の子として注入される → `:first-child`セレクタを避ける
- 複数のLiquidGlassルートは屈折を共有しない

### パフォーマンス

- DOM→Canvasのキャプチャは重い処理。ラッパーは小さく浅く保つ
- `data-dynamic` は毎フレーム再キャプチャを発生させるため、本当に必要な場合のみ使用
- 各インスタンスは独自のWebGLコンテキストを開く（ブラウザの上限は通常16）
- ウィンドウリサイズは全てを再キャプチャする

### テキスト・フォント

- **Webフォントは `init()` 前にロード**が必要。CORS対応ヘッダー付きで配信されること
  - Google Fonts、jsdelivr、unpkg はそのまま動作
- クロスオリジンの `<img>` には `crossorigin="anonymous"` が必要（汚染されたcanvasはテクスチャアップロードを壊す）

### フォント待機パターン（公式サイトより）

```javascript
// フォントの読み込みを待ってからinit
if (document.fonts && document.fonts.ready) {
    await document.fonts.ready;
}

const instance = await LiquidGlass.init({ ... });
```

---

## 公式サイトの実装パターン（Hero Section）

公式サイトのHeroセクションの構造:

```html
<div id="hero-root" style="position: relative; overflow: hidden;">

    <!-- 背景画像（直接の子） -->
    <img class="hero-bg" src="background.avif" alt=""
         style="position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;">

    <!-- タイトル（glass要素） -->
    <div class="hero-title">
        <h1>Liquid Glass</h1>
        <p class="subtitle">説明テキスト</p>
    </div>

    <!-- ボタン（glass要素、直接の子、grid-areaで配置） -->
    <a href="#" class="hero-btn" id="glass-btn-1">
        <span class="label">
            <svg>...</svg>
            ボタンテキスト
        </span>
    </a>

    <!-- フローティングパネル（glass要素） -->
    <div class="float-panel" id="glass-fp1">
        <span class="label">Regular Glass</span>
    </div>
</div>
```

公式のボタン設定:

```javascript
document.getElementById('glass-btn-1').dataset.config = JSON.stringify({
    button: true,
    cornerRadius: 28,
    blurAmount: 0.3,
    brightness: -0.1,
});
```

公式のフローティングパネル3種:

```javascript
// Regular Glass
{ floating: true, cornerRadius: 40, blurAmount: 0 }

// Frosted Glass
{ floating: true, cornerRadius: 40, blurAmount: 0.5 }

// Dark Glass
{ floating: true, cornerRadius: 40, brightness: -0.3, blurAmount: 0.4 }
```

---

## Playgroundパラメータ範囲

インタラクティブプレイグラウンドで使用される各パラメータの範囲：

| パラメータ | min | max | step | デフォルト |
|-----------|-----|-----|------|-----------|
| `blurAmount` | 0 | 1 | 0.01 | 0.25 |
| `refraction` | 0 | 2 | 0.01 | 0.69 |
| `chromAberration` | 0 | 0.3 | 0.005 | 0.05 |
| `edgeHighlight` | 0 | 1 | 0.01 | 0.05 |
| `specular` | 0 | 1 | 0.01 | 0 |
| `fresnel` | 0 | 2 | 0.01 | 1 |
| `distortion` | 0 | 1 | 0.01 | 0 |
| `cornerRadius` | 0 | 100 | 1 | 40 |
| `zRadius` | 1 | 100 | 1 | 40 |
| `opacity` | 0 | 1 | 0.01 | 1 |
| `saturation` | -1 | 1 | 0.01 | 0 |
| `brightness` | -0.5 | 0.5 | 0.01 | 0 |
| `shadowOpacity` | 0 | 1 | 0.01 | 0.3 |
| `shadowSpread` | 0 | 40 | 1 | 10 |
| `bevelMode` | 0 | 1 | 1 | 0 |
