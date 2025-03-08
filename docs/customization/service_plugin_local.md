---
tags:
  - plugins
---

## NorFab Custom Service Plugin Tutorial

The simplest way to start with NorFab plugins is to create plugin within NorFab base directory, directory where `inventory.yaml` file resides.

In this tutorial we going to create `DummyService` and its worker. We going to define two tasks that worker can execute - `get_version` and `get_inventory` to retrieve worker's version and inventory details. In addition we going to define a set of custom nfcli shell commands to interact with custom `DummyService` from interactive command line shell.

To start with, define these folders structure and create all the files:

``` shell
└───norfab
    │   inventory.yaml
    │
    └───plugins
            dummy_worker_inventory.yaml
            dummy_service.py
```

Above are all the files we need, `plugins` directory name is arbitrary and can be anything, NorFab is not hardcoded to search for any of the directories, all plugins mapping defined withing `inventory.yaml` file.

### Dummy Service Custom Worker

Below is the source code of custom worker plugin for dummy service.

``` python title="plugins/dummy_service.py"
import logging
import sys
import importlib.metadata

from norfab.core.worker import NFPWorker, Result
from pydantic import BaseModel, Field
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
```

NorFab shell creates two commands:

- `dummy show version`
- `dummy show inventory`

### Configure NorFab Inventory

Populate `inventory.yaml` file with this content to run single `DummyService` worker:

``` yaml title="inventory.yaml"
broker:
  endpoint: "tcp://127.0.0.1:5555"

workers:
  dummy-worker-1:
    - plugins/dummy_worker_inventory.yaml

topology:
  broker: True
  workers:
    - dummy-worker-1

plugins:
  DummyService: 
    worker: "plugins.dummy_service:DummyServiceWorker"
    nfcli: 
      mount_path: "dummy"
      shell_model: "plugins.dummy_service:DummyServiceNfcliShell"
```

We also need to define inventoy for dummy service itself:

``` yaml title="plugins/dummy_worker_inventory.yaml"
service: DummyService

data:
  any: data
  goes: here

more:
  service: data
```

### Use Dummy Service from Nfcli Shell

Run nfcli command to start NorFab. NorFab should detect custom worker plugin and start `DummyService` worker process. After startup completes, can run dummy service commands.

```

```

### Use Dummy Service from Python API

```

```
