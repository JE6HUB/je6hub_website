def notifications(request):
    """ヘッダーの通知アイコンに出す未読数 (ログインしているときだけ、テンプレートで参照されたら数える)。"""
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated):
        return {}

    cache = []

    def unread():
        if not cache:
            cache.append(user.notifications.filter(read_at__isnull=True).count())
        return cache[0]

    return {'notifications_unread': unread}
