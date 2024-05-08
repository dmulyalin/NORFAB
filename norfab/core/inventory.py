"""
# Simple Local Inventory

Inventory plugin to load inventory data from locally stored files.

Sample inventory file

```yaml
broker:
  endpoint: "tcp://127.0.0.1:5555"
  
workers:
  nornir-*:
    - nornir/common.yaml  
  nornir-worker-1:
    - nornir/nornir-worker-1.yaml
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
data for keys that matched worker name.
"""
import os
import fnmatch
import yaml
import logging

from typing import Any, Union

log = logging.getLogger(__name__)


class WorkersInventory:
    __slots__ = (
        "path",
        "data",
    )

    def __init__(self, path: str, data: dict) -> None:
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
                    self.merge_recursively(ret, yaml.safe_load(f.read()))
            else:
                log.error(f"{os.path.join(self.path, item)} - file not found")
                raise FileNotFoundError(os.path.join(self.path, item))

        if ret:
            return ret
        else:
            raise KeyError(f"{name} has no invenotry data")

    def merge_recursively(self, data: dict, merge: dict) -> None:
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
                    self.merge_recursively(data[k], v)
                # rewrite existing value with new data
                else:
                    data[k] = v
            else:
                data[k] = v


class NorFabInventory:
    __slots__ = ("broker", "workers", "topology")

    def __init__(self, path: str) -> None:
        self.broker = {}
        self.workers = {}
        self.topology = {}
        path = os.path.abspath(path)
        self.load(path)

    def load(self, path: str) -> None:
        if not os.path.exists(path):
            log.error(f"{path} - inventory data not found")
            return

        assert os.path.isfile(path), "Path not pointing to a file"

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f.read())

        self.broker = data.get("broker", {})
        self.workers = WorkersInventory(path, data.get("workers", {}))
        self.topology = data.get("topology", {})

    def __getitem__(self, key: str) -> Any:
        return self.workers[key]

    def get(self, item: str, default: Any) -> Any:
        if item in self.__slots__:
            return getattr(self, item)
        else:
            return default
