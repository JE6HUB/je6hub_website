from django import template

register = template.Library()


@register.filter
def scene_info(photos, scene_id):
    """シーン ID → 番号・写真・WanderLens へのリンク (views._journey_context で作る)。"""
    return (photos or {}).get(scene_id) or {}
