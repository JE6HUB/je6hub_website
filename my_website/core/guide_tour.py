"""ホームの「使い方ガイド」の中身。

ガイドは章 (chapter) ごとの手順 (step) の並びで、static/js/guide-tour.js が実際の画面の
上に吹き出しを出して一歩ずつ案内する。文言の翻訳と URL の解決をサーバー側で済ませるため、
ここで定義して /guide/tour.json (章の一覧はホームのテンプレート) で渡す。

step のキー:
    page      ... この手順を出すページの pathname の正規表現 (省略するとどのページでも)
    target    ... 指し示す要素の CSS セレクタのリスト。上から順に、画面に見えている最初の要素を使う
    action    ... 次へ進む操作。click / input / change / wait (別ページへの移動を待つ) / None (「次へ」ボタン)
    navigates ... click でページを移動する (移動前に進捗を保存する)
    device    ... "mobile" / "desktop" だけで出す (734px 以下が mobile)
    auth      ... "user" (ログイン中) / "guest" (未ログイン) だけで出す
    menu      ... スマートフォンのメニューを "open" / "closed" にしてから出す
    listen    ... 操作を検出する要素 (target より広い範囲で検出したいとき)
    set_next  ... ログイン画面で、ログイン後の移動先 (next) をこの URL にする
    url       ... この手順のページにいないときに「続ける」で開く URL
"""
import re

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

MOBILE_MENU_BTN = '#jh-menu-btn'


