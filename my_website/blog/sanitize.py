"""
ブログ本文 (エディタが生成するHTML) のサニタイズ。

本文はテンプレートで |safe 出力するため、保存時に必ずここを通して
許可リスト外のタグ・属性・URLスキーム (script, onerror, javascript: 等) を除去する。
"""
import nh3

ALLOWED_TAGS = {
    'p', 'br', 'h2', 'h3', 'h4',
    'strong', 'b', 'em', 'i', 'u', 's', 'sub', 'sup', 'code',
    'a', 'blockquote', 'pre', 'ul', 'ol', 'li', 'img', 'hr', 'span',
    'div',  # ブロック数式 (.ql-math-display) のみ。class は下で制限
}

ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title'},
    'img': {'src', 'alt', 'width', 'height'},
    # 数式の LaTeX ソース。記事ページで KaTeX が描画する (HTML としては解釈しない)
    'span': {'data-value'},
    'div': {'data-value'},
}

# エディタ (Quill) の配置・インデントはクラスで表現されるため、そのクラスのみ許可する
_BLOCK_CLASSES = (
    {f'ql-align-{a}' for a in ('center', 'right', 'justify')}
    | {f'ql-indent-{i}' for i in range(1, 9)}
)
ALLOWED_CLASSES = {tag: _BLOCK_CLASSES for tag in ('p', 'h2', 'h3', 'h4', 'li', 'blockquote', 'pre')}
ALLOWED_CLASSES['span'] = {'ql-formula'}
ALLOWED_CLASSES['div'] = {'ql-math-display'}

# data: URI (base64埋め込み画像) は不許可。画像は必ずアップロードAPI経由のURLにする
URL_SCHEMES = {'http', 'https', 'mailto'}


def sanitize_html(html):
    if not html:
        return ''
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        allowed_classes=ALLOWED_CLASSES,
        url_schemes=URL_SCHEMES,
        link_rel='noopener noreferrer nofollow',
    ).strip()
