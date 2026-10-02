"""サイト全体のカラースキーム。

実際の色は static/css/style.css の html[data-jh-scheme="..."] で定義する。
ここではスキームの名前・表示名と、設定ページの見本 (スウォッチ) に使う色だけを持つ。
"""
from django.utils.translation import gettext_lazy as _

DEFAULT_SCHEME = "midnight"

DARK = "dark"
LIGHT = "light"
MODES = [(DARK, _("ダーク")), (LIGHT, _("ライト"))]

# (値, 表示名, モード, 見本の色: 背景 / カード / アクセント)。背景は meta theme-color にも使う
SCHEMES = [
    ("midnight", _("ミッドナイト"), DARK, ("#000000", "#1c1c1e", "#2997ff")),
    ("ocean", _("オーシャン"), DARK, ("#03101d", "#102338", "#4cc2ff")),
    ("forest", _("フォレスト"), DARK, ("#050f0a", "#13241a", "#4fd18b")),
    ("ember", _("エンバー"), DARK, ("#120a06", "#271912", "#ff9f5a")),
    ("sakura", _("サクラ"), DARK, ("#12070d", "#28141f", "#ff85b8")),
    ("amethyst", _("アメジスト"), DARK, ("#0a0718", "#1b1634", "#a58bff")),
    ("daylight", _("デイライト"), LIGHT, ("#f5f5f7", "#ffffff", "#0066cc")),
    ("sky", _("スカイ"), LIGHT, ("#eef5fb", "#ffffff", "#0070b8")),
    ("mint", _("ミント"), LIGHT, ("#eff7f2", "#ffffff", "#12804a")),
    ("sand", _("サンド"), LIGHT, ("#faf4ee", "#ffffff", "#b84a0a")),
    ("blossom", _("ブロッサム"), LIGHT, ("#fbf1f5", "#ffffff", "#b82a66")),
    ("lavender", _("ラベンダー"), LIGHT, ("#f3f1fb", "#ffffff", "#5f3dd6")),
]

CHOICES = [(value, label) for value, label, _mode, _colors in SCHEMES]
VALUES = {value for value, _label, _mode, _colors in SCHEMES}


def scheme_groups(current):
    """設定ページの選択肢を、ダーク / ライトの見出しごとにまとめる。"""
    return [
        {
            "mode": mode,
            "label": mode_label,
            "options": [
                {
                    "value": value,
                    "label": label,
                    "bg": bg,
                    "card": card,
                    "accent": accent,
                    "selected": value == current,
                }
                for value, label, scheme_mode, (bg, card, accent) in SCHEMES
                if scheme_mode == mode
            ],
        }
        for mode, mode_label in MODES
    ]


def theme_color(scheme):
    """<meta name="theme-color"> に入れる背景色。"""
    for value, _label, _mode, (bg, _card, _accent) in SCHEMES:
        if value == scheme:
            return bg
    return SCHEMES[0][3][0]
