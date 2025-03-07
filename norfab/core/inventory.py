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
import sys

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
    Combines the inventory logging section with a predefined logging configuration.
    This function updates the predefined logging configuration with the settings
    provided in the inventory dictionary. It ensures that the log file is stored
    in the specified base directory and merges handlers, formatters, and root logger
    settings from the inventory into the predefined configuration.

    Args:
        base_dir (str): The base directory where the log file will be stored.
        inventory (dict): A dictionary containing logging configuration settings.

    Returns:
        dict: The combined logging configuration.
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
    Function to merge two dictionaries recursively.

    This function takes two dictionaries and merges the second dictionary into the first one.
    If both dictionaries have a key with a dictionary as its value, the function will merge
    those dictionaries recursively. If both dictionaries have a key with a list as its value,
    the function will append the elements of the second list to the first list, avoiding duplicates.
    For other types of values, the function will override the value in the first dictionary
    with the value from the second dictionary.

    Args:
        data: The primary dictionary to be merged into.
        merge: The dictionary to merge into the primary dictionary.

    Raises:
        AssertionError: If either of the inputs is not a dictionary.
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


def make_hooks(base_dir: str, hooks: List) -> Dict[str, List]:
    """
    Load and organize hook functions from specified modules.

    Args:
        base_dir (str): The base directory to include in the search path for modules.
        hooks (list): A list of dictionaries, each containing:
            - "function" (str): The full path to the hook function in the format 'module.submodule.function'.
            - "attachpoint" (str): The key to which the hook function should be attached.

    Returns:
        dict: A dictionary where keys are attach points and values are lists of hook function dictionaries.

    Raises:
        Exception: If there is an error importing or loading a hook function.
    """
    ret = {}

    # make sure to include current and base_dir directories in search path
    if os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())
    if base_dir not in sys.path:
        sys.path.append(base_dir)

    # load hook functions one by one
    for attachpoint, hooks in hooks.items():
        ret[attachpoint] = []
        for hook in hooks:
            try:
                imp_str, hook_function_name = hook["function"].split(":")
                log.info(f"Importing hook '{imp_str}' function '{hook_function_name}'")
                hook_module = __import__(imp_str, fromlist=[""])
                hook["function"] = getattr(hook_module, hook_function_name)
                ret[attachpoint].append(hook)
                log.info(f"Successfully loaded hook function {hook['function']}")
            except Exception as e:
                log.exception(f"Failed loading hook {hook}")

    return ret


def make_plugins(base_dir: str, plugins: Dict) -> Dict[str, Dict]:
    """
    Loads and initializes plugin functions for the given services.

    This function ensures that the current working directory and the specified
    base directory are included in the Python search path. It then iterates
    through the list of worker plugins provided in the `plugins` dictionary,
    dynamically imports the specified plugin classes, and adds them to the
    returned dictionary.

    Args:
        base_dir (str): The base directory to include in the search path.
        plugins (dict): A dictionary containing plugin configurations. The
                        dictionary should have a key "workers" which maps to a
                        list of plugin configurations. Each configuration should
                        include a "service" key and a "plugin" key in the format
                        "module:ClassName".

    Returns:
        dict: A dictionary with a key "workers" mapping to another dictionary
              where each key is a service name and each value is the corresponding
              plugin configuration with the plugin class loaded.

    Raises:
        Exception: If there is an error loading any of the plugin classes, an
                   exception is logged and the function continues with the next
                   plugin.

    Example:
        plugins = {
            "workers": [
                {
                    "service": "example_service",
                    "plugin": "my.path.to.example_module:ExamplePluginClass"
                }
            ]
        }
        result = make_plugins("/path/to/base_dir", plugins)
    """
    ret = {}

    # make sure to include current and base_dir directories in search path
    if os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())
    if base_dir not in sys.path:
        sys.path.append(base_dir)

    # load service plugins
    for service_name, service_data in plugins.items():
        ret[service_name] = service_data
        # import worker plugin
        if service_data.get("worker"):
            try:
                imp_str, plugin_class_name = service_data["worker"].split(":")
                log.info(
                    f"Importing '{plugin_class_name}' worker plugin class from '{imp_str}' module"
                )
                plugin_module = __import__(imp_str, fromlist=[""])
                service_data["worker"] = getattr(plugin_module, plugin_class_name)
                log.info(
                    f"Successfully loaded worker plugin {plugin_class_name} for service {service_name}"
                )
            except Exception as e:
                log.exception(
                    f"Failed loading worker plugin '{service_data['worker']}'"
                )
        # impot nfcli pydantic model
        if service_data.get("nfcli"):
            try:
                imp_str, plugin_class_name = service_data["nfcli"]["shell_model"].split(
                    ":"
                )
                log.info(
                    f"Importing '{plugin_class_name}' nfcli pydantic model plugin class from '{imp_str}' module"
                )
                plugin_module = __import__(imp_str, fromlist=[""])
                service_data["nfcli"]["shell_model"] = getattr(
                    plugin_module, plugin_class_name
                )
                log.info(
                    f"Successfully loaded nfcli pydantic model plugin class {plugin_class_name} for service {service_name}"
                )
            except Exception as e:
                log.exception(
                    f"Failed loading nfcli pydantic model plugin class '{service_data['nfcli']}'"
                )

    return ret


