"""サイト全体のカラースキーム。

実際の色は static/css/style.css の html[data-jh-scheme="..."] で定義する。
ここではスキームの名前・表示名と、設定ページの見本 (スウォッチ) に使う色だけを持つ。
"""
from django.utils.translation import gettext_lazy as _

DEFAULT_SCHEME = "midnight"

# (値, 表示名, 見本の色: 背景 / カード / アクセント / meta theme-color)
SCHEMES = [
    ("midnight", _("ミッドナイト"), ("#000000", "#1c1c1e", "#2997ff")),
    ("ocean", _("オーシャン"), ("#03101d", "#102338", "#4cc2ff")),
    ("forest", _("フォレスト"), ("#050f0a", "#13241a", "#4fd18b")),
    ("ember", _("エンバー"), ("#120a06", "#271912", "#ff9f5a")),
    ("sakura", _("サクラ"), ("#12070d", "#28141f", "#ff85b8")),
    ("amethyst", _("アメジスト"), ("#0a0718", "#1b1634", "#a58bff")),
]

CHOICES = [(value, label) for value, label, _colors in SCHEMES]
VALUES = {value for value, _label, _colors in SCHEMES}


def scheme_options(current):
    """設定ページの選択肢。テンプレートで色見本と選択状態を描くのに使う。"""
    return [
        {
            "value": value,
            "label": label,
            "bg": bg,
            "card": card,
            "accent": accent,
            "selected": value == current,
        }
        for value, label, (bg, card, accent) in SCHEMES
    ]


def theme_color(scheme):
    """<meta name="theme-color"> に入れる背景色。"""
    for value, _label, (bg, _card, _accent) in SCHEMES:
        if value == scheme:
            return bg
    return SCHEMES[0][2][0]
