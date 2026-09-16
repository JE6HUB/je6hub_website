from django.urls import path
from . import views

app_name = 'community'

urlpatterns = [
    path('',                                        views.channel_list,   name='list'),
    path('create/',                                 views.create_channel,  name='create'),
    path('<int:channel_id>/',                       views.thread_view,     name='thread'),
    path('<int:channel_id>/join/',                  views.join_channel,    name='join'),
    path('<int:channel_id>/leave/',                 views.leave_channel,   name='leave'),
    path('<int:channel_id>/invite/',                views.invite_member,   name='invite'),
    path('<int:channel_id>/accept/',                views.accept_invite,   name='accept_invite'),
    path('<int:channel_id>/approve/<int:user_id>/', views.approve_member,  name='approve'),
    path('<int:channel_id>/decline/<int:user_id>/', views.decline_member,  name='decline'),
]