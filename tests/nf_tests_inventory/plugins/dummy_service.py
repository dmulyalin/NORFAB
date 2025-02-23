import logging
import sys
import importlib.metadata
from norfab.core.worker import NFPWorker, Result
from pydantic import (
    BaseModel,
    Field,
)
from typing import Dict, Callable
from picle.models import Outputters

SERVICE = "DummyService"

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# DUMMY SERVICE WORKER CLASS
# ---------------------------------------------------------------------------------------------


class DummyServiceWorker(NFPWorker):
    def __init__(
        self,
        inventory,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
        log_queue: object = None,
    ):
        """
        Initialize the DummyService.

        Args:
            inventory: The inventory object.
            broker (str): The broker address.
            worker_name (str): The name of the worker.
            exit_event (threading.Event, optional): Event to signal service exit.
            init_done_event (threading.Event, optional): Event to signal initialization completion.
            log_level (str, optional): The logging level.
            log_queue (object, optional): The logging queue.
        """
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event

        # get inventory from broker
        self.dummy_inventory = self.load_inventory()

        # signal to NFAPI that finished initializing
        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def get_version(self) -> Dict:
        """
        Retrieves the version information for specified libraries and the current Python environment.

        Returns:
            Dict: A dictionary containing the version information for the following keys:
                - "norfab": The version of the 'norfab' package, if installed.
                - "python": The version of the Python interpreter.
                - "platform": The platform on which the Python interpreter is running.

        Note:
            If the 'norfab' package is not installed, its version will be an empty string.
        """

        libs = {
            "norfab": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(result=libs)

    def get_inventory(self) -> Dict:
        """
        Retrieves the dummy service inventory.

        Returns:
            Dict: A dictionary containing the dummy inventory data.
        """
        return Result(result=self.dummy_inventory)


# ---------------------------------------------------------------------------------------------
# DUMMY SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class DummyServiceShowCommandsModel(BaseModel):
    inventory: Callable = Field(
        "get_inventory",
        description="show Dummy service inventory data",
    )
    version: Callable = Field(
        "get_version",
        description="show Dummy service version report",
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json

    @staticmethod
    def get_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("DummyService", "get_inventory", workers=workers)
        return result

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("DummyService", "get_version", workers=workers)
        return result


class DummyServiceNfcliShell(BaseModel):
    show: DummyServiceShowCommandsModel = Field(
        None, description="Show Dummy service parameters"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[dummy]#"
