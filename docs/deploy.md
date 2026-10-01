# 本番デプロイ手順（VPS + Caddy）

je6hub サイトを 1 台の VPS 上で `docker-compose.prod.yml` を使って公開する手順。
構成は `Caddy (80/443, 自動HTTPS, /media/ 配信) → Gunicorn (web) → PostgreSQL (db)`。

## 1. VPS を用意する

- 推奨スペック: **メモリ 1GB / Ubuntu 24.04 LTS**。個人サイトの規模なら 1GB で足りる。ただし Docker ビルド時にメモリが一時的に不足しやすいので、3 章で **スワップ 2GB** を必ず作る
- 候補（2026年9月時点、税込の目安）:
  - AWS Lightsail Micro-1GB: 月 $7（東京リージョン、IPv4 付き）
  - ConoHa VPS 1GB: 月 1,065 円上限の時間課金。長期割引あり
  - アクセスが増えてメモリが足りなくなったら、2GB プランに上げて `.env` の `WEB_CONCURRENCY` を 3 にする
- 作成時に SSH 公開鍵を登録し、固定の IPv4 アドレスを控えておく（Lightsail は「ネットワーキング」で静的 IP を作ってインスタンスにアタッチする。アタッチ中は無料）

## 2. ドメインと DNS

1. ドメインを取得する（Cloudflare Registrar や お名前.com など）
2. DNS に次のレコードを作る

   | 種類 | 名前 | 値 |
   |---|---|---|
   | A | `@`（例: `je6hub.com`） | VPS の IPv4 |
   | A | `www` | VPS の IPv4 |
   | AAAA | `@` / `www` | VPS の IPv6（ある場合のみ） |

3. Cloudflare の DNS を使う場合は、最初は **プロキシをオフ（DNS only / グレーの雲）** にする。Caddy が Let's Encrypt の証明書を取得できたあとでオンにしてよい。オンにする前に Cloudflare 側で次を設定する
   - SSL/TLS → 暗号化モードを **Full (strict)** にする（Flexible だと Caddy の HTTPS リダイレクトと衝突して無限リダイレクトになる）
   - SSL/TLS → Edge 証明書の **Always Use HTTPS はオフ** のままにする（HTTPS へのリダイレクトは Caddy が行う。証明書更新の確認リクエストを Caddy に届けるため）
   - 訪問者の本当の IP は `Caddyfile` の `trusted_proxies`（Cloudflare の IP 一覧）と `CF-Connecting-IP` で Django に渡している。Cloudflare が IP 一覧を更新したら `Caddyfile` も更新する
4. `dig +short je6hub.com` で VPS の IP が返ることを確認してから次へ進む

## 3. サーバーの初期設定

```bash
# root でログイン後、作業用ユーザーを作る
adduser deploy && usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy

# SSH をパスワードログイン禁止にする（/etc/ssh/sshd_config）
#   PasswordAuthentication no
#   PermitRootLogin no
systemctl restart ssh

# ファイアウォール: SSH / HTTP / HTTPS のみ許可
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable

# セキュリティ更新の自動適用
apt update && apt install -y unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades

# スワップ 2GB（メモリ1GBのサーバーでビルドや migrate が落ちないように）
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Docker (公式手順)
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
```

VPS 事業者のパケットフィルター（Lightsail の「ネットワーキング → IPv4 ファイアウォール」、ConoHa の「セキュリティグループ」など）がある場合は、そちらでも 22/80/443 を開ける。

## 4. アプリを配置して起動する

```bash
# deploy ユーザーで
git clone https://github.com/JE6HUB/je6hub_website.git
cd je6hub_website
cp .env.example .env
```

`.env` で最低限設定する項目:

| 変数 | 例 |
|---|---|
| `DJANGO_SECRET_KEY` | `python3 -c "import secrets;print(secrets.token_urlsafe(50))"` の出力 |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `je6hub.com,www.je6hub.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://je6hub.com,https://www.je6hub.com` |
| `DB_PASSWORD` | 長いランダム文字列 |
| `SITE_DOMAIN` | `je6hub.com` |
| `ACME_EMAIL` | 証明書期限の通知を受けるメールアドレス |

`DJANGO_BEHIND_PROXY` は `docker-compose.prod.yml` が自動で `True` にするので設定不要。

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f caddy   # 証明書取得のログを確認
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

`https://je6hub.com` が開き、`http://` と `www.` が `https://je6hub.com` にリダイレクトされれば成功。

## 5. 公開後の設定

- **サイト情報**: 管理画面 `/ja/admin/` → Sites で、ドメインを `je6hub.com` に変更する（allauth やメール内リンクが使う）
- **Sign in with Apple**: Apple Developer の Services ID に以下を登録する
  - Domains: `je6hub.com`
  - Return URLs: `https://je6hub.com/ja/accounts/apple/login/callback/` と `https://je6hub.com/en/accounts/apple/login/callback/`
  - `.env` の `APPLE_CLIENT_ID` / `APPLE_TEAM_ID` / `APPLE_KEY_ID` / `APPLE_SECRET_KEY` を設定して `up -d` し直す
