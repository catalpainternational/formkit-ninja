from django.urls import path
from ninja import NinjaAPI
from formkit_ninja.api import router

api = NinjaAPI(title="FormKit Ninja API")
api.add_router("/", router)

urlpatterns = (path("", api.urls),)
