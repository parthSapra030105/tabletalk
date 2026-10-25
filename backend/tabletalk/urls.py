from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.urls import path, re_path

from api import views


def frontend(request):
    index = settings.FRONTEND_DIR / "index.html"
    if not index.exists():
        raise Http404("The frontend isn't built")
    return FileResponse(open(index, "rb"), content_type="text/html")


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz),
    path("api/datasets/", views.datasets),
    path("api/datasets/<int:dataset_id>/", views.dataset),
    path("api/datasets/<int:dataset_id>/threads/", views.threads),
    path("api/datasets/<int:dataset_id>/glossary/", views.glossary),
    path("api/datasets/<int:dataset_id>/glossary/<str:term>/", views.glossary_entry),
    path("api/threads/<uuid:thread_id>/", views.thread),
    path("api/threads/<uuid:thread_id>/messages/", views.messages),
    re_path(r"^(?!api/).*$", frontend),
]
