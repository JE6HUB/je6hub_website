from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('dashboard/',                                   views.index,         name='index'),
    path('dashboard/traffic/',                           views.traffic,       name='traffic'),
    path('dashboard/reports/',                           views.reports,       name='reports'),
    path('dashboard/reports/<str:kind>/<int:object_id>/', views.report_detail, name='report_detail'),
    path('dashboard/media/<int:object_id>/',             views.message_media, name='message_media'),
    path('dashboard/users/',                             views.users,         name='users'),
    path('dashboard/users/<int:pk>/',                    views.user_detail,   name='user_detail'),
    path('dashboard/contacts/',                          views.contacts,      name='contacts'),
    path('dashboard/log/',                               views.log,           name='log'),
    # 利用者からの通報
    path('report/<str:kind>/<int:object_id>/',           views.report,        name='report'),
]
