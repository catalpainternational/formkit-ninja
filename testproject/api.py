from ninja import NinjaAPI

api = NinjaAPI()

from formkit_ninja.api import router as formkit_router

api = NinjaAPI()

api.add_router("/formkit/", formkit_router)
