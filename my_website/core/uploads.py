"""
ユーザーがアップロードした画像・動画を安全に保存するための共通処理。

- 拡張子や Content-Type (ブラウザ申告) は信用せず、中身から形式を判定する
  → HTML などを「画像」と偽ってアップロードし、サイトのドメインで実行させる攻撃を防ぐ
- 保存するファイル名はランダムにする (元のファイル名に含まれる個人情報を残さない・URL を推測させない)
- 画像は Pillow で読み直して保存し、EXIF (GPS の撮影位置・撮影日時・カメラの製造番号など) を取り除く
- 動画 (MP4 / MOV) は撮影位置のメタデータ (©xyz / ISO 6709 / XMP) を無効化する
"""
import io
import re
import struct
import uuid
import warnings

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

# 展開後のピクセル数の上限 (小さなファイルを巨大な画像に展開させてメモリを使い切らせる攻撃の対策)。
# 1 億画素 ≒ 12000 x 8000 程度。スマホ・一眼の写真はこれより小さい。
MAX_IMAGE_PIXELS = 100_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

# Pillow の形式名 → (保存形式, 拡張子)
_IMAGE_OUTPUTS = {
    'JPEG': ('JPEG', 'jpg'),
    'MPO': ('JPEG', 'jpg'),  # 一部カメラの JPEG
    'PNG': ('PNG', 'png'),
    'WEBP': ('WEBP', 'webp'),
    'GIF': ('GIF', 'gif'),
}


def random_name(ext):
    return f'{uuid.uuid4().hex}.{ext}'


def open_image(uploaded):
    """Pillow で実際に画像として読めるかを確認して開く。巨大すぎる画像は拒否する。"""
    try:
        uploaded.seek(0)
        with warnings.catch_warnings():
            # 上限を超える画像は警告ではなくエラーとして扱う
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            probe = Image.open(uploaded)
        probe.verify()
        uploaded.seek(0)
        image = Image.open(uploaded)
        image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError(_('画像の解像度が大きすぎます。')) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValidationError(_('画像として読み込めないファイルです (JPEG / PNG / WebP / GIF に対応)。')) from exc
    return image


def _strip_frame(frame):
    """保存時にメタデータが引き継がれないよう、フレームの info を空にしたコピーを返す。"""
    frame = frame.copy()
    # 色の再現に必要な ICC プロファイルと、アニメーション・透過の設定だけ残す
    frame.info = {k: v for k, v in frame.info.items() if k in ('duration', 'transparency', 'loop', 'background', 'icc_profile')}
    return frame


def sanitize_image(uploaded):
    """画像を検証し、メタデータを取り除いた保存用ファイル (ランダムなファイル名) を返す。

    形式は変えない (GIF のアニメーションや PNG の透過はそのまま)。JPEG は向きを補正して保存し直す。
    """
    image = open_image(uploaded)
    if image.format not in _IMAGE_OUTPUTS:
        raise ValidationError(_('JPEG / PNG / WebP / GIF の画像を選択してください。'))
    fmt, ext = _IMAGE_OUTPUTS[image.format]
    buf = io.BytesIO()

    if fmt == 'GIF' and getattr(image, 'n_frames', 1) > 1:
        frames = []
        for i in range(image.n_frames):
            image.seek(i)
            frames.append(_strip_frame(image))
        frames[0].save(
            buf, 'GIF', save_all=True, append_images=frames[1:],
            loop=image.info.get('loop', 0), duration=[f.info.get('duration', 100) for f in frames],
            disposal=2,
        )
    else:
        image = _strip_frame(ImageOps.exif_transpose(image))
        # exif / xmp / pnginfo などを渡さないので、メタデータは書き込まれない
        icc = {'icc_profile': image.info['icc_profile']} if image.info.get('icc_profile') else {}
        if fmt == 'JPEG':
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            image.save(buf, 'JPEG', quality=90, optimize=True, **icc)
        elif fmt == 'WEBP':
            image.save(buf, 'WEBP', quality=90, **icc)
        else:
            image.save(buf, fmt, optimize=True, **icc)

    return ContentFile(buf.getvalue(), name=random_name(ext))


# ─── 動画 ────────────────────────────────────────────────────

# ISO 6709 形式の位置情報 (例: "+35.6812+139.7671+040.000/")。iPhone の MOV や Android の MP4 が書き込む
_ISO6709_RE = re.compile(rb'[+-]\d{2}(?:\.\d+)?[+-]\d{3}(?:\.\d+)?(?:[+-]\d+(?:\.\d+)?)?(?:CRS[^/]{0,40})?/')
# XMP メタデータの uuid ボックス (GPS を含むことがある)
_XMP_UUID = bytes.fromhex('BE7ACFCB97A942E89C71999491E3AFAC')
_CONTAINER_BOXES = {b'moov', b'trak', b'udta', b'meta', b'mdia', b'minf', b'ilst', b'edts'}
_MAX_MOOV_BYTES = 64 * 1024 * 1024

