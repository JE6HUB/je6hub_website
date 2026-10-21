# JE6HUB iOS アプリ

je6hub.com と同じサーバー・同じアカウントを使う iPhone / iPad アプリ (SwiftUI, iOS 17 以上)。
データは Django の JSON API (`/api/v1/`, `my_website/api/`) から読み書きするので、Web とアプリで内容は常に同じ。

## できること (最初の版)

| 画面 | 内容 |
| --- | --- |
| Blogs | 記事の一覧・検索・本文、いいね、コメント (返信・@メンション)、通報 |
| Lounge | チャンネル一覧・作成・参加リクエスト・招待の承認、会話 (5 秒ごとに更新)、写真・動画の送信 |
| WanderLens | 地図 (Apple のマップ)、スポットの詳細・写真・コメント、写真からのスポット追加 (撮影位置・撮影日を自動入力)、削除 |
| 通知 | Web のベルと同じ通知。タップでその記事・チャンネル・スポットへ |
| マイページ | プロフィール編集、ユーザー画像、メール通知の設定、自分の記事、ログアウト、退会 |

ログインはユーザー名 / メールアドレス + パスワード、または Sign in with Apple。
記事の作成・編集 (ブロックエディタ)、カラースキーム、お気に入りの曲、会員登録は Web 版を開く。
ログインしていなくても Blogs と WanderLens は見られる。

## Mac でビルドする

1. Xcode 16 以上で `ios/JE6HUB.xcodeproj` を開く
2. ターゲット JE6HUB の **Signing & Capabilities** で Team を選ぶ
3. **Bundle Identifier** (`com.je6hub.app`) を自分のものに変える (Apple Developer で使える ID)
4. シミュレーターか実機を選んで実行

ローカルの Django (docker compose) に向けるときは、Edit Scheme → Run → Environment Variables に
`JE6HUB_BASE_URL = http://localhost:8000` を追加する (Debug ビルドだけ有効。既定は https://je6hub.com)。

## Sign in with Apple を使うには

アプリの Sign in with Apple は、アプリが受け取った identity token をサーバーが検証する。
その token の宛先 (audience) はアプリの Bundle ID なので、サーバーの `.env` の `APPLE_CLIENT_ID` に
Web の Services ID に続けて Bundle ID をカンマ区切りで加える (先頭の Services ID は Web のログインで使われる)。

```
APPLE_CLIENT_ID=<Web の Services ID>,<アプリの Bundle ID>
```

Apple Developer の Identifiers でアプリの App ID に「Sign in with Apple」を有効にしておくこと。

## App Store に出すとき

- Apple Developer Program (年額) への登録が必要
- App Store Connect でアプリを作り、Xcode の Product → Archive からアップロードする
- 審査では、投稿 (UGC) のあるアプリに「通報」「不適切な投稿の削除」「迷惑なユーザーのブロック」が求められる。
  通報と退会はアプリにあるが、ユーザーのブロックはまだサイトにない
- プライバシーポリシーの URL が必要

## CI

`ios/` を変えた PR では、GitHub Actions (`.github/workflows/ios.yml`) が macOS で署名なしのシミュレーター向けビルドを行い、
コンパイルエラーを確認する。
