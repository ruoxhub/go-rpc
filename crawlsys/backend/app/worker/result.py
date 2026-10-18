"""Worker 业务执行结果。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
