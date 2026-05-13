"""Celery 应用实例 + 配置。"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "kg_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.pipeline_tasks"],
)

# === 基础配置 ===
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # 任务执行
    task_acks_late=True,          # worker 崩溃时任务重新入队
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, # 一次只拿 1 个，避免长任务卡死预取队列
    # 结果保留时间
    result_expires=3600 * 24,     # 24h
    # task 超时（pipeline 真实运行约 13s，给 5 分钟 buffer）
    task_time_limit=300,
    task_soft_time_limit=270,
)