- **WanderLens の地図 (Mapbox)**: [account.mapbox.com/access-tokens](https://account.mapbox.com/access-tokens/) の Create a token で新しい公開トークン (pk.) を作り、URL restrictions に `https://je6hub.com` を登録する（ワイルドカードは使えない。この 1 件ですべてのパスと `www.` などのサブドメインが許可される。Default public token には制限をかけられない。制限付きトークンは localhost では動かないので、手元の開発用には別のトークンを作る）。`.env` の `MAPBOX_ACCESS_TOKEN` に設定して `up -d` し直す。無料枠は月 50,000 マップロード（Account → Statistics で使用量を確認でき、請求アラートも設定できる）。Mapbox Studio で作ったスタイルを使うときは `MAPBOX_STYLE` にその URL を入れる
- **お問い合わせ通知**: `EMAIL_*` と `CONTACT_NOTIFY_EMAIL` を設定し、フォームから送って届くことを確認する
- **HSTS**: `Caddyfile` がすべての応答に `Strict-Transport-Security: max-age=31536000; includeSubDomains` を付ける（設定不要）。ブラウザが 1 年間 HTTPS でしか接続しなくなるため、`je6hub.com` とそのサブドメインは HTTPS で配信し続けること。Cloudflare のプロキシを使う場合は SSL/TLS → Edge 証明書 → **HSTS を有効化** でも同じ値（最大有効期間 12 か月、サブドメインを含める: オン、プリロード: オフ、No-Sniff: オン）を設定すると、Cloudflare の Security Insights の「Domains without HSTS」が解消される

## 6. 更新（デプロイ）

```bash
cd ~/je6hub_website
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`migrate` と `collectstatic` はコンテナ起動時に自動で実行される。

## 7. バックアップ

データは Docker ボリュームにある。`postgres_data`（DB）と `media_data`（アップロード写真）が消えると復元できないので、毎日バックアップを取る。

```bash
# /home/deploy/backup.sh
set -e
cd /home/deploy/je6hub_website
mkdir -p ~/backups
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres portfolio_db | gzip > ~/backups/db-$(date +%F).sql.gz
docker run --rm -v je6hub_website_media_data:/media -v ~/backups:/out alpine tar czf /out/media-$(date +%F).tgz -C /media .
find ~/backups -mtime +14 -delete
```

`crontab -e` で `0 4 * * * sh /home/deploy/backup.sh` を登録する。VPS 自体が壊れた場合に備え、`~/backups` は定期的に手元や外部ストレージ（Cloudflare R2、S3 など）にも複製する。VPS 事業者の自動バックアップ（スナップショット）を有効にしておくとさらに安全。

## 8. アップロード済みファイルの位置情報を消す（2026-09 のセキュリティ修正後に 1 回）

アップロード時に画像・動画の撮影位置（GPS）などを取り除く処理は、Lounge と Blogs では 2026-09 のセキュリティ修正から入った。それ以前に Lounge・Blogs へ投稿された写真・動画には撮影位置が残っている可能性があるため、修正をデプロイしたあとに 1 回だけ実行する（WanderLens は最初から除去済み）。

```bash
# 何が変わるかを確認
docker compose -f docker-compose.prod.yml exec web python manage.py scrub_media --dry-run
# 実行（画像・動画として読めないファイルは --delete-invalid で削除される）
docker compose -f docker-compose.prod.yml exec web python manage.py scrub_media --delete-invalid
```

事前に 7. の手順でバックアップを取っておくこと。

## 9. 管理者ダッシュボードとアクセス解析

スーパーユーザーでログインすると、ヘッダーのアカウント欄にメーター型のアイコンが出る（`/dashboard/`）。アクセス数・アクセス元の国と都市・通報・ユーザーの凍結/削除・お問い合わせ・操作履歴を扱える。スーパーユーザーは `docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser` で作る。

アクセス元の国・都市は、訪問者の IP を外部サービスに送らず、サーバー上の位置情報データベース（MMDB 形式）で推定する。IP アドレスそのものは保存せず、日ごとの件数だけを残す。データベースを置くまでは、場所は「不明」として数えられる。

無料の [DB-IP IP to City Lite](https://db-ip.com/db/download/ip-to-city-lite)（登録不要、CC BY 4.0。ダッシュボードに出典を表示済み）を使う場合:

```bash
cd ~/je6hub_website
mkdir -p geoip
curl -fL "https://download.db-ip.com/free/dbip-city-lite-$(date +%Y-%m).mmdb.gz" | gunzip > geoip/city.mmdb.new && mv geoip/city.mmdb.new geoip/city.mmdb
```

`geoip/` は web コンテナの `/app/geoip` に読み取り専用でマウントされる（`docker-compose.prod.yml`）。ファイルを差し替えると再起動なしで反映される。データは毎月更新されるので、`crontab -e` で `0 5 3 * * cd /home/deploy/je6hub_website && curl -fsL "https://download.db-ip.com/free/dbip-city-lite-$(date +\%Y-\%m).mmdb.gz" | gunzip > geoip/city.mmdb.new && mv geoip/city.mmdb.new geoip/city.mmdb` を登録しておくとよい。

MaxMind の GeoLite2 City（要アカウント登録）を使う場合は、ダウンロードした `GeoLite2-City.mmdb` を `geoip/city.mmdb` として置けばよい。
