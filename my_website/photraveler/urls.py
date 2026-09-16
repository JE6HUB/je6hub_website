from django.urls import path
from . import views

app_name = 'photraveler'

urlpatterns = [
    # グローバル探索（全ユーザーのピン）
    path('',                                    views.map_view,      name='map'),
    # ユーザー別マップ
    path('<str:username>/',                     views.user_map_view, name='user_map'),
    path('<str:username>/add/',                 views.add_pin,       name='add_pin'),
    # ピン操作（ログイン必須）
    path('pins/<int:pin_id>/edit/',             views.edit_pin,      name='edit_pin'),
    path('pins/<int:pin_id>/delete/',           views.delete_pin,    name='delete_pin'),
    # コメント API
    path('pins/<int:pin_id>/comments/',         views.pin_comments,  name='pin_comments'),
]