# ftyp のブランド → 拡張子 (QuickTime は mov、それ以外の ISO BMFF は mp4)
_QT_BRANDS = {b'qt  '}


def _iter_boxes(data, start, end):
    """[start, end) の範囲にある ISO BMFF ボックスを (type, 開始位置, 中身の開始位置, 終了位置) で返す。"""
    pos = start
    while pos + 8 <= end:
        size, box_type = struct.unpack('>I4s', data[pos:pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = struct.unpack('>Q', data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return
        yield box_type, pos, pos + header, pos + size
        pos += size


def _scrub_boxes(data, start, end):
    """位置情報を持つボックスを 'free' (再生時に無視される) に書き換える。サイズは変えない。"""
    for box_type, pos, body, box_end in _iter_boxes(data, start, end):
        if box_type == b'\xa9xyz' or (box_type == b'uuid' and data[body:body + 16] == _XMP_UUID):
            data[pos + 4:pos + 8] = b'free'
        elif box_type in _CONTAINER_BOXES:
            inner = body
            # ISO の meta は FullBox (version/flags の 4 バイト)。QuickTime の meta は直後に子ボックス
            if box_type == b'meta' and data[body:body + 4] == b'\x00\x00\x00\x00':
                inner += 4
            _scrub_boxes(data, inner, box_end)


def _zero_iso6709(data):
    """残った ISO 6709 の位置文字列 (keys/ilst の com.apple.quicktime.location など) を 0 で塗りつぶす。"""
    for m in _ISO6709_RE.finditer(bytes(data)):
        s, e = m.span()
        data[s:e] = re.sub(rb'\d', b'0', m.group(0))


def _read_at(f, pos, n):
    f.seek(pos)
    return f.read(n)


def _scrub_isobmff(f, file_size):
    """MP4 / MOV の moov (メタデータ) を読み、位置情報を消してその場で書き戻す。"""
    pos = 0
    found_moov = False
    while pos + 8 <= file_size:
        head = _read_at(f, pos, 16)
        size, box_type = struct.unpack('>I4s', head[:8])
        header = 8
        if size == 1:
            size = struct.unpack('>Q', head[8:16])[0]
            header = 16
        elif size == 0:
            size = file_size - pos
        if size < header or pos + size > file_size:
            raise ValidationError(_('動画ファイルが壊れているか、対応していない形式です。'))
        if box_type in (b'moov', b'meta', b'udta', b'uuid'):
            if size > _MAX_MOOV_BYTES:
                raise ValidationError(_('動画ファイルが壊れているか、対応していない形式です。'))
            data = bytearray(_read_at(f, pos, size))
            if box_type == b'uuid':
                if data[header:header + 16] == _XMP_UUID:
                    data[4:8] = b'free'
            else:
                _scrub_boxes(data, 0, size)
                _zero_iso6709(data)
            f.seek(pos)
            f.write(data)
            found_moov = found_moov or box_type == b'moov'
        pos += size
    if not found_moov:
        raise ValidationError(_('動画ファイルが壊れているか、対応していない形式です。'))


def _video_kind(head):
    """先頭のバイト列から動画の形式を判定する。対応外なら None。"""
    if head[4:8] == b'ftyp':
        return 'mov' if head[8:12] in _QT_BRANDS else 'mp4'
    if head[:4] == b'\x1a\x45\xdf\xa3':  # EBML (Matroska / WebM)
        return 'webm' if b'webm' in head[:64] else None
    return None


def sanitize_video(uploaded):
    """動画を検証し、撮影位置のメタデータを消した保存用ファイル (ランダムなファイル名) を返す。

    MP4 / MOV / WebM のみ受け付ける。アップロードされた一時ファイルをその場で書き換える
    (ファイル全体をメモリに読み込まない)。
    """
    f = uploaded.file if hasattr(uploaded, 'file') else uploaded
    f.seek(0)
    kind = _video_kind(f.read(64))
    if kind is None:
        raise ValidationError(_('対応していない動画形式です (MP4 / MOV / WebM に対応)。'))
    if kind in ('mp4', 'mov'):
        f.seek(0, io.SEEK_END)
        try:
            _scrub_isobmff(f, f.tell())
        except struct.error as exc:
            raise ValidationError(_('動画ファイルが壊れているか、対応していない形式です。')) from exc
    f.seek(0)
    uploaded.name = random_name(kind)
    return uploaded