def render_jinja2_template(
    template: str, context: dict = None, filters: dict = None
) -> List[str]:
    """
    Renders a Jinja2 template with the given context and custom filters.

    Args:
        template (str): The Jinja2 template as a string.
        context (dict, optional): A dictionary containing the context variables for the template. Defaults to None.
        filters (dict, optional): A dictionary containing custom Jinja2 filters. Defaults to None.

    Returns:
        List[str]: The rendered template as a string.

    Raises:
        TemplateError: If there is an error in rendering the template.
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
    """
    Class to collect and server NorFab workers inventory data,
    forming it by recursively merging all data files that associated
    with the name of worker requesting inventory data.

    Attributes:
        path (str): OS path to the top folder with workers inventory data.
        data (dict): Dictionary keyed by glob patterns matching workers' names
            and values being a list of OS paths to files or dictionaries with workers'
            inventory data.

    Methods:
        __init__(path: str, data: dict) -> None:
            Initializes the WorkersInventory with the given path and data.
        __getitem__(name: str) -> Any:
            Retrieves and merges inventory data for the specified worker name.
            Raises a KeyError if no inventory data is found for the given name.
    """

    __slots__ = (
        "path",
        "data",
    )

    def __init__(self, path: str, data: dict) -> None:
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
    __slots__ = (
        "broker",
        "workers",
        "topology",
        "logging",
        "base_dir",
        "hooks",
        "plugins",
    )

    def __init__(
        self, path: str = None, data: dict = None, base_dir: str = None
    ) -> None:
        """
        Initialize NorFab Simple Inventory object.

        Args:
            path (str, optional): The file path to the inventory YAML file. Defaults to None.
            data (dict, optional): The inventory data dictionary. Defaults to None.
            base_dir (str, optional): The base directory for the inventory. Defaults to None.

        Raises:
            RuntimeError: If neither path nor data is provided.
        """
        self.broker = {}
        self.workers = {}
        self.topology = {}
        self.logging = {}
        self.hooks = {}
        self.plugins = {}

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
        """
        Load and initialize various components from the provided data dictionary.

        Args:
            data (dict): A dictionary containing configuration data for initializing
                         the broker, workers, topology, logging, hooks, and plugins.

        Returns:
            None
        """
        self.broker = data.pop("broker", {})
        self.workers = WorkersInventory(self.base_dir, data.pop("workers", {}))
        self.topology = data.pop("topology", {})
        self.logging = make_logging_config(self.base_dir, data.pop("logging", {}))
        self.hooks = make_hooks(self.base_dir, data.pop("hooks", {}))
        self.plugins = make_plugins(self.base_dir, data.pop("plugins", {}))

    def load_path(self, path: str) -> None:
        """
        Loads inventory data from a specified file path.

        Args:
            path (str): The file path to the inventory.yaml file.

        Raises:
            FileNotFoundError: If the file does not exist at the specified path.
            AssertionError: If the path does not point to a file.
        """
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
        """
        Retrieve an item from the inventory.

        Args:
            key (str): The key of the item to retrieve.

        Returns:
            Any: The value associated with the given key.

        Raises:
            KeyError: If the key is not found in the inventory.
        """
        if key in self.__slots__:
            return getattr(self, key)
        else:
            return self.workers[key]

    def get(self, item: str, default: Any = None) -> Any:
        """
        Retrieve the value of the specified item from the inventory.

        Args:
            item (str): The name of the item to retrieve.
            default (Any, optional): The value to return if the item is not found. Defaults to None.

        Returns:
            Any: The value of the specified item if it exists, otherwise the default value.
        """
        if item in self.__slots__:
            return getattr(self, item)
        else:
            return default

    def dict(self) -> Dict[str, Any]:
        """
        Convert the inventory object to a dictionary representation.

        Returns:
            Dict[str, Any]: A dictionary containing the inventory details:
                - broker (str): The broker information.
                - workers (Any): The data related to workers.
                - topology (Any): The topology information.
                - logging (Any): The logging configuration.
                - hooks (dict): A dictionary containing startup and exit hooks, where each
                    hook's function is represented by its name.
        """
        ret = {
            "broker": self.broker,
            "workers": self.workers.data,
            "topology": self.topology,
            "logging": self.logging,
            "hooks": {},
            "plugins": {},
        }

        # add hooks replacing hook function with its name
        for attachpoint, hooks in self.hooks.items():
            ret["hooks"][attachpoint] = []
            for hook in hooks:
                ret["hooks"][attachpoint].append(
                    {**hook, "function": hook["function"].__name__}
                )

        # add plugins replacing plugin classes with their name
        for service_name, service_data in self.plugins.items():
            ret["plugins"][service_name] = {**service_data}
            if service_data.get("worker"):
                ret["plugins"][service_name]["worker"] = service_data["worker"].__name__
            if service_data.get("nfcli"):
                ret["plugins"][service_name]["nfcli"]["shell_model"] = service_data[
                    "nfcli"
                ]["shell_model"].__name__

        return ret
