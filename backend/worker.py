"""RQ worker entrypoint for VisionSafe backend background jobs.

Run:
  python worker.py
"""

from __future__ import annotations

import multiprocessing as mp
import logging
import os
import signal
import socket
import threading
import time
from pathlib import Path

from rq import Connection, Worker

from app.services.queue_service import QUEUE_NAME, get_queue_connection, register_worker, worker_queue_name
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


def _run_worker_loop(instance_index: int | None = None) -> None:
    setup_logging()
    redis_conn = get_queue_connection()
    worker_id = os.getenv("VISIONSAFE_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    gpu_id = os.getenv("CUDA_VISIBLE_DEVICES") or os.getenv("VISIONSAFE_GPU_ID")
    capacity = int(os.getenv("VISIONSAFE_WORKER_CAPACITY", "1"))
    queues = [worker_queue_name(worker_id), QUEUE_NAME]
    logger.info(
        "worker process booting",
        extra={
            "event": "queue_worker_boot",
            "worker_id": worker_id,
            "gpu_id": gpu_id,
            "capacity": capacity,
            "instance_index": instance_index,
            "queues": queues,
        },
    )

    def heartbeat() -> None:
        while True:
            register_worker(worker_id=worker_id, gpu_id=gpu_id, capacity=capacity)
            time.sleep(15)

    threading.Thread(target=heartbeat, daemon=True).start()

    with Connection(redis_conn):
        worker = Worker(queues, name=worker_id)
        worker.push_exc_handler(_job_exception_handler)
        logger.info(
            "RQ worker started",
            extra={
                "event": "queue_worker_started",
                "queues": queues,
                "worker_id": worker_id,
                "gpu_id": gpu_id,
                "capacity": capacity,
            },
        )
        worker.work(with_scheduler=True)


def main() -> None:
    pool_size = max(1, int(os.getenv("VISIONSAFE_WORKER_POOL_SIZE", "2")))
    if pool_size == 1:
        _run_worker_loop(instance_index=1)
        return

    setup_logging()
    children: list[mp.Process] = []
    stop_requested = threading.Event()

    def _shutdown(signum, _frame) -> None:
        logger.warning("worker supervisor received signal %s", signum)
        stop_requested.set()
        for child in children:
            if child.is_alive():
                child.terminate()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info(
        "worker supervisor starting",
        extra={"event": "queue_worker_supervisor_start", "pool_size": pool_size},
    )
    for index in range(pool_size):
        child = mp.Process(target=_run_worker_loop, kwargs={"instance_index": index + 1}, name=f"visionsafe-worker-{index + 1}")
        child.start()
        children.append(child)
        logger.info(
            "worker child started",
            extra={"event": "queue_worker_child_started", "index": index + 1, "pid": child.pid},
        )

    try:
        while children and not stop_requested.is_set():
            alive_children: list[mp.Process] = []
            for child in children:
                child.join(timeout=1.0)
                if child.is_alive():
                    alive_children.append(child)
            children = alive_children
            if children:
                time.sleep(0.2)
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
        for child in children:
            child.join(timeout=5)


if __name__ == "__main__":
    main()
