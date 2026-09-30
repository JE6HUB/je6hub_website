"""
WanderLens の写真アップロード処理。

- Pillow で実際に画像として読めるものだけを受け付ける (拡張子や Content-Type は信用しない)
- EXIF から撮影位置 (GPS) と撮影日を読み取る (ピンの位置・日付の自動入力に使う)
- 向きを補正し、長辺 2560px に縮小、サムネイル (長辺 720px) を作る
- 保存する画像からはメタデータ (GPS・カメラ情報など) をすべて取り除く
  → ピンを別の場所に置いても、写真の正確な撮影位置が公開されない
"""
import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PHOTOS_PER_PIN = 10
FULL_SIZE = 2560
THUMB_SIZE = 720
ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF', 'MPO'}  # MPO = 一部カメラの JPEG

# EXIF タグ番号
_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825
_DATETIME_ORIGINAL = 36867
_DATETIME = 306


@dataclass
class ProcessedPhoto:
    full: ContentFile
    thumb: ContentFile
    latitude: float | None = None
    longitude: float | None = None
    taken_on: date | None = None


def _to_degrees(values, ref):
    try:
        d, m, s = (float(v) for v in values)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    deg = d + m / 60 + s / 3600
    return -deg if ref in ('S', 'W') else deg


def _read_exif(image):
    exif = image.getexif()
    lat = lng = taken = None
    gps = exif.get_ifd(_GPS_IFD)
    if gps:
        lat = _to_degrees(gps.get(2), gps.get(1))
        lng = _to_degrees(gps.get(4), gps.get(3))
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
            lat = lng = None
    raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
    if isinstance(raw, str):
        try:
            taken = datetime.strptime(raw.strip()[:19], '%Y:%m:%d %H:%M:%S').date()
        except ValueError:
            taken = None
    return lat, lng, taken


def _encode(image, size, quality):
    img = image.copy()
    img.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    # exif を渡さないので、メタデータは書き込まれない
    img.save(buf, 'JPEG', quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def process_photo(uploaded):
    """アップロードされたファイルを検証・変換する。問題があれば ValidationError。"""
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationError(_('写真は 1 枚 25MB までです。'))
    try:
        probe = Image.open(uploaded)
        probe.verify()
        uploaded.seek(0)
        image = Image.open(uploaded)
        image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValidationError(_('画像として読み込めないファイルです (JPEG / PNG / WebP に対応)。')) from exc
    if image.format not in ALLOWED_FORMATS:
        raise ValidationError(_('JPEG / PNG / WebP の写真を選択してください。'))

    lat, lng, taken = _read_exif(image)
    image = ImageOps.exif_transpose(image)
    if image.mode not in ('RGB', 'L'):
        background = Image.new('RGB', image.size, (0, 0, 0))
        rgba = image.convert('RGBA')
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    elif image.mode == 'L':
        image = image.convert('RGB')

    name = uuid.uuid4().hex[:16]
    return ProcessedPhoto(
        full=ContentFile(_encode(image, FULL_SIZE, 86), name=f'{name}.jpg'),
        thumb=ContentFile(_encode(image, THUMB_SIZE, 80), name=f'{name}_thumb.jpg'),
        latitude=lat,
        longitude=lng,
        taken_on=taken,
    )
