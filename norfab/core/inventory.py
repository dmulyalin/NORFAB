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

from jinja2 import Environment
from typing import Any, Union, Dict, List

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


def render_jinja2_template(
    template: str, context: dict = None, filters: dict = None
) -> str:
    """
    Helper function to render a list of Jinja2 template.

    :param templates: list of template strings to render
    :param context: Jinja2 context dictionary
    :param filter: custom Jinja2 filters
    :returns: list of rendered strings
    """
    rendered = ""
    filters = filters or {}
    context = context or {}

    # get OS environment variables
    context["env"] = {k: v for k, v in os.environ.items()}

    # render template
    j2env = Environment(loader="BaseLoader")
    j2env.filters.update(filters)  # add custom filters
    renderer = j2env.from_string(template)
    rendered = renderer.render(**context)

    return rendered


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
            and values being a list of OS paths to files or dictionaries with workers
            inventory data
        """
        self.path = path
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
            if isinstance(item, str):
                if os.path.isfile(os.path.join(self.path, item)):
                    with open(
                        os.path.join(self.path, item), "r", encoding="utf-8"
                    ) as f:
                        rendered = render_jinja2_template(f.read())
                        merge_recursively(ret, yaml.safe_load(rendered))
                else:
                    log.error(f"{os.path.join(self.path, item)} - file not found")
                    raise FileNotFoundError(os.path.join(self.path, item))
            elif isinstance(item, dict):
                merge_recursively(ret, item)
            else:
                raise TypeError(f"Expecting string or dictionary not {type(item)}")

        if ret:
            return ret
        else:
            raise KeyError(f"{name} has no inventory data")


class NorFabInventory:
    __slots__ = ("broker", "workers", "topology", "logging", "base_dir")

    def __init__(
        self, path: str = None, data: dict = None, base_dir: str = None
    ) -> None:
        """
        NorFabInventory class to instantiate simple inventory either
        from file or from dictionary.

        :param path: OS path to YAML file with inventory data
        :param data: NorFab inventory dictionary
        """
        self.broker = {}
        self.workers = {}
        self.topology = {}
        self.logging = {}

        if data:
            self.base_dir = base_dir or os.path.split(os.getcwd())[0]
            self.load_data(data)
        elif path:
            path = os.path.abspath(path)
            self.base_dir = base_dir or os.path.split(path)[0]
            self.load_path(path)
        else:
            raise RuntimeError(
                "Either path to inventory.yaml or inventory data dictionary must be provided."
            )

    def load_data(self, data) -> None:
        self.broker = data.pop("broker", {})
        self.workers = WorkersInventory(self.base_dir, data.pop("workers", {}))
        self.topology = data.pop("topology", {})
        self.logging = make_logging_config(self.base_dir, data.pop("logging", {}))

    def load_path(self, path: str) -> None:
        if not os.path.exists(path):
            msg = f"inventory.yaml file not found under provided path `{path}`"
            log.critical(msg)
            raise FileNotFoundError(msg)

        assert os.path.isfile(path), "Path not pointing to a file"

        with open(path, "r", encoding="utf-8") as f:
            rendered = render_jinja2_template(f.read())
            data = yaml.safe_load(rendered)

        self.load_data(data)

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

    def dict(self) -> Dict[str, Any]:
        """
        Return serialized dictionary of inventory
        """
        return {
            "broker": self.broker,
            "workers": self.workers.data,
            "topology": self.topology,
            "logging": self.logging,
        }
