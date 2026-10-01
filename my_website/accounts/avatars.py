"""
ユーザー画像 (アバター) のアップロード処理。

- core.uploads.sanitize_image で中身から形式を判定し、EXIF (撮影位置など) を取り除く
- 中央を正方形に切り抜き、一辺 AVATAR_SIZE px 以下に縮小する (大きな写真をそのまま配信しない)
- GIF のアニメーションは最初のフレームだけを使う。透過のある画像は PNG、それ以外は JPEG で保存する
- ファイル名はランダムにする
"""
import io

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps

from core.uploads import random_name, sanitize_image

AVATAR_SIZE = 512
MAX_AVATAR_BYTES = 10 * 1024 * 1024  # 10 MB


def process_avatar(uploaded):
    """アップロードされた画像を検証・変換し、保存用のファイルを返す。問題があれば ValidationError。"""
    if uploaded.size > MAX_AVATAR_BYTES:
        raise ValidationError(_('画像サイズの上限は10MBです。'))
    clean = sanitize_image(uploaded)
    image = Image.open(clean)
    image.seek(0)
    image.load()

    has_alpha = image.mode in ('RGBA', 'LA', 'PA') or 'transparency' in image.info
    image = image.convert('RGBA' if has_alpha else 'RGB')
    side = min(AVATAR_SIZE, image.width, image.height)
    image = ImageOps.fit(image, (side, side), Image.LANCZOS)

    buf = io.BytesIO()
    # exif などを渡さないので、メタデータは書き込まれない
    if has_alpha:
        image.save(buf, 'PNG', optimize=True)
        ext = 'png'
    else:
        image.save(buf, 'JPEG', quality=88, optimize=True, progressive=True)
        ext = 'jpg'
    return ContentFile(buf.getvalue(), name=random_name(ext))
