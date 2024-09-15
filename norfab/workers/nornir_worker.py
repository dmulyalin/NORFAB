"""

### Nornir Worker Inventory Reference

- ``watchdog_interval`` - watchdog run interval in seconds, default is 30
- ``connections_idle_timeout`` - watchdog connection idle timeout, 
    default is ``None`` - no timeout, connection always kept alive, 
    if set to 0, connections disconnected imminently after task 
    completed, if positive number, connection disconnected after 
    not being used for over ``connections_idle_timeout``

"""

import json
import logging
import sys
import importlib.metadata
import yaml
import time
import copy
import os
import hashlib

from jinja2 import Environment, FileSystemLoader
from norfab.core.worker import NFPWorker, Result
from norfab.core.inventory import merge_recursively
from norfab.core.exceptions import UnsupportedPluginError
from nornir import InitNornir
from nornir_salt.plugins.tasks import (
    netmiko_send_commands,
    scrapli_send_commands,
    napalm_send_commands,
    napalm_configure,
    netmiko_send_config,
    scrapli_send_config,
    nr_test,
    connections as nr_connections,
)
from nornir_salt.plugins.functions import (
    FFun_functions,
    FFun,
    ResultSerializer,
    HostsKeepalive,
)
from nornir_salt.plugins.processors import (
    TestsProcessor,
    ToFileProcessor,
    DiffProcessor,
    DataProcessor,
    NorFabEventProcessor,
)
from nornir_salt.utils.pydantic_models import modelTestsProcessorSuite
from typing import Union
from threading import Thread, Lock

log = logging.getLogger(__name__)


