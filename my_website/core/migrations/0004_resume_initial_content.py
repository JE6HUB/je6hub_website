from django.db import migrations


def T(ja, en=''):
    return {'ja': ja, 'en': en}


# テンプレートに直書きしていた Resume の内容 (英語は django.po の訳)。以後はページ上の編集モードで更新する。
INITIAL = {
    'name': T('Yuta Kumadaki', 'Yuta Kumadaki'),
    'tagline': T('AI Architect & Photographer. Tokyo.', 'AI Architect & Photographer. Tokyo.'),
    'summary': T(
        '大規模言語モデル（LLM）のシステム設計・社会実装を専門とするAIアーキテクト。Transformer内部メカニズムの研究（Mechanistic Interpretability）に取り組みながら、Leica Q3によるフォトグラフィーも並行して続けている。',
        'An AI architect specializing in the system design and real-world deployment of large language models (LLMs). Researching the internal mechanisms of Transformers (Mechanistic Interpretability) while also pursuing photography with a Leica Q3.',
    ),
    'stats': [
        {'id': 'stat1', 'value': '5+', 'label': T('年の経験', 'years of experience')},
        {'id': 'stat2', 'value': '10+', 'label': T('件のプロジェクト', 'projects')},
        {'id': 'stat3', 'value': '3', 'label': T('つの専門領域', 'areas of expertise')},
    ],
    'focus': [
        {'id': 'focus1', 'title': T('AI Engineering', 'AI Engineering'), 'body': T(
            '大規模言語モデルの社会実装とシステム設計。Transformerデコーダモデルの内部機序研究を通じて LLM の内部構造を解明する。')},
        {'id': 'focus2', 'title': T('Photography', 'Photography'), 'body': T(
            '都市・旅・自然のスナップショット。世界中の記憶を地図にピン留めして共有するサイト「WanderLens」を開発。')},
        {'id': 'focus3', 'title': T('Community', 'Community'), 'body': T(
            'AI・クラフトビール・写真をテーマにしたコミュニティ Lounge と、誰でも書ける Blogs を運営。',
            'Runs Lounge, a community around AI, craft beer, and photography, and Blogs, where anyone can write.')},
    ],
    'experience': [
        {'id': 'exp1', 'period': T('2026 – 現在', '2026 – Present'), 'title': T('Application Engineer', 'Application Engineer'),
         'org': T('Accenture Japan', 'Accenture Japan'),
         'bullets': {'ja': ['システムDBのマイグレーションツール導入', 'RAG / Agent ワークフローにおけるVDBロード高速化'], 'en': []}},
        {'id': 'exp2', 'period': T('2024 – 2026', '2024 – 2026'),
         'title': T('Computer Science|Natural Language Processing', 'Computer Science|Natural Language Processing'),
         'org': T('Yoshinaga Lab. @ Graduate School of Information Science and Technology, Tokyo University · Japan',
                  'Yoshinaga Lab. @ Graduate School of Information Science and Technology, Tokyo University · Japan'),
         'bullets': {'ja': [], 'en': []}},
        {'id': 'exp3', 'period': T('2020 – 2024', '2020 – 2024'),
         'title': T('Computer Science|Data Science', 'Computer Science|Data Science'),
         'org': T('Yukawa Lab. @Keio University · Japan', 'Yukawa Lab. @Keio University · Japan'),
         'bullets': {'ja': [], 'en': []}},
    ],
    'skills': [
        {'id': 'skill1', 'title': T('AI / ML', 'AI / ML'),
         'items': T('LLM, Transformers, RAG, MCP, Mechanistic Interpretability, Agents',
                    'LLM, Transformers, RAG, MCP, Mechanistic Interpretability, Agents')},
        {'id': 'skill2', 'title': T('Engineering', 'Engineering'),
         'items': T('Python, Django, PostgreSQL, Docker, Git', 'Python, Django, PostgreSQL, Docker, Git')},
        {'id': 'skill3', 'title': T('Creative', 'Creative'),
         'items': T('Photography, UI Design', 'Photography, UI Design')},
    ],
    'projects': [
        {'id': 'proj1', 'title': T('Blogs', 'Blogs'), 'url': '/blog/', 'image': 'blogs-glass',
         'body': T('テンプレートを選ぶだけで、洗練されたブログを。', 'Just pick a template for a polished blog.')},
        {'id': 'proj2', 'title': T('Community Lounge', 'Community Lounge'), 'url': '/community/', 'image': 'lounge-fluid',
         'body': T('AI・写真・クラフトビールを語り合う場所。', 'A place to talk about AI, photography, and craft beer.')},
        {'id': 'proj3', 'title': T('WanderLens', 'WanderLens'), 'url': '/map/', 'image': '',
         'body': T('旅の記憶を世界地図にピン留めするフォトトラベルジャーナル。',
                   'A photo travel journal that pins your travel memories on a world map.')},
        {'id': 'proj4', 'title': T('JE6HUB.com', 'JE6HUB.com'), 'url': '/', 'image': '',
         'body': T('このサイト。Django と PostgreSQL で構築。', 'This site. Built with Django and PostgreSQL.')},
    ],
}


def create_resume(apps, schema_editor):
    Resume = apps.get_model('core', 'Resume')
    Resume.objects.get_or_create(pk=1, defaults={'data': INITIAL})


def delete_resume(apps, schema_editor):
    apps.get_model('core', 'Resume').objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_resume'),
    ]

    operations = [
        migrations.RunPython(create_resume, delete_resume),
    ]
