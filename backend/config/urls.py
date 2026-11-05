from django.conf import settings
from django.urls import path, re_path
from django.views.static import serve

from .api import api

urlpatterns = [path('api/', api.urls)]
if settings.DEBUG:  # in production photos are served from object storage / a CDN
    urlpatterns.append(re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}))
