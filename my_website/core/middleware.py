from django.conf import settings


class MediaSvgSecurityMiddleware:
    """
    ユーザーがアップロードした SVG (media/ 以下) を配信するときに、スクリプトなどを
    実行できないようにするヘッダーを付ける。SVG は保存時にサニタイズ済みだが、
    画像の URL を直接開かれた場合に備えた二重の対策。

    本番で media を Django 以外 (nginx など) から配信する場合は、同じヘッダーを
    そちらでも付けること。
    """

    CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"

    def __init__(self, get_response):
        self.get_response = get_response
        self.prefix = '/' + settings.MEDIA_URL.lstrip('/')

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.prefix) and request.path.lower().endswith('.svg'):
            response['Content-Security-Policy'] = self.CSP
            response['X-Content-Type-Options'] = 'nosniff'
        return response
