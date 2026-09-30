from django.conf import settings


class MediaSvgSecurityMiddleware:
    """
    ユーザーがアップロードしたファイル (media/ 以下) を配信するときに、スクリプトなどを
    実行できないようにするヘッダーを付ける。

    - SVG: 保存時にサニタイズ済みだが、画像の URL を直接開かれた場合に備えた二重の対策
    - それ以外: アップロード時に中身を検証しているが、万一 HTML などが紛れ込んでいても
      (過去に保存されたものを含む) sandbox でスクリプトを動かさない

    本番で media を Django 以外 (Caddy) から配信する場合は、同じヘッダーを
    そちらでも付けること (Caddyfile の handle_path /media/*)。
    """

    CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"
    MEDIA_CSP = "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'; sandbox"

    def __init__(self, get_response):
        self.get_response = get_response
        self.prefix = '/' + settings.MEDIA_URL.lstrip('/')

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.prefix):
            response['Content-Security-Policy'] = self.CSP if request.path.lower().endswith('.svg') else self.MEDIA_CSP
            response['X-Content-Type-Options'] = 'nosniff'
        return response