class WatchDog(Thread):
    """
    Class to monitor Nornir worker performance
    """

    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.watchdog_interval = worker.inventory.get("watchdog_interval", 30)
        self.memory_threshold_mbyte = worker.inventory.get(
            "memory_threshold_mbyte", 1000
        )
        self.memory_threshold_action = worker.inventory.get(
            "memory_threshold_action", "log"
        )
        self.connections_idle_timeout = worker.inventory.get(
            "connections_idle_timeout", None
        )
        self.connections_data = {}  # store connections use timestamps
        self.started_at = time.time()

        # stats attributes
        self.runs = 0
        self.idle_connections_cleaned = 0
        self.dead_connections_cleaned = 0

    def stats(self):
        return {
            "runs": self.runs,
            "timestamp": time.ctime(),
            "alive": int(time.time() - self.started_at),
            "dead_connections_cleaned": self.dead_connections_cleaned,
            "idle_connections_cleaned": self.idle_connections_cleaned,
        }

    def configuration(self):
        return {
            "watchdog_interval": self.watchdog_interval,
            "connections_idle_timeout": self.connections_idle_timeout,
        }

    def connections_get(self):
        return {
            "connections": self.connections_data,
        }

    def connections_update(self, nr, plugin: str) -> None:
        """
        Function to update connection use timestamps for each host

        :param nr: Nornir object
        :param plugin: connection plugin name
        """
        conn_stats = {
            "last_use": None,
            "last_keepealive": None,
            "keepalive_count": 0,
        }
        for host_name in nr.inventory.hosts:
            self.connections_data.setdefault(host_name, {})
            self.connections_data[host_name].setdefault(plugin, conn_stats.copy())
            self.connections_data[host_name][plugin]["last_use"] = time.ctime()
        log.info(
            f"{self.worker.name} - updated connections use timestamps for '{plugin}'"
        )

    def connections_clean(self):
        """
        Check if need to tear down connections that are idle -
        not being used over connections_idle_timeout
        """
        # dictionary keyed by plugin name and value as a list of hosts
        disconnect = {}
        if not self.worker.connections_lock.acquire(blocking=False):
            return
        try:
            # if idle timeout not set, connections don't age out
            if self.connections_idle_timeout is None:
                disconnect = {}
            # disconnect all connections for all hosts
            elif self.connections_idle_timeout == 0:
                disconnect = {"all": list(self.connections_data.keys())}
            # only disconnect aged/idle connections
            elif self.connections_idle_timeout > 0:
                for host_name, plugins in self.connections_data.items():
                    for plugin, conn_data in plugins.items():
                        last_use = time.mktime(time.strptime(conn_data["last_use"]))
                        age = time.time() - last_use
                        if age > self.connections_idle_timeout:
                            disconnect.setdefault(plugin, [])
                            disconnect[plugin].append(host_name)
            # run task to disconnect connections for aged hosts
            for plugin, hosts in disconnect.items():
                if not hosts:
                    continue
                aged_hosts = FFun(self.worker.nr, FL=hosts)
                aged_hosts.run(task=nr_connections, call="close", conn_name=plugin)
                log.debug(
                    f"{self.worker.name} watchdog, disconnected '{plugin}' "
                    f"connections for '{', '.join(hosts)}'"
                )
                self.idle_connections_cleaned += len(hosts)
                # wipe out connections data if all connection closed
                if plugin == "all":
                    self.connections_data = {}
                    break
                # remove disconnected plugin from host's connections_data
                for host in hosts:
                    self.connections_data[host].pop(plugin)
                    if not self.connections_data[host]:
                        self.connections_data.pop(host)
        except Exception as e:
            msg = f"{self.worker.name} - watchdog failed to close idle connections, error: {e}"
            log.error(msg)
        finally:
            self.worker.connections_lock.release()

    def connections_keepalive(self):
        """Keepalive connections and clean up dead connections if any"""
        if self.connections_idle_timeout == 0:  # do not keepalive if idle is 0
            return
        if not self.worker.connections_lock.acquire(blocking=False):
            return
        try:
            log.debug(f"{self.worker.name} - watchdog running connections keepalive")
            stats = HostsKeepalive(self.worker.nr)
            self.dead_connections_cleaned += stats["dead_connections_cleaned"]
            # update connections statistics
            for plugins in self.connections_data.values():
                for plugin in plugins.values():
                    plugin["last_keepealive"] = time.ctime()
                    plugin["keepalive_count"] += 1
        except Exception as e:
            msg = f"{self.worker.name} - watchdog HostsKeepalive check error: {e}"
            log.error(msg)
        finally:
            self.worker.connections_lock.release()

    def run(self):
        slept = 0
        while not self.worker.exit_event.is_set():
            # continue sleeping for watchdog_interval
            if slept < self.watchdog_interval:
                time.sleep(0.1)
                slept += 0.1
                continue

            # run the tasks
            self.connections_clean()
            self.connections_keepalive()

            # update counters
            self.runs += 1

            slept = 0  # reset to go to sleep


