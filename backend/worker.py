"""RQ worker entrypoint for VisionSafe backend background jobs.

Run:
  python worker.py
"""

from __future__ import annotations

import logging
from pathlib import Path

from rq import Connection, Worker

from app.services.queue_service import QUEUE_NAME, get_queue_connection
from app.utils.logging_config import setup_logging


logger = logging.getLogger("visionsafe.queue.worker")


def _job_exception_handler(job, exc_type, exc_value, traceback) -> bool:
    """Log failed background jobs to file and standard logger."""
    logs_dir = Path(__file__).resolve().parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    failure_log = logs_dir / "queue_worker_failures.log"

    with open(failure_log, "a", encoding="utf-8") as f:
        f.write(
            f"job_id={job.id} queue={job.origin} func={job.func_name} "
            f"exc_type={exc_type.__name__} exc={exc_value}\n"
        )

    logger.exception(
        "queue job failed",
        extra={
            "event": "queue_job_failed",
            "job_id": job.id,
            "queue": job.origin,
            "function": job.func_name,
        },
        exc_info=(exc_type, exc_value, traceback),
    )
    return True


def main() -> None:
    setup_logging()
    redis_conn = get_queue_connection()

    with Connection(redis_conn):
        worker = Worker([QUEUE_NAME])
        worker.push_exc_handler(_job_exception_handler)
        logger.info("RQ worker started", extra={"event": "queue_worker_started", "queue": QUEUE_NAME})
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
