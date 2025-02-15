import json
import logging
import sys
import threading
import time
import os
import signal
import importlib.metadata

from norfab.core.worker import NFPWorker, Result
from norfab.core.models import WorkerResult, ClientPostJobResponse, ClientGetJobResponse
from typing import Union, List, Dict, Any, Annotated


from pydantic import BaseModel

log = logging.getLogger(__name__)

try:
    import uvicorn
    from fastapi import FastAPI, Body

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
        service: str = b"fastapi",
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
        self.app = make_fast_api_app(
            worker=self, config=self.fastapi_inventory.get("fastapi", {})
        )

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

    def get_fastapi_inventory(self) -> dict:
        return Result(
            task=f"{self.name}:get_fastapi_inventory",
            result={
                **dict(self.fastapi_inventory),
                "uvicorn": self.uvicorn_inventory,
            },
        )

    def get_version(self):
        """
        Produce Python packages version report
        """
        libs = {
            "norfab": "",
            "fastapi": "",
            "uvicorn": "",
            "pydantic": "",
            "python-multipart": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(task=f"{self.name}:get_version", result=libs)

    def get_inventory(self):
        return Result(
            result={**self.fastapi_inventory, "uvicorn": self.uvicorn_inventory},
            task=f"{self.name}:get_inventory",
        )


# ------------------------------------------------------------------
# FastAPI REST API routes endpoints
# ------------------------------------------------------------------


class RunJobResponse(BaseModel):
    None


def make_fast_api_app(worker: object, config: dict) -> FastAPI:
    """
    Function to construct FastAPI application.

    :param worker: NorFab worker object
    :param config: dictionary with FastAPI configuration
    """

    app = FastAPI(**config)

    @app.post("/job")
    def post_job(
        service: Annotated[
            str, Body(description="The name of the service to post the job to")
        ],
        task: Annotated[
            str, Body(description="The task to be executed by the service")
        ],
        args: Annotated[
            List[Any], Body(description="A list of positional arguments for the task")
        ] = None,
        kwargs: Annotated[
            Dict[str, Any],
            Body(description="A dictionary of keyword arguments for the task"),
        ] = None,
        workers: Annotated[
            Union[str, List[str]], Body(description="The workers to dispatch the task")
        ] = "all",
        uuid: Annotated[
            str, Body(description="Optional a unique identifier to use for the job")
        ] = None,
        timeout: Annotated[
            int, Body(description="The timeout for the job in seconds")
        ] = 600,
    ) -> ClientPostJobResponse:
        """
        Method to post the job to NorFab.

        :param service: The name of the service to post the job to.
        :param task: The task to be executed by the service.
        :param args: A list of positional arguments for the task. Defaults to None.
        :param kwargs: A dictionary of keyword arguments for the task. Defaults to None.
        :param workers: The workers to dispatch the task. Defaults to "all".
        :param uuid: Optional a unique identifier to use for the job. Defaults to None.
        :param timeout: The timeout for the job in seconds. Defaults to 600.
        :returns: The response from the NorFab service.
        """
        log.debug(
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
        service: Annotated[
            str, Body(description="The name of the service to get the job from")
        ],
        uuid: Annotated[str, Body(description="A unique identifier for the job")],
        workers: Annotated[
            Union[str, List[str]],
            Body(description="The workers to dispatch the get request to"),
        ] = "all",
        timeout: Annotated[
            int, Body(description="The timeout for the job in seconds")
        ] = 600,
    ) -> ClientGetJobResponse:
        """
        Method to get job results from NorFab.

        :param service: The name of the service to get the job from.
        :param workers: The workers to dispatch the get request to. Defaults to "all".
        :param uuid: A unique identifier for the job.
        :param timeout: The timeout for the job get requests in seconds. Defaults to 600.
        :returns: The response from the NorFab service.
        """
        log.debug(
            f"{worker.name} - received job get request, service {service}, uuid {uuid}"
        )
        res = worker.client.get(
            service=service,
            uuid=uuid,
            workers=workers,
            timeout=timeout,
        )
        return res

    @app.post("/job/run")
    def run_job(
        service: Annotated[
            str, Body(description="The name of the service to post the job to")
        ],
        task: Annotated[
            str, Body(description="The task to be executed by the service")
        ],
        args: Annotated[
            List[Any], Body(description="A list of positional arguments for the task")
        ] = None,
        kwargs: Annotated[
            Dict[str, Any],
            Body(description="A dictionary of keyword arguments for the task"),
        ] = None,
        workers: Annotated[
            Union[str, List[str]], Body(description="The workers to dispatch the task")
        ] = "all",
        uuid: Annotated[
            str, Body(description="Optional a unique identifier to use for the job")
        ] = None,
        timeout: Annotated[
            int, Body(description="The timeout for the job in seconds")
        ] = 600,
        retry: Annotated[
            int, Body(description="The number of times to try and GET job results")
        ] = 10,
    ) -> Dict[str, WorkerResult]:
        """
        Method to run job and return job results synchronously. This function
        is blocking, internally it uses post/get methods to submit job request
        and waits for job results to come through for all workers request was
        dispatched to, exiting either once timeout expires or after all workers
        reported job result back to the client.

        :param service: The name of the service to post the job to.
        :param task: The task to be executed by the service.
        :param args: A list of positional arguments for the task. Defaults to None.
        :param kwargs: A dictionary of keyword arguments for the task. Defaults to None.
        :param workers: The workers to dispatch the task. Defaults to "all".
        :param uuid: A unique identifier for the job. Defaults to None.
        :param timeout: The timeout for the job in seconds. Defaults to 600.
        :param retry: The number of times to try and GET job results. Defaults to 10.
        :returns: The response from the NorFab service.
        """
        log.debug(
            f"{worker.name} - received run job request, service {service}, task {task}, args {args}, kwargs {kwargs}"
        )
        res = worker.client.run_job(
            service=service,
            task=task,
            uuid=uuid,
            args=args,
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            retry=retry,
        )
        return res

    return app
