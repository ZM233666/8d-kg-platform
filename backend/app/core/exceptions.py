"""业务异常基类 + FastAPI 全局异常处理器。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """所有业务异常的基类。"""

    code: str = "APP_ERROR"
    http_status: int = 500
    message: str = "An internal error occurred"

    def __init__(self, message: str | None = None, details: dict | None = None):
        self.message = message or self.__class__.message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "NOT_FOUND"
    http_status = 404
    message = "Resource not found"


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    http_status = 422
    message = "Request validation failed"


class PermissionDenied(AppError):
    code = "FORBIDDEN"
    http_status = 403
    message = "Permission denied"


class DuplicateUploadError(AppError):
    code = "DUPLICATE_UPLOAD"
    http_status = 409
    message = "File already uploaded"


class PipelineError(AppError):
    code = "PIPELINE_ERROR"
    http_status = 500
    message = "Pipeline execution failed"


class FatalPipelineError(PipelineError):
    """单个文档 pipeline 整体失败，不重试。"""


class PartialPipelineError(PipelineError):
    """部分失败，记录 failed_items 并继续后续阶段。"""

    def __init__(self, message: str, failed_items: list[dict] | None = None):
        super().__init__(message)
        self.failed_items = failed_items or []


class LLMUpstreamError(AppError):
    code = "LLM_UPSTREAM_ERROR"
    http_status = 502
    message = "LLM upstream error"


class ServiceUnavailableError(AppError):
    code = "SERVICE_UNAVAILABLE"
    http_status = 503
    message = "Service temporarily unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    """将业务异常处理器注册到 FastAPI app。"""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "trace_id": request.state.trace_id
                    if hasattr(request.state, "trace_id")
                    else None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """兜底异常处理器，不暴露内部堆栈。"""
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred",
                    "details": {},
                    "trace_id": request.state.trace_id
                    if hasattr(request.state, "trace_id")
                    else None,
                }
            },
        )
