import json
import logging
import sys
import threading
import time
import os
import signal

from norfab.core.worker import NFPWorker
from typing import Union, List, Dict, Any

from pydantic import BaseModel

log = logging.getLogger(__name__)

try:
    import uvicorn
    from fastapi import FastAPI, APIRouter

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    log.debug("FastAPI worker - failed to import FastAPI library.")


class FastAPIWorker(NFPWorker):
    """
    :param broker: broker URL to connect to
    :param service: name of the service with worker belongs to
    :param worker_name: name of this worker
    :param exit_event: if set, worker need to stop/exit
    :param init_done_event: event to set when worker done initializing
    :param log_level: logging level of this worker
    """

    def __init__(
        self,
        inventory: str,
        broker: str,
        worker_name: str,
        service: str = b"nornir",
        exit_event=None,
        init_done_event=None,
        log_level: str = None,
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, service, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event
        self.exit_event = exit_event

        # get inventory from broker
        self.fastapi_inventory = self.load_inventory()
        self.uvicorn_inventory = {
            "host": "0.0.0.0",
            "port": 8000,
            **self.fastapi_inventory.pop("uvicorn", {}),
        }

        # start FastAPI server
        self.fastapi_start()

    def fastapi_start(self):
        """
        Method to start FatAPI server
        """
        self.app = make_fast_api_app(self, **self.fastapi_inventory.get("fastapi", {}))
        # self.api_router = APIRouter()
        # self.app.include_router(self.api_router)

        # add API endpoints
        # self.api_router.add_api_route('/jobs', endpoint=self.post_job, methods=["POST"])
        # self.api_router.add_api_route('/jobs', endpoint=self.get_job, methods=["GET"])
        # self.api_router.add_api_route('/run_job', endpoint=self.run_job, methods=["POST"])

        # start uvicorn server in a thread
        config = uvicorn.Config(app=self.app, **self.uvicorn_inventory)
        self.uvicorn_server = uvicorn.Server(config=config)

        self.uvicorn_server_thread = threading.Thread(target=self.uvicorn_server.run)
        self.uvicorn_server_thread.start()

        # wait for server to start
        while not self.uvicorn_server.started:
            time.sleep(0.001)

        self.init_done_event.set()

        log.info(
            f"{self.name} - Uvicorn server started, serving FastAPI app at "
            f"http://{self.uvicorn_inventory['host']}:{self.uvicorn_inventory['port']}"
        )

    def worker_exit(self):
        os.kill(os.getpid(), signal.SIGTERM)


# ------------------------------------------------------------------
# FastAPI REST API routes endpoints
# ------------------------------------------------------------------


def make_fast_api_app(worker, **config):

    app = FastAPI(**config)

    @app.post("/job")
    def post_job(
        service: str,
        task: str,
        args: List[Any] = None,
        kwargs: Dict[str, Any] = None,
        workers: str = "all",
        uuid: str = None,
        timeout: int = 600,
    ) -> Dict:
        """
        Method to post the job to NorFab
        """
        log.info(
            f"{worker.name} - received job post request, service {service}, task {task}, args {args}, kwargs {kwargs}"
        )
        res = worker.client.post(
            service=service,
            task=task,
            args=args,
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
        )
        return res

    @app.get("/job")
    def get_job(
        service: str,
        uuid: str,
        workers: str = "all",
        timeout: int = 600,
    ) -> Dict:
        """
        Method to get job results from NorFab
        """
        log.info(
            f"{worker.name} - received job get request, service {service}, uuid {uuid}"
        )
        res = worker.client.get(
            service=service,
            workers=workers,
            uuid=uuid,
            timeout=timeout,
        )
        return res

    @app.post("/run_job")
    def run_job(
        service: str,
        task: str,
        args: List[Any] = None,
        kwargs: Dict[str, Any] = None,
        workers: str = "all",
        timeout: int = 600,
        retry: int = 10,
    ) -> Dict:
        """
        Method to run job and return job results
        """
        log.warning(
            f"{worker.name} - received run job request, service {service}, task {task}, args {args}, kwargs {kwargs}"
        )
        res = worker.client.run_job(
            service=service,
            task=task,
            args=args,
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            retry=retry,
        )
        return res

    return app