class NornirWorker(NFPWorker):
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
        broker: str,
        service: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
    ):
        super().__init__(broker, service, worker_name, exit_event, log_level)
        self.init_done_event = init_done_event
        self.tf_base_path = os.path.join(self.base_dir, "tf")

        # misc attributes
        self.connections_lock = Lock()

        # get inventory from broker
        self.inventory = self.load_inventory()

        # pull Nornir inventory from Netbox
        self._pull_netbox_inventory()

        # initiate Nornir
        self._init_nornir()

        # initiate watchdog
        self.watchdog = WatchDog(self)
        self.watchdog.start()

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def _init_nornir(self):
        # initiate Nornir
        self.nr = InitNornir(
            logging=self.inventory.get("logging", {"enabled": False}),
            runner=self.inventory.get("runner", {}),
            inventory={
                "plugin": "DictInventory",
                "options": {
                    "hosts": self.inventory.get("hosts", {}),
                    "groups": self.inventory.get("groups", {}),
                    "defaults": self.inventory.get("defaults", {}),
                },
            },
            user_defined=self.inventory.get("user_defined", {}),
        )

    def _pull_netbox_inventory(self):
        """Function to query inventory from Netbox"""
        # exit if has no Netbox data in inventory
        if isinstance(self.inventory.get("netbox"), dict):
            kwargs = self.inventory["netbox"]
        elif self.inventory.get("netbox") is True:
            kwargs = {}
        else:
            return

        # extract parameters from kwargs
        retry = kwargs.pop("retry", 3)
        retry_interval = kwargs.pop("retry_interval", 5)

        # check if need to add devices list
        if "filters" not in kwargs and "devices" not in kwargs:
            if self.inventory.get("hosts"):
                kwargs["devices"] = list(self.inventory["hosts"])
            else:
                log.critical(
                    f"{self.name} - inventory has no hosts, netbox "
                    f"filters or devices defined"
                )
                return

        # get Nornir inventory from netbox
        while retry:
            if self.destroy_event.is_set():
                return
            retry -= 1
            nb_inventory_data = self.client.run_job(
                b"netbox",
                "get_nornir_inventory",
                workers="any",
                kwargs=kwargs,
                job_timeout=30,
            )
            if not nb_inventory_data:
                continue
            worker, data = nb_inventory_data.popitem()
            if data["result"] and not data["failed"]:
                break
            log.warning(
                f"{self.name} - Netbox service returned no Nornir "
                f"inventory data, retrying..."
            )
            time.sleep(retry_interval)
        else:
            log.error(
                f"{self.name} - Netbox service returned no Nornir "
                f"inventory data after 3 attempts, is it running?"
            )
            return

        # merge Netbox inventory into Nornir inventory
        if data["result"].get("hosts"):
            merge_recursively(self.inventory, data["result"])
        else:
            log.warning(
                f"{self.name} - '{kwargs.get('instance', 'default')}' Netbox "
                f"instance returned no hosts data, worker '{worker}'"
            )

    def _add_processors(self, nr, kwargs: dict):
        """
        Helper function to extract processors arguments and add processors
        to Nornir.

        :param kwargs: (dict) dictionary with kwargs
        :param nr: (obj) Nornir object to add processors to
        :return: (obj) Nornir object with added processors
        """
        processors = []

        # extract parameters
        tf = kwargs.pop("tf", None)  # to file
        tf_skip_failed = kwargs.pop("tf_skip_failed", False)  # to file
        diff = kwargs.pop("diff", "")  # diff processor
        diff_last = kwargs.pop("diff_last", 1) if diff else None  # diff processor
        dp = kwargs.pop("dp", [])  # data processor
        xml_flake = kwargs.pop("xml_flake", "")  # data processor xml_flake function
        match = kwargs.pop("match", "")  # data processor match function
        before = kwargs.pop("before", 0)  # data processor match function
        run_ttp = kwargs.pop("run_ttp", None)  # data processor run_ttp function
        ttp_structure = kwargs.pop(
            "ttp_structure", "flat_list"
        )  # data processor run_ttp function
        remove_tasks = kwargs.pop("remove_tasks", True)  # tests and/or run_ttp
        tests = kwargs.pop("tests", None)  # tests
        subset = kwargs.pop("subset", [])  # tests
        failed_only = kwargs.pop("failed_only", False)  # tests
        xpath = kwargs.pop("xpath", "")  # xpath DataProcessor
        jmespath = kwargs.pop("jmespath", "")  # jmespath DataProcessor
        iplkp = kwargs.pop("iplkp", "")  # iplkp - ip lookup - DataProcessor
        ntfsm = kwargs.pop("ntfsm", False)  # ntfsm - ntc-templates TextFSM parsing
        progress = kwargs.pop(
            "progress", False
        )  # Emit progress events using NorFabEventProcessor

        # add processors if any
        if dp:
            processors.append(DataProcessor(dp))
        if iplkp:
            processors.append(
                DataProcessor(
                    [
                        {
                            "fun": "iplkp",
                            "use_dns": True if iplkp == "dns" else False,
                            "use_csv": iplkp if iplkp else False,
                        }
                    ]
                )
            )
        if xml_flake:
            processors.append(
                DataProcessor([{"fun": "xml_flake", "pattern": xml_flake}])
            )
        if xpath:
            processors.append(
                DataProcessor(
                    [{"fun": "xpath", "expr": xpath, "recover": True, "rm_ns": True}]
                )
            )
        if jmespath:
            processors.append(DataProcessor([{"fun": "jmespath", "expr": jmespath}]))
        if match:
            processors.append(
                DataProcessor([{"fun": "match", "pattern": match, "before": before}])
            )
        if run_ttp:
            processors.append(
                DataProcessor(
                    [
                        {
                            "fun": "run_ttp",
                            "template": run_ttp,
                            "res_kwargs": {"structure": ttp_structure},
                            "remove_tasks": remove_tasks,
                        }
                    ]
                )
            )
        if ntfsm:
            processors.append(DataProcessor([{"fun": "ntfsm"}]))
        if tests:
            processors.append(
                TestsProcessor(
                    tests=tests,
                    remove_tasks=remove_tasks,
                    failed_only=failed_only,
                    build_per_host_tests=True,
                    subset=subset,
                    render_tests=False,
                )
            )
        if diff:
            processors.append(
                DiffProcessor(
                    diff=diff,
                    last=int(diff_last),
                    base_url=self.tf_base_path,
                    index=self.name,
                )
            )
        if progress:
            processors.append(NorFabEventProcessor(worker=self))
        # append ToFileProcessor as the last one in the sequence
        if tf and isinstance(tf, str):
            processors.append(
                ToFileProcessor(
                    tf=tf,
                    base_url=self.tf_base_path,
                    index=self.name,
                    max_files=1000,
                    skip_failed=tf_skip_failed,
                    tf_index_lock=None,
                )
            )

        return nr.with_processors(processors)

    def render_jinja2_templates(
        self, templates: list[str], context: dict, filters: dict = None
    ) -> list[str]:
        """
        helper function to render a list of Jinja2 templates

        :param templates: list of template strings to render
        :param context: Jinja2 context dictionary
        :param filter: custom Jinja2 filters
        :returns: list of rendered strings
        """
        rendered = []
        filters = filters or {}
        for template in templates:
            if template.startswith("nf://"):
                filepath = self.fetch_jinja2(template)
                searchpath, filename = os.path.split(filepath)
                j2env = Environment(loader=FileSystemLoader(searchpath))
                renderer = j2env.get_template(filename)
            else:
                j2env = Environment(loader="BaseLoader")
                renderer = j2env.from_string(template)
            j2env.filters.update(filters)  # add custom filters
            rendered.append(renderer.render(**context))

        return rendered

    # ----------------------------------------------------------------------
    # Nornir Service Functions that exposed for calling
    # ----------------------------------------------------------------------

    def get_nornir_hosts(self, details: bool = False, **kwargs: dict) -> list:
        """
        Produce a list of hosts managed by this worker

        :param kwargs: dictionary of nornir-salt Fx filters
        """
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        filtered_nornir = FFun(self.nr, **filters)
        if details:
            return Result(
                result={
                    host_name: {
                        "platform": str(host.platform),
                        "hostname": str(host.hostname),
                        "port": str(host.port),
                        "groups": [str(g) for g in host.groups],
                        "username": str(host.username),
                    }
                    for host_name, host in filtered_nornir.inventory.hosts.items()
                }
            )
        else:
            return Result(result=list(filtered_nornir.inventory.hosts))

    def get_nornir_inventory(self, **kwargs: dict) -> dict:
        """
        Retrieve running Nornir inventory for requested hosts

        :param kwargs: dictionary of nornir-salt Fx filters
        """
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        filtered_nornir = FFun(self.nr, **filters)
        return Result(
            result=filtered_nornir.inventory.dict(), task="get_nornir_inventory"
        )

    def get_nornir_version(self):
        """
        Produce Python packages version report
        """
        libs = {
            "scrapli": "",
            "scrapli-netconf": "",
            "scrapli-community": "",
            "paramiko": "",
            "netmiko": "",
            "napalm": "",
            "nornir": "",
            "ncclient": "",
            "nornir-netmiko": "",
            "nornir-napalm": "",
            "nornir-scrapli": "",
            "nornir-utils": "",
            "tabulate": "",
            "xmltodict": "",
            "puresnmp": "",
            "pygnmi": "",
            "pyyaml": "",
            "jmespath": "",
            "jinja2": "",
            "ttp": "",
            "nornir-salt": "",
            "lxml": "",
            "ttp-templates": "",
            "ntc-templates": "",
            "cerberus": "",
            "pydantic": "",
            "requests": "",
            "textfsm": "",
            "N2G": "",
            "dnspython": "",
            "pythonping": "",
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

    def get_watchdog_stats(self):
        return Result(result=self.watchdog.stats())

    def get_watchdog_configuration(self):
        return Result(result=self.watchdog.configuration())

    def get_watchdog_connections(self):
        return Result(result=self.watchdog.connections_get())

    def task(self, plugin: str, **kwargs) -> Result:
        """
        Function to invoke any of supported Nornir task plugins. This function
        performs dynamic import of requested plugin function and executes
        ``nr.run`` using supplied args and kwargs

        ``plugin`` attribute can refer to a file to fetch from file service. File must contain
        function named ``task`` accepting Nornir task object as a first positional
        argument, for example:

        ```python
        # define connection name for RetryRunner to properly detect it
        CONNECTION_NAME = "netmiko"

        # create task function
        def task(nornir_task_object, *args, **kwargs):
            pass
        ```

        !!! note "CONNECTION_NAME"

            ``CONNECTION_NAME`` must be defined within custom task function file if
            RetryRunner in use, otherwise connection retry logic skipped and connections
            to all hosts initiated simultaneously up to the number of ``num_workers``.

        :param plugin: (str) ``path.to.plugin.task_fun`` to import or ``nf://path/to/task.py``
            to download custom task
        :param kwargs: (dict) arguments to use with specified task plugin
        """
        # extract attributes
        add_details = kwargs.pop("add_details", False)  # ResultSerializer
        to_dict = kwargs.pop("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        ret = Result(task=f"{self.name}:task", result={} if to_dict else [])

        # download task from broker and load it
        if plugin.startswith("nf://"):
            function_text = self.fetch_file(plugin)
            if function_text is None:
                raise FileNotFoundError(
                    f"{self.name} - '{plugin}' task plugin download failed"
                )

            # load task function running exec
            globals_dict = {}
            exec(function_text, globals_dict, globals_dict)
            task_function = globals_dict["task"]
        # import task function
        else:
            # below same as "from nornir.plugins.tasks import task_fun as task_function"
            task_fun = plugin.split(".")[-1]
            module = __import__(plugin, fromlist=[""])
            task_function = getattr(module, task_fun)

        self.nr.data.reset_failed_hosts()  # reset failed hosts
        filtered_nornir = FFun(self.nr, **filters)  # filter hosts

        # check if no hosts matched
        if not filtered_nornir.inventory.hosts:
            msg = (
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            log.debug(msg)
            ret.messages.append(msg)
            return ret

        nr = self._add_processors(filtered_nornir, kwargs)  # add processors

        # run task
        log.debug(f"{self.name} - running Nornir task '{plugin}', kwargs '{kwargs}'")
        with self.connections_lock:
            result = nr.run(task=task_function, **kwargs)
        ret.result = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        self.watchdog.connections_clean()

        return ret

    def cli(
        self,
        commands: list = None,
        plugin: str = "netmiko",
        cli_dry_run: bool = False,
        run_ttp: str = None,
        **kwargs,
    ) -> dict:
        """
        Function to collect show commands output from devices using
        Command Line Interface (CLI)

        :param commands: list of commands to send to devices
        :param plugin: plugin name to use - ``netmiko``, ``scrapli``, ``napalm``
        :param cli_dry_run: do not send commands to devices just return them
        :param run_ttp: TTP Template to run
        """
        add_details = kwargs.pop("add_details", False)  # ResultSerializer
        to_dict = kwargs.pop("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        downloaded_cmds = []
        ret = Result(task=f"{self.name}:cli", result={} if to_dict else [])

        # decide on what send commands task plugin to use
        if plugin == "netmiko":
            task_plugin = netmiko_send_commands
        elif plugin == "scrapli":
            task_plugin = scrapli_send_commands
        elif plugin == "napalm":
            task_plugin = napalm_send_commands
        else:
            raise UnsupportedPluginError(f"Plugin '{plugin}' not supported")

        self.nr.data.reset_failed_hosts()  # reset failed hosts
        filtered_nornir = FFun(self.nr, **filters)  # filter hosts

        # check if no hosts matched
        if not filtered_nornir.inventory.hosts:
            msg = (
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            log.debug(msg)
            ret.messages.append(msg)
            return ret

        # download TTP template if needed
        if run_ttp and run_ttp.startswith("nf://"):
            downloaded = self.fetch_file(run_ttp)
            kwargs["run_ttp"] = downloaded
            if downloaded is None:
                msg = f"{self.name} - TTP template download failed '{run_ttp}'"
                raise FileNotFoundError(msg)
            self.event(f"TTP Template downloaded '{run_ttp}'")

        nr = self._add_processors(filtered_nornir, kwargs)  # add processors

        # render commands using Jinja2 on a per-host basis
        if commands:
            commands = commands if isinstance(commands, list) else [commands]
            for host in nr.inventory.hosts.values():
                rendered = self.render_jinja2_templates(
                    templates=commands,
                    context={"host": host, "norfab": self.client, "nornir": self},
                )
                host.data["__task__"] = {"commands": rendered}

        # run task
        log.debug(
            f"{self.name} - running cli commands '{commands}', kwargs '{kwargs}', is cli dry run - '{cli_dry_run}'"
        )
        if cli_dry_run is True:
            result = nr.run(
                task=nr_test, use_task_data="commands", name="cli_dry_run", **kwargs
            )
        else:
            with self.connections_lock:
                result = nr.run(task=task_plugin, **kwargs)

        ret.result = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        # remove __task__ data
        for host_name, host_object in nr.inventory.hosts.items():
            _ = host_object.data.pop("__task__", None)

        self.watchdog.connections_update(nr, plugin)
        self.watchdog.connections_clean()

        return ret

    def nb_get_next_ip(self, *args, **kwargs):
        """Method to query next available IP address from Netbox service"""
        reply = self.client.run_job(
            "netbox",
            "get_next_ip",
            args=args,
            kwargs=kwargs,
            workers="any",
            job_timeout=30,
        )
        # reply is a dict of {worker_name: results_dict}
        result = list(reply.values())[0]

        return result["result"]

    def cfg(
        self, config: list, plugin: str = "netmiko", cfg_dry_run: bool = False, **kwargs
    ) -> dict:
        """
        Function to send configuration commands to devices using
        Command Line Interface (CLI)

        :param config: list of commands to send to devices
        :param plugin: plugin name to use - ``netmiko``, ``scrapli``, ``napalm``
        :param cfg_dry_run: do not send commands to devices just return them
        """
        downloaded_cfg = []
        config = config if isinstance(config, list) else [config]
        add_details = kwargs.pop("add_details", False)  # ResultSerializer
        to_dict = kwargs.pop("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        ret = Result(task=f"{self.name}:cfg", result={} if to_dict else [])

        # decide on what send commands task plugin to use
        if plugin == "netmiko":
            task_plugin = netmiko_send_config
        elif plugin == "scrapli":
            task_plugin = scrapli_send_config
        elif plugin == "napalm":
            task_plugin = napalm_configure
        else:
            raise UnsupportedPluginError(f"Plugin '{plugin}' not supported")

        self.nr.data.reset_failed_hosts()  # reset failed hosts
        filtered_nornir = FFun(self.nr, **filters)  # filter hosts

        # check if no hosts matched
        if not filtered_nornir.inventory.hosts:
            msg = (
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            ret.messages.append(msg)
            log.debug(msg)
            return ret

        nr = self._add_processors(filtered_nornir, kwargs)  # add processors

        # render config using Jinja2 on a per-host basis
        for host in nr.inventory.hosts.values():
            rendered = self.render_jinja2_templates(
                templates=config,
                context={"host": host, "norfab": self.client, "nornir": self},
                filters={"nb_get_next_ip": self.nb_get_next_ip},
            )
            host.data["__task__"] = {"config": rendered}

        # run task
        log.debug(
            f"{self.name} - sending config commands '{config}', kwargs '{kwargs}', is cfg_dry_run - '{cfg_dry_run}'"
        )
        if cfg_dry_run is True:
            result = nr.run(
                task=nr_test, use_task_data="config", name="cfg_dry_run", **kwargs
            )
        else:
            with self.connections_lock:
                result = nr.run(task=task_plugin, **kwargs)
            ret.changed = True

        ret.result = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        # remove __task__ data
        for host_name, host_object in nr.inventory.hosts.items():
            _ = host_object.data.pop("__task__", None)

        self.watchdog.connections_update(nr, plugin)
        self.watchdog.connections_clean()

        return ret

    def test(
        self,
        suite: Union[list, str],
        subset: str = None,
        dry_run: bool = False,
        remove_tasks: bool = True,
        failed_only: bool = False,
        return_tests_suite: bool = False,
        **kwargs,
    ) -> dict:
        """
        Function to tests data obtained from devices.

        :param suite: path to YAML file with tests
        :param dry_run: if True, returns produced per-host tests suite content only
        :param subset: list or string with comma separated non case sensitive glob
            patterns to filter tests' by name, subset argument ignored by dry run
        :param failed_only: if True returns test results for failed tests only
        :param remove_tasks: if False results will include other tasks output
        :param return_tests_suite: if True returns rendered per-host tests suite
            content in addition to test results using dictionary with ``results``
            and ``suite`` keys
        :param kwargs: any additional arguments to pass on to Nornir service task
        """
        downloaded_suite = None
        tests = {}  # dictionary to hold per-host test suites
        add_details = kwargs.get("add_details", False)  # ResultSerializer
        to_dict = kwargs.get("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        ret = Result(task=f"{self.name}:test", result={} if to_dict else [])
        suites = {}  # dictionary to hold combined test suites

        self.nr.data.reset_failed_hosts()  # reset failed hosts
        filtered_nornir = FFun(self.nr, **filters)  # filter hosts

        # check if no hosts matched
        if not filtered_nornir.inventory.hosts:
            msg = (
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            log.debug(msg)
            ret.messages.append(msg)
            if return_tests_suite is True:
                ret.result = {"test_results": [], "suite": {}}
            return ret

        # download tests suite
        downloaded_suite = self.fetch_jinja2(suite)

        # generate per-host test suites
        searchpath, template = os.path.split(downloaded_suite)
        for host_name, host in filtered_nornir.inventory.hosts.items():
            context = {"host": host, "norfab": self.client, "nornir": self}
            # render suite using Jinja2
            try:
                j2env = Environment(loader=FileSystemLoader(searchpath))
                renderer = j2env.get_template(template)
                rendered_suite = renderer.render(**context)
            except Exception as e:
                msg = f"{self.name} - '{suite}' Jinja2 rendering failed: '{e}'"
                raise RuntimeError(msg)
            # load suit using YAML
            try:
                tests[host_name] = yaml.safe_load(rendered_suite)
            except Exception as e:
                msg = f"{self.name} - '{suite}' YAML load failed: '{e}'"
                raise RuntimeError(msg)

        # validate tests suite
        try:
            _ = modelTestsProcessorSuite(tests=tests)
        except Exception as e:
            msg = f"{self.name} - '{suite}' suite validation failed: '{e}'"
            raise RuntimeError(msg)

        # download pattern, schema and custom function files
        for host_name in tests.keys():
            for index, item in enumerate(tests[host_name]):
                for k in ["pattern", "schema", "function_file"]:
                    if self.is_url(item.get(k)):
                        item[k] = self.fetch_file(
                            item[k], raise_on_fail=True, read=True
                        )
                        if k == "function_file":
                            item["function_text"] = item.pop(k)
                tests[host_name][index] = item

        # save per-host tests suite content before mutating it
        if return_tests_suite is True:
            return_suite = copy.deepcopy(tests)

        log.debug(f"{self.name} - running test '{suite}', is dry run - '{dry_run}'")
        # run dry run task
        if dry_run is True:
            result = filtered_nornir.run(
                task=nr_test, name="tests_dry_run", ret_data_per_host=tests
            )
            ret.result = ResultSerializer(
                result, to_dict=to_dict, add_details=add_details
            )
        # combine per-host tests in suites based on task task and arguments
        # Why - to run tests using any nornir service tasks with various arguments
        else:
            for host_name, host_tests in tests.items():
                for test in host_tests:
                    dhash = hashlib.md5()
                    test_args = test.pop("norfab", {})
                    nrtask = test_args.get("nrtask", "cli")
                    assert nrtask in [
                        "cli",
                        "network",
                        "cfg",
                        "task",
                    ], f"{self.name} - unsupported NorFab Nornir Service task '{nrtask}'"
                    test_json = json.dumps(test_args, sort_keys=True).encode()
                    dhash.update(test_json)
                    test_hash = dhash.hexdigest()
                    suites.setdefault(test_hash, {"params": test_args, "tests": {}})
                    suites[test_hash]["tests"].setdefault(host_name, [])
                    suites[test_hash]["tests"][host_name].append(test)
            log.debug(
                f"{self.name} - combined per-host tests suites based on NorFab Nornir Service task and arguments:\n{suites}"
            )
            # run test suites collecting output from devices
            for tests_suite in suites.values():
                nrtask = tests_suite["params"].pop("nrtask", "cli")
                function_kwargs = {
                    **tests_suite["params"],
                    **kwargs,
                    **filters,
                    "tests": tests_suite["tests"],
                    "remove_tasks": remove_tasks,
                    "failed_only": failed_only,
                    "subset": subset,
                }
                result = getattr(self, nrtask)(
                    **function_kwargs
                )  # returns Result object
                # save test results into overall results
                if to_dict == True:
                    for host_name, host_res in result.result.items():
                        ret.result.setdefault(host_name, {})
                        ret.result[host_name].update(host_res)
                else:
                    ret.result.extend(result.result)

        # check if need to return tests suite content
        if return_tests_suite is True:
            ret.result = {"test_results": ret.result, "suite": return_suite}

        return ret

    def netconf(self) -> dict:
        pass

    def file(self) -> dict:
        pass

    def gnmi(self) -> dict:
        pass

    def snmp(self) -> dict:
        pass

    def network(self, fun, **kwargs) -> dict:
        """
        Function to call various network related utility functions.

        :param fun: (str) utility function name to call
        :param kwargs: (dict) function arguments

        Available utility functions.

        **resolve_dns** function

        resolves hosts' hostname DNS returning IP addresses using
        ``nornir_salt.plugins.tasks.network.resolve_dns`` Nornir-Salt
        function.

        **ping** function

        Function to execute ICMP ping to host using
        ``nornir_salt.plugins.tasks.network.ping`` Nornir-Salt
        function.
        """
        kwargs["call"] = fun
        return self.task(
            plugin="nornir_salt.plugins.tasks.network",
            **kwargs,
        )
