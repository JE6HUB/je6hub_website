"""ログイン・ログアウト (トークンの発行と破棄)。"""
from django.utils.translation import gettext as _

from accounts.forms import LoginForm
from accounts.ratelimit import is_rate_limited

from .. import serialize
from ..auth import ApiError, api_view, json_body
from ..models import ApiToken


def _issued(request, user):
    _token, key = ApiToken.issue(user, name=json_body(request).get('device_name', ''))
    return {'token': key, 'user': serialize.me(request, user)}


@api_view('POST', login=False)
def login(request):
    """ユーザー名 (またはメールアドレス) とパスワードでログインし、トークンを返す。"""
    # Web のログインと同じく、同じ IP からは 5 分間に 10 回まで
    if is_rate_limited(request, 'api_login', limit=10, period=300):
        raise ApiError(_('ログインの試行回数が多すぎます。しばらくしてからお試しください。'), status=429)
    data = json_body(request)
    form = LoginForm(request, data={'username': data.get('username', ''), 'password': data.get('password', '')})
    if not form.is_valid():
        if form.unverified:
            raise ApiError(_('メールアドレスの確認が済んでいません。届いたメールのリンクを開いてください。'),
                           status=403, errors={'code': ['unverified']})
        raise ApiError(_('ユーザー名またはパスワードが正しくありません。'), status=400)
    return _issued(request, form.get_user())


@api_view('POST', login=False)
def apple_login(request):
    """アプリの Sign in with Apple。Apple が発行した identity token を検証してトークンを返す。

    Web の Sign in with Apple (allauth) と同じ SocialAccount を使うので、どちらから登録しても同じアカウントになる。
    初めての人はその場でアカウントを作る (Web と同じ AppleSocialAccountAdapter を通す)。
    """
    from allauth.socialaccount.adapter import get_adapter
    from django.core.exceptions import ValidationError

    if is_rate_limited(request, 'api_login', limit=10, period=300):
        raise ApiError(_('ログインの試行回数が多すぎます。しばらくしてからお試しください。'), status=429)
    data = json_body(request)
    identity_token = data.get('identity_token') or ''
    if not identity_token:
        raise ApiError('identity_token is required')

    try:
        provider = get_adapter().get_provider(request, 'apple')
        login = provider.verify_token(request, {'id_token': identity_token})
    except ValidationError:
        raise ApiError(_('Apple でのサインインを確認できませんでした。'), status=401)
    except Exception:
        # Apple のアプリ設定 (SocialApp / APPLE_CLIENT_ID) がない場合など
        raise ApiError(_('Apple でのサインインは現在利用できません。'), status=503)

    login.lookup()
    if login.is_existing:
        user = login.user
    else:
        # Apple は名前を identity token に含めず、初回にアプリへ渡すだけなので、アプリから受け取る
        login.user.first_name = (data.get('first_name') or '')[:150]
        login.user.last_name = (data.get('last_name') or '')[:150]
        user = get_adapter().save_user(request, login)
    if not user.is_active:
        raise ApiError(_('このアカウントは利用できません。'), status=403)
    return _issued(request, user)


@api_view('POST')
def logout(request):
    """この端末のトークンを無効にする。"""
    request.api_token.delete()
    return {}
