"""
Simple Local Inventory is an inventory plugin to load 
inventory data from locally stored files.

Sample inventory file

```yaml
broker:
  endpoint: "tcp://127.0.0.1:5555"
  
logging:
  handlers:
    terminal:
      level: CRITICAL
    file: 
      level: DEBUG

workers:
  nornir-*:
    - nornir/common.yaml  
  nornir-worker-1:
    - nornir/nornir-worker-1.yaml
    
topology:
  broker: True
  workers:
    - nornir-worker-1
```

where `nornir/common.yaml` contains

```
service: nornir
broker_endpoint: "tcp://127.0.0.1:5555"
runner:
  plugin: RetryRunner
  options: 
    num_workers: 100
    num_connectors: 10
    connect_retry: 3
    connect_backoff: 1000
    connect_splay: 100
    task_retry: 3
    task_backoff: 1000
    task_splay: 100
    reconnect_on_fail: True
    task_timeout: 600
```

and `nornir/nornir-worker-1.yaml` contains

```yaml
hosts: 
  csr1000v-1:
    hostname: sandbox-1.lab.com
    platform: cisco_ios
    username: developer
    password: secretpassword
  csr1000v-2:
    hostname: sandbox-2.lab.com
    platform: cisco_ios
    username: developer
    password: secretpassword
groups: {}
defaults: {}
```

Whenever inventory queried to provide data for worker with name `nornir-worker-1`
Simple Inventory iterates over `workers` dictionary and recursively merges 
data for keys (glob patterns) that matched worker name.
"""
import os
import fnmatch
import yaml
import logging
import copy

from typing import Any, Union

log = logging.getLogger(__name__)

# logs producer process configuration is just a QueueHandler attached to the
# root logger, which allows all messages to be sent to the queue. Producers are
# workers and broker processes
logging_config_producer = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"queue": {"class": "logging.handlers.QueueHandler", "queue": None}},
    "root": {"handlers": ["queue"], "level": "DEBUG"},
}

# listener is nfapi process
logging_config_listener = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "class": "logging.Formatter",
            "format": "%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "terminal": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": "CRITICAL",
        },
        "file": {
            "backupCount": 50,
            "class": "logging.handlers.RotatingFileHandler",
            "delay": False,
            "encoding": "utf-8",
            "filename": None,
            "formatter": "default",
            "level": "INFO",
            "maxBytes": 1024000,
            "mode": "a",
        },
    },
    "root": {"handlers": ["terminal", "file"], "level": "INFO"},
}


def make_logging_config(base_dir: str, inventory: dict) -> dict:
    """
    Helper function to combine inventory logging section and
    logging_config_listener dictionary.
    """
    logging_config_listener["handlers"]["file"]["filename"] = os.path.join(
        base_dir, "__norfab__", "logs", "norfab.log"
    )

    if not inventory:
        return logging_config_listener

    log_cfg = copy.deepcopy(inventory)
    ret = copy.deepcopy(logging_config_listener)

    # merge handlers
    ret["handlers"]["terminal"].update(log_cfg.get("handlers", {}).pop("terminal", {}))
    ret["handlers"]["file"].update(log_cfg.get("handlers", {}).pop("file", {}))
    ret["handlers"].update(log_cfg.pop("handlers", {}))
    # merge formatters
    ret["formatters"]["default"].update(
        log_cfg.get("formatters", {}).pop("default", {})
    )
    ret["formatters"].update(log_cfg.pop("formatters", {}))
    # merge root logger
    ret["root"].update(log_cfg.pop("root", {}))
    if "file" not in ret["root"]["handlers"]:
        ret["root"]["handlers"].append("file")
    if "terminal" not in ret["root"]["handlers"]:
        ret["root"]["handlers"].append("terminal")
    # merge remaining config
    ret.update(log_cfg)
    ret["disable_existing_loggers"] = False

    return ret


def merge_recursively(data: dict, merge: dict) -> None:
    """
    Function to merge two dictionaries data recursively.

    :param data: primary dictionary
    :param merge: dictionary to merge into primary overriding the content
    """
    assert isinstance(data, dict) and isinstance(
        merge, dict
    ), f"Only supports dictionary/dictionary data merges, not {type(data)}/{type(merge)}"
    for k, v in merge.items():
        if k in data:
            # merge two lists
            if isinstance(data[k], list) and isinstance(v, list):
                for i in v:
                    if i not in data[k]:
                        data[k].append(i)
            # recursively merge dictionaries
            elif isinstance(data[k], dict) and isinstance(v, dict):
                merge_recursively(data[k], v)
            # rewrite existing value with new data
            else:
                data[k] = v
        else:
            data[k] = v


class WorkersInventory:
    __slots__ = (
        "path",
        "data",
    )

    def __init__(self, path: str, data: dict) -> None:
        """
        Class to collect and server NorFab workers inventory data,
        forming it by recursively merging all data files that associated
        with the name of worker requesting inventory data.

        :param path: OS path to top folder with workers inventory data
        :param data: dictionary keyed by glob patterns matching workers names
            and values being a list of OS paths to files with workers
            inventory data
        """
        self.path, _ = os.path.split(path)
        self.data = data

    def __getitem__(self, name: str) -> Any:
        ret = {}

        # iterate over data keys and collect paths matching the item name
        paths = []
        for key, path_items in self.data.items():
            if fnmatch.fnmatchcase(name, key):
                for i in path_items:
                    if i not in paths:
                        paths.append(i)

        # iterate over path items, load and merge them
        for item in paths:
            if os.path.isfile(os.path.join(self.path, item)):
                with open(os.path.join(self.path, item), "r", encoding="utf-8") as f:
                    merge_recursively(ret, yaml.safe_load(f.read()))
            else:
                log.error(f"{os.path.join(self.path, item)} - file not found")
                raise FileNotFoundError(os.path.join(self.path, item))

        if ret:
            return ret
        else:
            raise KeyError(f"{name} has no inventory data")


class NorFabInventory:
    __slots__ = ("broker", "workers", "topology", "logging", "base_dir")

    def __init__(self, path: str) -> None:
        """
        NorFabInventory class to instantiate simple inventory.

        :param path: OS path to YAML file with inventory data
        """
        path = os.path.abspath(path)

        self.broker = {}
        self.workers = {}
        self.topology = {}
        self.base_dir = os.path.split(path)[0]
        self.load(path)

    def load(self, path: str) -> None:
        if not os.path.exists(path):
            log.error(f"{path} - inventory data not found")
            return

        assert os.path.isfile(path), "Path not pointing to a file"

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f.read())

        self.broker = data.pop("broker", {})
        self.workers = WorkersInventory(path, data.pop("workers", {}))
        self.topology = data.pop("topology", {})
        self.logging = make_logging_config(self.base_dir, data.pop("logging", {}))

    def __getitem__(self, key: str) -> Any:
        if key in self.__slots__:
            return getattr(self, key)
        else:
            return self.workers[key]

    def get(self, item: str, default: Any = None) -> Any:
        if item in self.__slots__:
            return getattr(self, item)
        else:
            return default
