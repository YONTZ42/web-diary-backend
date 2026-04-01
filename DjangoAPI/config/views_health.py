# your_app/views_health.py
from __future__ import annotations

import os
from typing import Any

import boto3
from django.conf import settings
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse

from config.logging_utils import bind_logger, get_logger, log_exception

HEALTH_LOGGER = get_logger("django.health")

def health_check(request):
    return HttpResponse("ok", status=200)

class HealthView(APIView):
    """
    Deep health check for operational monitoring.
    - /healthz: shallow check (App Runner liveness) のまま維持
    - /health : DB / S3 の deep check
    """
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request):
        logger = bind_logger(
            HEALTH_LOGGER,
            component="django.health",
            request_id=getattr(request, "request_id", None),
            guest_id=getattr(request, "guest_id", None),
            user_id=getattr(request, "user_id", None),
            path=request.path,
            method=request.method,
        )

        checks: dict[str, str] = {
            "db": "unknown",
            "s3": "unknown",
        }

        errors: dict[str, str] = {}
        status_code = 200
        overall_status = "ok"

        # ----------------------------
        # DB deep health check
        # ----------------------------
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["db"] = "ok"
        except Exception as exc:
            checks["db"] = "error"
            errors["db"] = type(exc).__name__
            overall_status = "degraded"
            status_code = 503

            log_exception(
                logger,
                event_type="health_dependency_failed",
                message="database health check failed",
                error_code="HEALTH_DB_FAILED",
                dependency="db",
                status_code=503,
            )

        # ----------------------------
        # S3 deep health check
        # ----------------------------
        bucket_name = (
            getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
            or os.environ.get("AWS_STORAGE_BUCKET_NAME", "")
        )

        if not bucket_name:
            checks["s3"] = "error"
            errors["s3"] = "BucketNotConfigured"
            overall_status = "degraded"
            status_code = 503

            logger.error(
                "s3 health check failed because bucket is not configured",
                event="health_dependency_failed",
                component="django.health",
                dependency="s3",
                error_code="HEALTH_S3_BUCKET_NOT_CONFIGURED",
                status_code=503,
            )
        else:
            try:
                s3 = boto3.client("s3")
                s3.head_bucket(Bucket=bucket_name)
                checks["s3"] = "ok"
            except Exception as exc:
                checks["s3"] = "error"
                errors["s3"] = type(exc).__name__
                overall_status = "degraded"
                status_code = 503

                log_exception(
                    logger,
                    event_type="health_dependency_failed",
                    message="s3 health check failed",
                    error_code="HEALTH_S3_FAILED",
                    dependency="s3",
                    s3_bucket=bucket_name,
                    status_code=503,
                )

        response_body = {
            "status": overall_status,
            "checks": checks,
            "service": getattr(settings, "SERVICE_NAME", os.environ.get("SERVICE_NAME", "mini-museum-api")),
            "stage": getattr(settings, "STAGE", os.environ.get("STAGE", os.environ.get("APP_ENV", "local"))),
        }

        if errors:
            response_body["errors"] = errors

        if status_code == 200:
            logger.info(
                "deep health check passed",
                component="django.health",
                status_code=200,
                checks=checks,
            )
        else:
            logger.warning(
                "deep health check degraded",
                component="django.health",
                status_code=503,
                checks=checks,
                errors=errors,
            )

        return Response(response_body, status=status_code)