from django.urls import path

from formkit_ninja.api import api

urlpatterns = (path("", api.urls),)
