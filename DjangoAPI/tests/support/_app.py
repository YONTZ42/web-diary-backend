from __future__ import annotations

import os
from importlib import import_module
from typing import Any

from django.apps import apps


"""
Central place to adapt this scaffold to your actual backend.

Required tweaks:
- Set MUSEUM_APP_LABEL if your Django app label is not `museum`.
- Set VIEWS_MODULE if your views module path is not `<app>.views`.
- Set VIEWS_UPLOAD_MODULE if your upload view path differs.
- Set REMBG_PROCESSOR_MODULE if util path differs.

Example:
    export MUSEUM_APP_LABEL=gallery
    export VIEWS_MODULE=gallery.views
    export VIEWS_UPLOAD_MODULE=gallery.views_upload
    export REMBG_PROCESSOR_MODULE=your_app.services.rembg_processor
"""

APP_LABEL = os.getenv("MUSEUM_APP_LABEL", "museum")
VIEWS_MODULE = os.getenv("VIEWS_MODULE", f"{APP_LABEL}.views")
VIEWS_UPLOAD_MODULE = os.getenv("VIEWS_UPLOAD_MODULE", f"{APP_LABEL}.views_upload")
REMBG_PROCESSOR_MODULE = os.getenv(
    "REMBG_PROCESSOR_MODULE", f"{APP_LABEL}.utils.rembg_processor"
)


def get_model(model_name: str):
    return apps.get_model(APP_LABEL, model_name)


def import_attr(module_path: str, attr_name: str) -> Any:
    module = import_module(module_path)
    return getattr(module, attr_name)
