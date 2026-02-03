from ninja import NinjaAPI

from formkit_ninja.api import router as formkit_router

api = NinjaAPI()

api.add_router("/formkit/", formkit_router)

from testproject.sample_app.api import router as sample_app_router
api.add_router("/sample_app/", sample_app_router)

from testproject.complex_app.api import router as complex_app_router
api.add_router('/complex_app/', complex_app_router)

from testproject.partisipa.api import router as partisipa_router
api.add_router('/partisipa/', partisipa_router)
