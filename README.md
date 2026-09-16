# je6hub Website

Django製の個人ポートフォリオサイト。"liquid glass"（iOSライクなガラスモーフィズム）デザインを採用し、写真×地図（WanderLens）、コミュニティチャット（Lounge）、Apple Music連携プロフィールなどの機能を持つ。

## 目次

- [構成概要](#構成概要)
- [ディレクトリ構成](#ディレクトリ構成)
- [アプリ構成](#アプリ構成)
- [ローカル開発](#ローカル開発)
- [環境変数](#環境変数)
- [Dockerでの起動（本番想定）](#dockerでの起動本番想定)
- [テスト](#テスト)
- [CI](#ci)
- [本番デプロイのチェックリスト](#本番デプロイのチェックリスト)

## 構成概要

| レイヤ | 技術 |
|---|---|
| バックエンド | Django 6.0 (MVT, サーバーサイドレンダリング) |
| データベース | PostgreSQL |
| フロントエンド | Django Template + MDBootstrap (Material Design) + 自前のliquid glass CSS |
| 静的ファイル配信 | WhiteNoise（Dockerコンテナ単体で配信、Nginx等が無くても動作） |
| 認証 | Django標準認証 + カスタムユーザーモデル (`accounts.CustomUser`) |
| アプリケーションサーバー | Gunicorn |
| コンテナ化 | Docker / docker-compose (web + postgres) |
| CI | GitHub Actions（`manage.py check` + `pytest`） |

## ディレクトリ構成

```
.
├── Dockerfile                 # 本番イメージのビルド定義
├── docker-compose.yml         # web(Django) + db(PostgreSQL) のローカル/本番起動定義
├── docker-entrypoint.sh       # コンテナ起動時に migrate → collectstatic → gunicorn を実行
├── requirements.txt           # Python依存パッケージ（バージョン固定）
├── .env.example                # 環境変数のテンプレート（本番では実際の値を .env か注入で渡す）
├── pytest.ini                  # pytest / pytest-django の設定
├── .github/workflows/ci.yml    # GitHub Actions: PostgreSQLを使ったテストパイプライン
└── my_website/                 # Djangoプロジェクト本体
    ├── manage.py
    ├── config/                 # プロジェクト設定 (settings/urls/wsgi/asgi)
    ├── accounts/                # 認証・プロフィール・Apple Music API
    ├── core/                    # トップページ・お問い合わせ
    ├── photraveler/             # 写真×地図 (WanderLens)
    ├── community/                # チャンネル制チャット (Lounge)
    ├── templates/                # 共通テンプレート (base.html, 404/500.html)
    ├── static/                   # CSS/JS/画像（liquid glassデザインの実体）
    └── media/                    # ユーザーアップロード（写真など）
```

## アプリ構成

### `config/`
プロジェクト全体の設定。`settings.py` は環境変数駆動で、開発/本番を切り替える（詳細は[環境変数](#環境変数)を参照）。`urls.py` は `i18n_patterns` で `/ja/`・`/en/` のURLプレフィックスを切り替える多言語対応。

### `accounts/`
- カスタムユーザーモデル `CustomUser`（Privateチャンネル参加承認フラグ、お気に入り楽曲情報を保持）
- サインアップ・プロフィール編集ビュー
- Apple Music (iTunes Search API) のサーバーサイドプロキシ `apple_music_search` / `apple_music_token`（IP単位のレート制限付き。`accounts/ratelimit.py` 参照）

### `core/`
- トップページ (`home_view`)
- お問い合わせフォーム (`contact_view`)。送信されたメッセージは `ContactMessage` としてDB保存され、`CONTACT_NOTIFY_EMAIL` が設定されていれば管理者宛に通知メールを送信する。

### `photraveler/` (WanderLens)
- `MapPin` モデル（緯度経度・写真・説明）を地図上にピン表示。`map_view` はDBから取得した実データをJSONとして地図テンプレートに渡す。
- `PhotoComment` モデルあり（管理画面から登録可能）。
- ピン・コメントの登録は管理画面 (`/admin/`) から行う。

### `community/` (Lounge)
- `Channel`（public/private）と `Message` で構成されるシンプルなチャット。
- 初期チャンネルはアプリ起動時の自動生成ではなく、`community/migrations/0002_seed_channels.py` のdata migrationで一度だけ投入される（`migrate` 実行時にスーパーユーザーが既に存在する場合のみ作成者として割り当てられる）。
- Privateチャンネルは `is_approved_for_private=True` のユーザーのみ閲覧可能。
- メッセージ送信時に送信元IPを記録（不正利用調査用。管理画面ではスーパーユーザーのみ閲覧可）。

## ローカル開発

PostgreSQLとPythonが必要（Dockerを使わない場合）。

```bash
# 仮想環境・依存関係
cd je6hub_website
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .envを用意（DEBUG=Trueにしてローカル開発用に上書き）
cp .env.example .env
# DJANGO_DEBUG=True, DB_HOST=localhost などに編集

# DB起動（例: Homebrewの場合）
brew services start postgresql@16
createdb portfolio_db

# マイグレーション & 起動
cd my_website
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

`DJANGO_DEBUG=True` のときは `STORAGES["staticfiles"]` が素の `StaticFilesStorage` になるため、`collectstatic` を実行しなくても `runserver` でCSS/JSが配信される。

## 環境変数

`.env.example` に全項目を記載。主なもの：

| 変数 | 説明 | 未設定時の挙動 |
|---|---|---|
| `DJANGO_SECRET_KEY` | Djangoの署名キー | 開発用ダミー値（本番では必ず設定） |
| `DJANGO_DEBUG` | デバッグモード | `False`（安全側） |
| `DJANGO_ALLOWED_HOSTS` | 許可ホスト（カンマ区切り） | `localhost,127.0.0.1` |
| `DJANGO_SECURE_SSL_REDIRECT` | HTTP→HTTPSリダイレクト | DEBUG時False、それ以外True |
| `DJANGO_SECURE_HSTS_SECONDS` | HSTSの有効期間（秒） | `0`（無効）。HTTPS配信が安定してから設定する |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | PostgreSQL接続情報 | — |
| `APPLE_MUSIC_DEVELOPER_TOKEN` | MusicKit用の開発者トークン | 空（Apple Music関連機能が404を返す） |
| `EMAIL_HOST` 等 | お問い合わせ通知用SMTP設定 | 未設定ならコンソール出力バックエンド |
| `CONTACT_NOTIFY_EMAIL` | お問い合わせ通知の送信先 | 空（通知メール送信をスキップ） |

## Dockerでの起動（本番想定）

```bash
cp .env.example .env
# .env を編集（DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, DB_PASSWORD など）

docker compose build
docker compose up -d
```

起動時に `docker-entrypoint.sh` が自動的に `migrate` → `collectstatic` を実行してから `gunicorn` を起動する。`web` サービスは `8000` 番ポートで公開されるため、手前にリバースプロキシ（Nginx/Caddy等）を置きTLS終端を行うことを想定している。

初回起動後、管理者ユーザーを作成する：

```bash
docker compose exec web python manage.py createsuperuser
```

## テスト

```bash
pytest
```

`pytest.ini` で `DJANGO_SETTINGS_MODULE=config.settings` と `pythonpath=my_website` を設定済み。実行にはPostgreSQLへの接続が必要（環境変数 `DB_*` を参照）。各アプリの `tests.py` に最小限のスモークテストがある（ページ表示・フォーム送信・認証要求・レート制限など）。

## CI

`.github/workflows/ci.yml` が `push`/`pull_request` 時にPostgreSQLサービスコンテナ上で `manage.py check` と `pytest` を実行する。

## 本番デプロイのチェックリスト

- [ ] `.env` に強力な `DJANGO_SECRET_KEY` を設定（`python -c "import secrets;print(secrets.token_urlsafe(50))"` などで生成）
- [ ] `DJANGO_DEBUG=False`、`DJANGO_ALLOWED_HOSTS` に実ドメインを設定
- [ ] PostgreSQLの接続情報・パスワードを本番用に設定
- [ ] HTTPS配信を確認した上で `DJANGO_SECURE_HSTS_SECONDS` を有効化（例: `31536000`）
- [ ] `CONTACT_NOTIFY_EMAIL` とSMTP設定でお問い合わせ通知が届くことを確認
- [ ] `createsuperuser` でスーパーユーザーを作成（community の初期チャンネルseedはこの後の `migrate` で投入される）
- [ ] `media/` をボリュームまたは外部ストレージ（S3等）でバックアップ
