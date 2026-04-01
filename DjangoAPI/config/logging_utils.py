from __future__ import annotations

import logging
import os
from typing import Any

import structlog


SERVICE_NAME = os.environ.get("SERVICE_NAME", "mini-museum-api")
STAGE = os.environ.get("STAGE", os.environ.get("APP_ENV", "local"))


def bind_request_context(
    *,
    request_id: str | None = None,
    guest_id: str | None = None,
    user_id: str | None = None,
    path: str | None = None,
    method: str | None = None,
) -> None:
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        guest_id=guest_id,
        user_id=user_id,
        path=path,
        method=method,
    )


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()


def get_logger(name: str):
    """
    logger 名ごとに service / stage / logger を bind 済みの logger を返す
    """
    return structlog.get_logger(name).bind(
        service=SERVICE_NAME,
        stage=STAGE,
        logger=name,
    )


def bind_logger(logger, **fields: Any):
    return logger.bind(**fields)


def log_exception(
    logger,
    *,
    event_type: str,
    message: str,
    error_code: str,
    status_code: int | None = 500,
    **fields: Any,
) -> None:
    logger.exception(
        message,
        event_type=event_type,
        error_code=error_code,
        status_code=status_code,
        **fields,
    )


def configure_structlog() -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", key="timestamp")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class AddDefaultFields(logging.Filter):
    """
    structlog 以外の logging logger も最低限 service / stage を持てるようにする
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "service"):
            record.service = SERVICE_NAME
        if not hasattr(record, "stage"):
            record.stage = STAGE
        return True