from django.shortcuts import render

# Create your views here.
# your_app/views_rembg.py
import json
import time
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from config.logging_utils import get_logger, bind_logger, log_exception

from .services.rembg_processor import process_event

from MiniatureMuseum.throttles import GuestIssueThrottle, RembgBurstThrottle, RembgSustainedThrottle




@method_decorator(csrf_exempt, name="dispatch")
class RembgProcessView(APIView):
    permission_classes=[]
    throttle_classes = [RembgBurstThrottle,RembgSustainedThrottle]
    """
    Lambda互換の request body を受ける View。
    POST body 例:
    {
      "image_url": "...",
      "only_for_boot": false
    }

    返却も Lambda互換の body を unwrap してそのまま JSON として返す。
    """

    http_method_names = ["post", "options"]


    def post(self, request: HttpRequest,model_name:str, *args, **kwargs) -> HttpResponse:
        started_at = time.perf_counter()
        base_logger = get_logger("django.rembg")
        logger = bind_logger(
            base_logger,
            component="django.rembg",
            model_name=model_name,
            request_id=getattr(request, "request_id", None),
            guest_id=request.headers.get("X-Guest-Id"),
            user_id=str(request.user.id) if getattr(request, "user", None) and request.user.is_authenticated else None,
            path=request.path,
            method=request.method,
        )

        try:
             raw_body = request.body.decode("utf-8") if request.body else "{}"
        except UnicodeDecodeError:
            log_exception(
                logger,
                event_type="rembg_input_decode_failed",
                message="failed to decode request body",
                error_code="REMBG_INVALID_UTF8_BODY",
                status_code=400,
            )
            return Response({"error": "Invalid request body encoding"}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            event_type="rembg_request_started",
            status_code=None,
        )

        try:
            parsed_body = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            log_exception(
                logger,
                event_type="rembg_input_decode_failed",
                message="failed to parse request json",
                error_code="REMBG_INVALID_JSON",
                status_code=400,
            )
            return Response({"error": "Invalid JSON body"}, status=status.HTTP_400_BAD_REQUEST)

        if parsed_body.get("image_data"):
            input_source = "image_data"
        elif parsed_body.get("image_url"):
            input_source = "image_url"
        elif parsed_body.get("bucket") and parsed_body.get("key"):
            input_source = "s3"
        else:
            input_source = "unknown"


        # Lambda event 風に合わせる
        event = {
            "body": raw_body,
            "headers": dict(request.headers),
            "httpMethod": "POST",
            "path": request.path,
            "queryStringParameters": request.GET.dict(),
            "pathParameters": {"model_name": model_name},
            "requestContext": {
                "request_id": getattr(request, "request_id", None),
                "guest_id": request.headers.get("X-Guest-Id"),
                "user_id": str(request.user.id) if getattr(request, "user", None) and request.user.is_authenticated else None,
            },
        }

        try:
            result = process_event(event, logger=logger.bind(input_source=input_source))
        except Exception:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            log_exception(
                logger.bind(input_source=input_source, duration_ms=duration_ms),
                event_type="rembg_processing_failed",
                message="rembg request failed",
                error_code="REMBG_REQUEST_FAILED",
                status_code=500,
            )
            return Response({"error": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        if duration_ms >= 5000:
            logger.warning(
                event_type="rembg_request_slow",
                message="rembg request is slow",
                input_source=input_source,
                duration_ms=duration_ms,
                status_code=200,
            )

        logger.info(
            event_type="rembg_request_succeeded",
            message="rembg request succeeded",
            input_source=input_source,
            duration_ms=duration_ms,
            status_code=200,
        )
        return Response(result, status=status.HTTP_200_OK)


def _apply_cors(resp: HttpResponse) -> None:
    # 必要に応じて origin を絞る
    resp["Access-Control-Allow-Origin"] = "*"
    resp["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Guest-Id"
    resp["Access-Control-Allow-Methods"] = "POST, OPTIONS"