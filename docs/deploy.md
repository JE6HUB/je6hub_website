# 本番デプロイ手順（VPS + Caddy）

je6hub サイトを 1 台の VPS 上で `docker-compose.prod.yml` を使って公開する手順。
構成は `Caddy (80/443, 自動HTTPS, /media/ 配信) → Gunicorn (web) → PostgreSQL (db)`。

## 1. VPS を用意する

- 推奨スペック: **メモリ 2GB / Ubuntu 24.04 LTS**（1GB だと Docker ビルドと PostgreSQL で不足しやすい）
- 候補: ConoHa VPS、さくらのVPS、Xserver VPS、AWS Lightsail（東京リージョン）。いずれも月 1,000〜1,500 円前後
- 作成時に SSH 公開鍵を登録し、固定の IPv4 アドレスを控えておく

## 2. ドメインと DNS

1. ドメインを取得する（Cloudflare Registrar や お名前.com など）
2. DNS に次のレコードを作る

   | 種類 | 名前 | 値 |
   |---|---|---|
   | A | `@`（例: `je6hub.com`） | VPS の IPv4 |
   | A | `www` | VPS の IPv4 |
   | AAAA | `@` / `www` | VPS の IPv6（ある場合のみ） |

3. Cloudflare の DNS を使う場合は、最初は **プロキシをオフ（DNS only / グレーの雲）** にする。Caddy が Let's Encrypt の証明書を取得できたあとでオンにしてよい（その場合 SSL/TLS モードは「Full (strict)」）
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

# Docker (公式手順)
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
```

VPS 事業者のパケットフィルター（ConoHa の「セキュリティグループ」など）がある場合は、そちらでも 22/80/443 を開ける。

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
- **お問い合わせ通知**: `EMAIL_*` と `CONTACT_NOTIFY_EMAIL` を設定し、フォームから送って届くことを確認する
- **HSTS**: HTTPS で問題なく数日運用できたら `DJANGO_SECURE_HSTS_SECONDS=31536000` にする（一度有効にすると HTTP に戻せないので最後に）

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
