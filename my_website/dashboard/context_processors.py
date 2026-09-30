def admin_badges(request):
    """ヘッダーのダッシュボードアイコンに出す未対応の通報数 (スーパーユーザーのときだけ数える)。"""
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated and user.is_superuser):
        return {}

    cache = []

    def open_reports():
        # テンプレートで参照されたときに 1 回だけ数える
        if not cache:
            from .models import Report
            cache.append(Report.objects.filter(status=Report.STATUS_OPEN).count())
        return cache[0]

    return {'dashboard_open_reports': open_reports}
