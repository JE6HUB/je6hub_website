from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext_lazy as _

from core.uploads import sanitize_image

from .blocks import blocks_to_html, normalize_blocks
from .models import Post
from .svg import is_svg_upload, sanitized_svg_upload

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'}


class ImageOrSvgField(forms.ImageField):
    """JPEG / PNG / GIF / WebP に加えて SVG を受け付ける。SVG はサニタイズしたものに差し替える。"""

    # 既定の拡張子チェックは Pillow 対応形式のみ (.svg を弾く)。
    # SVG 以外は super().to_python() が Pillow で実際に画像として読めるかを確認する。
    default_validators = []

    def to_python(self, data):
        if not (data and hasattr(data, 'read')):
            return super().to_python(data)
        if data.size > MAX_IMAGE_BYTES:
            raise forms.ValidationError(_('画像サイズの上限は10MBです。'))
        if is_svg_upload(data):
            return sanitized_svg_upload(data)
        super().to_python(data)
        # 撮影位置 (EXIF GPS) などのメタデータを取り除き、ファイル名もランダムにしてから保存する
        clean = sanitize_image(data)
        content_type = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'gif': 'image/gif'}
        return SimpleUploadedFile(clean.name, clean.read(), content_type=content_type[clean.name.rsplit('.', 1)[-1]])


def validate_image_upload(image):
    if image.size > MAX_IMAGE_BYTES:
        raise forms.ValidationError(_('画像サイズの上限は10MBです。'))
    content_type = getattr(image, 'content_type', None)
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        raise forms.ValidationError(_('JPEG / PNG / GIF / WebP / SVG 形式の画像を選択してください。'))
    return image


class PostForm(forms.ModelForm):
    cover_image = ImageOrSvgField(required=False)

    class Meta:
        model = Post
        fields = ('title', 'subtitle', 'cover_image', 'body_html', 'body_delta', 'body_blocks', 'template', 'display_width', 'accent')

    def __init__(self, *args, publishing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.publishing = publishing
        # 表示幅の指定がない送信 (古い画面など) は標準として扱う
        self.fields['display_width'].required = False

    def clean_display_width(self):
        return self.cleaned_data.get('display_width') or Post.WIDTH_STANDARD

    def clean_cover_image(self):
        image = self.cleaned_data.get('cover_image')
        # 新規アップロード時のみ検証 (既存ファイル・クリア時はそのまま)
        if image and hasattr(image, 'content_type'):
            validate_image_upload(image)
        return image

    def clean_body_blocks(self):
        return normalize_blocks(self.cleaned_data.get('body_blocks') or {})

    def clean(self):
        cleaned = super().clean()
        blocks = cleaned.get('body_blocks')
        body = blocks_to_html(blocks) if blocks else cleaned.get('body_html', '')
        if self.publishing and not Post(body_html=body).plain_text and '<img' not in body:
            self.add_error('body_html', _('公開するには本文を入力してください。'))
        return cleaned


class ImageUploadForm(forms.Form):
    image = ImageOrSvgField()

    def clean_image(self):
        return validate_image_upload(self.cleaned_data['image'])
