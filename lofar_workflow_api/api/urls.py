from django.conf.urls import url, include
from rest_framework.urlpatterns import format_suffix_patterns
from .views import *

from django.urls import path

urlpatterns = {
    url(r'^auth/', include('rest_framework.urls',
                               namespace='rest_framework')), 
    url(r'^sessions$', CreateSessionsView.as_view(), name="create"),
    url(r'^sessions/$', CreateSessionsView.as_view(), name="create"),
#    url(r'^sessions/(?P<pk>[0-9]+)/$', SessionDetailsView.as_view(), name='details'),
#    url(r'^sessions/(?P<pk>[0-9]+)/$', SessionDetails.as_view(), name='details'),
    url(r'^sessions/(?P<pk>[0-9]+)/$', SessionView.as_view(), name='session-details'),
    url(r'^pipelineschemas$', PipelineSchemasView.as_view(), name='pipelineschemas'),
    url(r'^pipelineschemas/$', PipelineSchemasView.as_view(), name='pipelineschemas'),
    url(r'^transfer$', TransferView.as_view(), name='transfer'),
    url(r'^transfer/$', TransferView.as_view(), name='transfer'),
    url(r'^stage$', StageView.as_view(), name="staging"),
    url(r'^stage/$', StageView.as_view(), name="staging")
#    path('api/<slug:jobid>/', views.job, name='jobState'),
#    url(r'^api/(?P<jobid>[-\w]+)/$', views.job, name='jobid'),
}

urlpatterns = format_suffix_patterns(urlpatterns)
