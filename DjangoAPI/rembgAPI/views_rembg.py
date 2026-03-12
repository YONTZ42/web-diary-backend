from django.shortcuts import render

# Create your views here.
# your_app/views_rembg.py
import json

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .services.rembg_processor import process_event


@method_decorator(csrf_exempt, name="dispatch")
class RembgProcessView(View):
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

    def options(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        resp = HttpResponse(status=200)
        _apply_cors(resp)
        return resp

    def post(self, request: HttpRequest,model_name:str, *args, **kwargs) -> HttpResponse:
        raw_body = request.body.decode("utf-8") if request.body else "{}"

        # Lambda event 風に合わせる
        event = {
            "body": raw_body,
            "headers": dict(request.headers),
            "httpMethod": "POST",
            "path": request.path,
            "queryStringParameters": request.GET.dict(),
            "pathParameters": {
                "model_name": model_name
            }
        }

        result = process_event(event)

        status_code = int(result.get("statusCode", 500))
        raw_result_body = result.get("body", "{}")

        try:
            parsed_body = json.loads(raw_result_body)
        except json.JSONDecodeError:
            parsed_body = {"raw": raw_result_body}

        resp = JsonResponse(parsed_body, status=status_code, safe=isinstance(parsed_body, dict))
        _apply_cors(resp)
        return resp


def _apply_cors(resp: HttpResponse) -> None:
    # 必要に応じて origin を絞る
    resp["Access-Control-Allow-Origin"] = "*"
    resp["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Guest-Id"
    resp["Access-Control-Allow-Methods"] = "POST, OPTIONS"