from django.urls import include, path

from .api import api

urlpatterns = (path("", api.urls),)
