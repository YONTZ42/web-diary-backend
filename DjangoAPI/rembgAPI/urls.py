# your_app/urls.py
from django.urls import path

from .views_rembg import RembgProcessView

urlpatterns = [
    path("image/rembg/<str:model_name>/", RembgProcessView.as_view(), name="rembg-process"),
]