def chapters():
    home = reverse('core:home')
    blog_list = reverse('blog:list')
    blog_create = reverse('blog:create')
    settings_url = reverse('account_settings')
    profile_url = reverse('profile')
    login_url = reverse('login')
    # URL には言語の接頭辞 (/ja/ など) が付くので、パスは reverse した URL から作る
    page = lambda url: '^%s$' % re.escape(url)
    home_page = page(home)
    list_page = page(blog_list)
    detail_page = r'^%s\d+/$' % re.escape(blog_list)
    editor_page = r'^%s$|^%s\d+/edit/$' % (re.escape(blog_create), re.escape(blog_list))
    login_page = page(login_url)
    settings_page = page(settings_url)

    return [
        {
            'id': 'start',
            'icon': 'explore',
            'color': '#2997ff',
            'title': _('サイトの歩き方'),
            'description': _('メニューの使い方と、各ページへの移動のしかた。'),
            'steps': [
                {
                    'page': home_page, 'device': 'desktop', 'target': ['#jh-globalnav .jh-globalnav-list'],
                    'title': _('上部のメニュー'),
                    'body': _('Blogs（記事）、WanderLens（写真と地図）、Lounge（メンバーのチャット）、Resume へは、ここからいつでも移動できます。'),
                },
                {
                    'page': home_page, 'device': 'mobile', 'menu': 'closed', 'target': [MOBILE_MENU_BTN],
                    'action': 'click',
                    'title': _('メニューを開く'),
                    'body': _('右上のボタンをタップすると、すべてのページへのリンクが表示されます。'),
                    'hint': _('タップしてみましょう'),
                },
                {
                    'page': home_page, 'device': 'mobile', 'menu': 'open', 'target': ['.jh-mobile-menu-list'],
                    'title': _('各ページへ移動'),
                    'body': _('Blogs（記事）、WanderLens（写真と地図）、Lounge（メンバーのチャット）、Resume へはここから。下ではアカウントと言語を切り替えられます。'),
                },
                {
                    'page': home_page, 'menu': 'closed', 'auth': 'user',
                    'target': ['#jh-globalnav .jh-globalnav-item.ms-auto [data-nav-account]',
                               '.jh-globalnav-mobile-actions [data-nav-account]'],
                    'title': _('あなたのアカウント'),
                    'body': _('アイコンを押すと、あなたのプロフィールカードが開きます。プロフィールや設定もここから変更できます。'),
                },
                {
                    'page': home_page, 'menu': 'closed', 'auth': 'guest',
                    'target': ['#jh-globalnav .jh-globalnav-item.ms-auto a[href="%s"]' % login_url,
                               '.jh-globalnav-mobile-actions [data-nav-account]'],
                    'title': _('サインイン'),
                    'body': _('記事を書いたり、いいねやコメントをしたりするには、ここからサインインします。アカウントの作成も無料です。'),
                },
                {
                    'page': home_page, 'menu': 'closed', 'target': ['#glass-btn-guide'],
                    'title': _('ガイドはいつでもここから'),
                    'body': _('ほかの使い方も、このボタンからいつでも確かめられます。'),
                },
            ],
        },
        {
            'id': 'read',
            'icon': 'auto_stories',
            'color': '#30d158',
            'title': _('記事を読む・反応する'),
            'description': _('記事を探して読み、いいねやコメントを送るまで。'),
            'steps': [
                {
                    'page': home_page, 'target': ['#glass-btn-2'], 'action': 'click', 'navigates': True, 'url': home,
                    'title': _('記事の一覧へ'),
                    'body': _('「記事を読む」を押すと、メンバーが書いた記事の一覧が開きます。'),
                    'hint': _('押してみましょう'),
                },
                {
                    'page': list_page, 'target': ['.blog-search'], 'url': blog_list,
                    'title': _('記事を探す'),
                    'body': _('キーワードを入れて Enter を押すと、タイトルや本文から記事を検索できます。'),
                },
                {
                    'page': list_page, 'target': ['.blog-grid .blog-card', '.blog-carousel .blog-slide'],
                    'action': 'click', 'navigates': True, 'url': blog_list,
                    'title': _('記事を開く'),
                    'body': _('気になる記事を押すと、本文が開きます。'),
                    'hint': _('記事を押してみましょう'),
                    'missing': _('まだ記事がありません。記事が投稿されたら、ここから読めるようになります。'),
                },
                {
                    'page': detail_page, 'target': ['.blog-like-btn'], 'action': 'click', 'auth': 'user',
                    'url': blog_list,
                    'title': _('いいねを送る'),
                    'body': _('記事を気に入ったら、ハートを押して著者に伝えましょう。もう一度押すと取り消せます。'),
                    'hint': _('ハートを押してみましょう'),
                },
                {
                    'page': detail_page, 'target': ['#blogCommentText'], 'action': 'input', 'auth': 'user',
                    'url': blog_list,
                    'title': _('コメントを書く'),
                    'body': _('感想を書いてみましょう。@ に続けてユーザー名を入れるとメンションでき、相手にメールで知らせます。'),
                    'hint': _('入力してみましょう'),
                },
                {
                    'page': detail_page, 'target': ['.blog-comment-form button[type="submit"]'],
                    'action': 'click', 'navigates': True, 'auth': 'user', 'url': blog_list,
                    'title': _('コメントを投稿'),
                    'body': _('「コメントする」を押すと公開されます。今は投稿しない場合は「完了」でガイドを終えられます。'),
                },
                {
                    'page': detail_page, 'target': ['.blog-reactions'], 'auth': 'guest', 'url': blog_list,
                    'title': _('いいねとコメント'),
                    'body': _('記事の下では、いいねやコメントで著者に感想を伝えられます。サインインすると使えるようになります。'),
                },
            ],
        },
        {
            'id': 'write',
            'icon': 'edit_note',
            'color': '#bf5af2',
            'title': _('ブログを書く'),
            'description': _('テンプレート選びから、書いて公開するまで。'),
            'steps': [
                {
                    'page': home_page, 'target': ['#glass-btn-1'], 'action': 'click', 'navigates': True, 'url': home,
                    'auth': 'user',
                    'title': _('新しい記事を作る'),
                    'body': _('「ブログを書く」を押すと、記事の作成画面が開きます。'),
                    'hint': _('押してみましょう'),
                },
                {
                    'page': home_page, 'target': ['#glass-btn-1'], 'action': 'click', 'navigates': True, 'url': home,
                    'auth': 'guest',
                    'title': _('まずはサインイン'),
                    'body': _('記事を書くにはサインインが必要です。「ブログを書く」を押すとサインイン画面へ進み、サインイン後はこのガイドの続きから再開します。'),
                    'hint': _('押してみましょう'),
                },
                {
                    'page': login_page, 'target': ['form[action="%s"]' % login_url], 'action': 'wait',
                    'auth': 'guest', 'set_next': blog_create, 'url': '%s?next=%s' % (login_url, blog_create),
                    'title': _('サインインする'),
                    'body': _('サインインすると、記事の作成画面へ進みます。アカウントがなければ、下の「アカウントを作成」から登録できます。'),
                },
                {
                    'page': editor_page, 'target': ['.blog-template-grid'], 'action': 'change', 'url': blog_create,
                    'title': _('テンプレートを選ぶ'),
                    'body': _('記事の雰囲気に合うレイアウトを選びましょう。あとからいつでも変えられます。'),
                    'hint': _('ひとつ選んでみましょう'),
                },
                {
                    'page': editor_page, 'target': ['#id_title'], 'action': 'input', 'url': blog_create,
                    'title': _('タイトルを付ける'),
                    'body': _('記事のタイトルを入力しましょう。'),
                    'hint': _('入力してみましょう'),
                },
                {
                    'page': editor_page, 'target': ['#blog-cover-drop'], 'url': blog_create,
                    'title': _('カバー画像（任意）'),
                    'body': _('押して選ぶか、画像をドラッグ＆ドロップすると、記事の顔になるカバー画像を設定できます。'),
                },
                {
                    'page': editor_page, 'target': ['#blog-blocks'], 'action': 'input', 'url': blog_create,
                    'title': _('本文を書く'),
                    'body': _('本文を書いてみましょう。空の行で「/」を入力すると、画像や列などのブロックを追加できます。'),
                    'hint': _('入力してみましょう'),
                },
                {
                    'page': editor_page, 'target': ['#blog-toolbar'], 'url': blog_create,
                    'title': _('書式を整える'),
                    'body': _('見出し、太字、揃え、リスト、引用、画像、数式などはこのツールバーから。'),
                },
                {
                    'page': editor_page, 'target': ['.blog-accent-row'], 'action': 'change', 'url': blog_create,
                    'title': _('アクセントカラー'),
                    'body': _('見出しの飾りやリンクに使う色を選びましょう。'),
                    'hint': _('色を選んでみましょう'),
                },
                {
                    'page': editor_page, 'target': ['.blog-actionbar'], 'action': 'click', 'navigates': True,
                    'url': blog_create,
                    'title': _('保存して公開'),
                    'body': _('「下書き保存」は自分だけに保存、「公開する」で一覧に載ります。⌘/Ctrl + S でも下書き保存できます。'),
                },
            ],
        },
        {
            'id': 'personalize',
            'icon': 'palette',
            'color': '#ff9f0a',
            'title': _('自分好みにする'),
            'description': _('カラースキーム、通知、プロフィールの設定。'),
            'steps': [
                {
                    'device': 'desktop', 'auth': 'user', 'scroll_top': True,
                    'target': ['#jh-globalnav a[href="%s"]' % settings_url],
                    'action': 'click', 'navigates': True,
                    'title': _('個人設定を開く'),
                    'body': _('歯車のアイコンから、個人設定へ移動します。'),
                    'hint': _('押してみましょう'),
                },
                {
                    'device': 'mobile', 'auth': 'user', 'menu': 'closed', 'target': [MOBILE_MENU_BTN],
                    'action': 'click',
                    'title': _('メニューを開く'),
                    'body': _('個人設定はメニューの中にあります。'),
                    'hint': _('タップしてみましょう'),
                },
                {
                    'device': 'mobile', 'auth': 'user', 'menu': 'open',
                    'target': ['.jh-mobile-menu-footer a[href="%s"]' % settings_url],
                    'action': 'click', 'navigates': True,
                    'title': _('個人設定を開く'),
                    'body': _('「個人設定」をタップします。'),
                    'hint': _('タップしてみましょう'),
                },
                {
                    'auth': 'guest', 'menu': 'closed', 'scroll_top': True,
                    'target': ['#jh-globalnav .jh-globalnav-item.ms-auto a[href="%s"]' % login_url,
                               '.jh-globalnav-mobile-actions [data-nav-account]'],
                    'action': 'click', 'navigates': True,
                    'title': _('まずはサインイン'),
                    'body': _('設定はアカウントごとに保存されます。サインインすると、このガイドの続きから再開します。'),
                    'hint': _('押してみましょう'),
                },
                {
                    'page': login_page, 'target': ['form[action="%s"]' % login_url], 'action': 'wait',
                    'auth': 'guest', 'set_next': settings_url, 'url': '%s?next=%s' % (login_url, settings_url),
                    'title': _('サインインする'),
                    'body': _('サインインすると、個人設定の画面へ進みます。'),
                },
                {
                    'page': settings_page, 'target': ['#jh-scheme-form .jh-scheme-options'], 'listen': '#jh-scheme-form',
                    'action': 'change',
                    'url': settings_url,
                    'title': _('カラースキーム'),
                    'body': _('好きな配色を選ぶと、すぐにサイト全体が切り替わり、アカウントに保存されます。'),
                    'hint': _('ひとつ選んでみましょう'),
                },
                {
                    'page': settings_page, 'target': ['#notifications'], 'url': settings_url,
                    'title': _('通知'),
                    'body': _('コメントなどで @メンションされたとき、メールで知らせるかどうかを選べます。'),
                },
                {
                    'page': settings_page, 'target': ['.jh-settings-tab[href="%s"]' % profile_url],
                    'action': 'click', 'navigates': True, 'url': settings_url,
                    'title': _('プロフィールへ'),
                    'body': _('名前やアイコンなど、ほかの人に見えるプロフィールはこちらで編集します。'),
                    'hint': _('押してみましょう'),
                },
                {
                    'page': page(profile_url), 'target': ['[data-avatar-picker]'], 'url': profile_url,
                    'title': _('アイコンを設定'),
                    'body': _('写真を選ぶと、記事やコメントにあなたのアイコンが表示されます。編集したら、下の「保存」を押しましょう。'),
                },
            ],
        },
    ]


def chapter_summaries():
    """ホームのガイド選択画面に並べる章の一覧 (手順の数はデバイスで変わるので出さない)。"""
    return [{k: c[k] for k in ('id', 'icon', 'color', 'title', 'description')} for c in chapters()]


def tour_data(user):
    return {
        'authenticated': user.is_authenticated,
        'chapters': chapters(),
        'labels': {
            'next': _('次へ'),
            'back': _('戻る'),
            'done': _('完了'),
            'skip_step': _('この手順を飛ばす'),
            'close': _('ガイドを終了'),
            'step': _('%(current)s / %(total)s'),
            'missing': _('この画面では見つかりませんでした。'),
            'nice': _('できました！'),
            'resume': _('ガイドを続ける'),
            'resume_hint': _('「%(chapter)s」の途中です'),
            'finished_title': _('「%(chapter)s」のガイドが完了しました'),
            'finished_body': _('次は、こちらも試してみませんか？'),
            'finished_all': _('すべてのガイドを見終わりました。いつでもホームの「使い方ガイド」から見直せます。'),
            'start_next': _('始める'),
            'closed_toast': _('ガイドはホームの「使い方ガイド」からいつでも再開できます。'),
        },
    }
