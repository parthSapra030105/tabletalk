from django.urls import path

from api import views

urlpatterns = [
    path("api/datasets/", views.datasets),
    path("api/datasets/<int:dataset_id>/", views.dataset),
    path("api/datasets/<int:dataset_id>/threads/", views.threads),
    path("api/datasets/<int:dataset_id>/glossary/", views.glossary),
    path("api/datasets/<int:dataset_id>/glossary/<str:term>/", views.glossary_entry),
    path("api/threads/<uuid:thread_id>/", views.thread),
    path("api/threads/<uuid:thread_id>/messages/", views.messages),
]
