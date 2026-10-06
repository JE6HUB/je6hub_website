"""iOS アプリ用の JSON API (/api/v1/...)。言語は Accept-Language で切り替わる。"""
from django.urls import path

from .views import auth, blog, lounge, me, notifications, reports, wanderlens

app_name = 'api'

urlpatterns = [
    path('auth/login/',                           auth.login,                  name='login'),
    path('auth/apple/',                           auth.apple_login,            name='apple_login'),
    path('auth/logout/',                          auth.logout,                 name='logout'),

    path('me/',                                   me.me,                       name='me'),
    path('me/avatar/',                            me.avatar,                   name='avatar'),
    path('users/<str:username>/',                 me.user_profile,             name='user_profile'),

    path('blog/posts/',                           blog.post_list,              name='post_list'),
    path('blog/posts/mine/',                      blog.my_posts,               name='my_posts'),
    path('blog/posts/<int:pk>/',                  blog.post_detail,            name='post_detail'),
    path('blog/posts/<int:pk>/like/',             blog.like,                   name='post_like'),
    path('blog/posts/<int:pk>/comments/',         blog.comment_create,         name='comment_create'),
    path('blog/comments/<int:pk>/',               blog.comment_delete,         name='comment_delete'),

    path('lounge/channels/',                      lounge.channels,             name='channels'),
    path('lounge/channels/<int:channel_id>/messages/', lounge.messages,        name='messages'),
    path('lounge/channels/<int:channel_id>/join/',  lounge.join,               name='join'),
    path('lounge/channels/<int:channel_id>/leave/', lounge.leave,              name='leave'),

    path('wanderlens/pins/',                      wanderlens.pins,             name='pins'),
    path('wanderlens/pins/<int:pin_id>/',         wanderlens.pin_detail,       name='pin_detail'),
    path('wanderlens/pins/<int:pin_id>/comments/', wanderlens.pin_comments,    name='pin_comments'),

    path('notifications/',                        notifications.notifications, name='notifications'),
    path('notifications/read/',                   notifications.read_all,      name='notifications_read_all'),
    path('notifications/<int:pk>/read/',          notifications.read,          name='notification_read'),

    path('reports/',                              reports.reports,             name='reports'),
]
