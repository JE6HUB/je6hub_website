"""サインアップ直後に一度だけ出す、プロフィール作成モーダルの表示フラグ (セッションに保存)。"""

SESSION_KEY = 'profile_onboarding'


def request_profile_onboarding(request):
    """次に表示するページでモーダルを出すよう印を付ける。"""
    request.session[SESSION_KEY] = True


def pop_profile_onboarding(request):
    """印があれば取り除いて True を返す。モーダルは一度表示したら二度と出さない。"""
    return bool(request.session.pop(SESSION_KEY, False))
