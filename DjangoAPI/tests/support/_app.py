from __future__ import annotations

import os
from importlib import import_module
from typing import Any

from django.apps import apps

"""
Central place to adapt this scaffold to your actual backend.

Recommended env overrides:
- MUSEUM_APP_LABEL
- VIEWS_CORE_MODULE      (default: <app>.views)
- VIEWS_AUTH_MODULE      (default: <app>.views_auth)
- VIEWS_UPLOAD_MODULE    (default: <app>.views_upload)
- VIEWS_REMBG_MODULE     (default: <app>.views_rembg)
- REMBG_PROCESSOR_MODULE (default: <app>.services.rembg_processor)
"""

APP_LABEL = os.getenv("MUSEUM_APP_LABEL", "MiniatureMuseum")
APP_LABEL_CORE = os.getenv("MUSEUM_APP_LABEL_CORE", "core")
APP_LABEL_REMBG = os.getenv("MUSEUM_APP_LABEL_REMBG", "rembgAPI")


VIEWS_CORE_MODULE = os.getenv("VIEWS_CORE_MODULE", f"{APP_LABEL}.views")
VIEWS_AUTH_MODULE = os.getenv("VIEWS_AUTH_MODULE", f"{APP_LABEL_CORE}.views_auth")
VIEWS_UPLOAD_MODULE = os.getenv("VIEWS_UPLOAD_MODULE", f"{APP_LABEL_CORE}.views_upload")
VIEWS_REMBG_MODULE = os.getenv("VIEWS_REMBG_MODULE", f"{APP_LABEL_REMBG}.views_rembg")
REMBG_PROCESSOR_MODULE = os.getenv(
    "REMBG_PROCESSOR_MODULE", f"{APP_LABEL_REMBG}.services.rembg_processor"
)


def get_model(model_name: str):
    return apps.get_model(APP_LABEL, model_name)


def import_attr(module_path: str, attr_name: str) -> Any:
    module = import_module(module_path)
    return getattr(module, attr_name)
