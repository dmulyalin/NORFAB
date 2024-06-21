import json
import logging
import sys
import importlib.metadata
import yaml
import time

from jinja2 import Environment
from norfab.core.worker import MajorDomoWorker, NFPWorker
from norfab.core.inventory import merge_recursively
from nornir import InitNornir
from nornir_salt.plugins.tasks import (
    netmiko_send_commands,
    scrapli_send_commands,
    napalm_send_commands,
    napalm_configure,
    netmiko_send_config,
    scrapli_send_config,
    nr_test,
)
from nornir_salt.plugins.functions import FFun_functions, FFun, ResultSerializer
from nornir_salt.plugins.processors import (
    TestsProcessor,
    ToFileProcessor,
    DiffProcessor,
    DataProcessor,
)
from nornir_salt.utils.pydantic_models import modelTestsProcessorSuite
from typing import Union

log = logging.getLogger(__name__)


class UnsupportedPluginError(Exception):
    """Exception to raise when specified plugin not supported"""

    pass


class NornirWorker(NFPWorker):
    def __init__(
        self, broker, service, worker_name, exit_event=None, log_level="WARNING"
    ):
        super().__init__(broker, service, worker_name, exit_event, log_level)

        # get inventory from broker
        self.inventory = self.load_inventory()

        # pull Nornir inventory from Netbox
        self._pull_netbox_inventory()

        # initiate Nornir
        self._initiate_nornir()

    def _initiate_nornir(self):
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
            retry -= 1
            nb_inventory_data = self.client.run_job(
                b"netbox",
                "get_nornir_inventory",
                workers="any",
                kwargs=kwargs,
            )
            if nb_inventory_data:
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
        worker, data = nb_inventory_data.popitem()
        if data.get("hosts"):
            merge_recursively(self.inventory, data)
        else:
            log.warning(
                f"{self.name} - '{kwargs.get('instance', 'default')}' Netbox "
                f"instance returned no hosts data, worker '{worker}'"
            )

    def _add_processors(self, nr, kwargs):
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
        last = kwargs.pop("last", 1) if diff else None  # diff processor
        dp = kwargs.pop("dp", [])  # data processor
        xml_flake = kwargs.pop("xml_flake", "")  # data processor xml_flake function
        match = kwargs.pop("match", "")  # data processor match function
        before = kwargs.pop("before", 0)  # data processor match function
        run_ttp = kwargs.pop("run_ttp", None)  # data processor run_ttp function
        ttp_structure = kwargs.pop(
            "ttp_structure", "flat_list"
        )  # data processor run_ttp function
        remove_tasks = kwargs.pop(
            "remove_tasks", True
        )  # TTP remove parsed tasks output
        xpath = kwargs.pop("xpath", "")  # xpath DataProcessor
        jmespath = kwargs.pop("jmespath", "")  # jmespath DataProcessor
        iplkp = kwargs.pop("iplkp", "")  # iplkp - ip lookup - DataProcessor
        ntfsm = kwargs.pop("ntfsm", False)  # ntfsm - ntc-templates TextFSM parsing

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
        if diff:
            processors.append(
                DiffProcessor(
                    diff=diff,
                    last=int(last),
                    base_url=nornir_data["files_base_path"],
                    index=nornir_data["stats"]["proxy_minion_id"],
                )
            )
        # append ToFileProcessor as the last one in the sequence
        if tf and isinstance(tf, str):
            processors.append(
                ToFileProcessor(
                    tf=tf,
                    base_url=nornir_data["files_base_path"],
                    index=nornir_data["stats"]["proxy_minion_id"],
                    max_files=nornir_data["files_max_count"],
                    skip_failed=tf_skip_failed,
                    tf_index_lock=nornir_data["tf_index_lock"],
                )
            )

        return nr.with_processors(processors)

    # ----------------------------------------------------------------------
    # Nornir Service Functions that exposed for calling
    # ----------------------------------------------------------------------

    def get_nornir_hosts(self, **kwargs):
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        filtered_nornir = FFun(self.nr, **filters)
        return list(filtered_nornir.inventory.hosts)

    def get_nornir_inventory(self, **kwargs):
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        filtered_nornir = FFun(self.nr, **filters)
        return filtered_nornir.inventory.dict()

    def get_nornir_version(self, **kwargs):
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

        return libs

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
        ret = []
        downloaded_cmds = []

        # extract attributes
        add_details = kwargs.pop("add_details", False)  # ResultSerializer
        to_dict = kwargs.pop("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}

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
            log.debug(
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            return {} if to_dict else []

        # download TTP template if needed
        if run_ttp and run_ttp.startswith("nf://"):
            downloaded = self.fetch_file(run_ttp)
            kwargs["run_ttp"] = downloaded
            if downloaded is None:
                log.error(f"{self.name} - TTP template download failed '{run_ttp}'")
                return {} if to_dict else []

        nr = self._add_processors(filtered_nornir, kwargs)  # add processors

        # put a per-host list of commands to run
        if commands:
            commands = commands if isinstance(commands, list) else [commands]

            # download commands from broker if needed
            for command in commands:
                if command.startswith("nf://"):
                    downloaded = self.fetch_file(command)
                    if downloaded is not None:
                        downloaded_cmds.append(downloaded)
                    else:
                        log.error(f"{self.name} - command download failed '{command}'")
                else:
                    downloaded_cmds.append(command)

            # render commands using Jinja2 on a per-host basis
            for host_name, host_object in nr.inventory.hosts.items():
                context = {"host": host_object, "norfab": self.client, "nornir": self}
                rendered_commands = []
                for command in downloaded_cmds:
                    renderer = Environment(loader="BaseLoader").from_string(command)
                    rendered_command = renderer.render(**context)
                    rendered_commands.append(rendered_command)
                host_object.data["__task__"] = {"commands": rendered_commands}

        # run task
        log.debug(
            f"{self.name} - running cli commands '{commands}', kwargs '{kwargs}', is cli dry run - '{cli_dry_run}'"
        )
        if cli_dry_run is True:
            result = nr.run(
                task=nr_test, use_task_data="commands", name="cli_dry_run", **kwargs
            )
        else:
            result = nr.run(task=task_plugin, **kwargs)

        ret = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        # remove __task__ data
        for host_name, host_object in nr.inventory.hosts.items():
            _ = host_object.data.pop("__task__", None)

        return ret

    def task(self, plugin: str, **kwargs) -> dict:
        """
        Function to invoke any of supported Nornir task plugins. This function
        performs dynamic import of requested plugin function and executes
        ``nr.run`` using supplied args and kwargs

        :param plugin: (str) ``path.to.plugin.task_fun`` to import or ``nf://path/to/task.py``
            to download custom task
        :param kwargs: (dict) arguments to use with specified task plugin

        ``plugin`` attribute can refer to a file to fetch from file service. File must contain
        function named ``task`` accepting Nornir task object as a first positional
        argument, for example::

            # define connection name for RetryRunner to properly detect it
            CONNECTION_NAME = "netmiko"

            # create task function
            def task(nornir_task_object, *args, **kwargs):
                pass

        .. note:: ``CONNECTION_NAME`` must be defined within custom task function file if
            RetryRunner in use, otherwise connection retry logic skipped and connections
            to all hosts initiated simultaneously up to the number of ``num_workers``.
        """
        # extract attributes
        add_details = kwargs.pop("add_details", False)  # ResultSerializer
        to_dict = kwargs.pop("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}

        # download task from broker and load it
        if plugin.startswith("nf://"):
            function_text = self.fetch_file(plugin)
            if function_text is None:
                msg = f"{self.name} - '{plugin}' task plugin download failed"
                log.error(msg)
                return msg
            # load task function running exec
            globals_dict = {}
            exec(function_text, globals_dict, globals_dict)
            task_function = globals_dict["task"]
        # import task function
        else:
            # below same as "from nornir.plugins.tasks import task_fun as task_function"
            task_fun = plugin.split(".")[-1]
            try:
                module = __import__(plugin, fromlist=[""])
                task_function = getattr(module, task_fun)
            except Exception as e:
                msg = f"{self.name} - '{plugin}' task import failed with error '{e}'"
                log.error(msg)
                return msg

        self.nr.data.reset_failed_hosts()  # reset failed hosts
        filtered_nornir = FFun(self.nr, **filters)  # filter hosts

        # check if no hosts matched
        if not filtered_nornir.inventory.hosts:
            log.debug(
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            return {} if to_dict else []

        nr = self._add_processors(filtered_nornir, kwargs)  # add processors

        # run task
        log.debug(f"{self.name} - running Nornir task '{plugin}', kwargs '{kwargs}'")
        result = nr.run(task=task_function, **kwargs)

        return ResultSerializer(result, to_dict=to_dict, add_details=add_details)

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
        ret = []
        downloaded_cfg = []
        config = config if isinstance(config, list) else [config]

        # extract attributes
        add_details = kwargs.pop("add_details", False)  # ResultSerializer
        to_dict = kwargs.pop("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}

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
            log.debug(
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            return {} if to_dict else []

        nr = self._add_processors(filtered_nornir, kwargs)  # add processors

        # download config from broker if needed
        for command in config:
            if command.startswith("nf://"):
                downloaded = self.fetch_file(command)
                if downloaded is not None:
                    downloaded_cfg.append(downloaded)
                else:
                    log.error(
                        f"{self.name} - config command download failed '{command}'"
                    )
            else:
                downloaded_cfg.append(command)

        # render config using Jinja2 on a per-host basis
        for host_name, host_object in nr.inventory.hosts.items():
            context = {"host": host_object}
            host_object.data["__task__"] = {"config": []}
            for command in downloaded_cfg:
                renderer = Environment(loader="BaseLoader").from_string(command)
                host_object.data["__task__"]["config"].append(
                    renderer.render(**context)
                )

        # run task
        log.debug(
            f"{self.name} - sending config commands '{config}', kwargs '{kwargs}', is cfg_dry_run - '{cfg_dry_run}'"
        )
        if cfg_dry_run is True:
            result = nr.run(
                task=nr_test, use_task_data="config", name="cfg_dry_run", **kwargs
            )
        else:
            result = nr.run(task=task_plugin, **kwargs)

        ret = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        # remove __task__ data
        for host_name, host_object in nr.inventory.hosts.items():
            _ = host_object.data.pop("__task__", None)

        return ret

    def test(
        self,
        suite: Union[list, str],
        subset: str = None,
        dry_run: bool = False,
        remove_tasks: bool = True,
        failed_only: bool = False,
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
        """
        ret = []
        downloaded_suite = None
        tests = {}  # dictionary to hold per-host test suites

        # extract attributes
        add_details = kwargs.pop("add_details", False)  # ResultSerializer
        to_dict = kwargs.pop("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}

        self.nr.data.reset_failed_hosts()  # reset failed hosts
        filtered_nornir = FFun(self.nr, **filters)  # filter hosts

        # check if no hosts matched
        if not filtered_nornir.inventory.hosts:
            log.debug(
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            return {} if to_dict else []

        # download tests suite
        downloaded_suite = self.fetch_file(suite)
        if downloaded_suite is None:
            msg = f"{self.name} - '{suite}' suite download failed"
            log.error(msg)
            return msg

        # generate per-host test suites
        for host_name, host_object in filtered_nornir.inventory.hosts.items():
            context = {"host": host_object}
            # render suite using Jinja2
            try:
                renderer = Environment(loader="BaseLoader").from_string(
                    downloaded_suite
                )
                rendered_suite = renderer.render(**context)
            except Exception as e:
                msg = (
                    f"{self.name} - '{suite}' Jinja2 rendering failed with error '{e}'"
                )
                log.error(msg)
                return msg
            # load suit using YAML
            try:
                tests[host_name] = yaml.safe_load(rendered_suite)
            except Exception as e:
                msg = f"{self.name} - '{suite}' YAML load failed with error '{e}'"
                log.error(msg)
                return msg

        # validate tests suite
        try:
            _ = modelTestsProcessorSuite(tests=tests)
        except Exception as e:
            msg = f"{self.name} - '{suite}' suite validation failed with error '{e}'"
            log.error(msg)
            return msg

        # run task
        log.debug(f"{self.name} - running test '{suite}', is dry run - '{dry_run}'")
        if dry_run is True:
            result = filtered_nornir.run(
                task=nr_test, name="tests_dry_run", ret_data_per_host=tests
            )
        else:
            # add tests processor
            nr = self._add_processors(
                filtered_nornir,
                kwargs={
                    "tests": tests,
                    "remove_tasks": remove_tasks,
                    "failed_only": failed_only,
                    "subset": subset,
                },
            )
            result = nr.run(task=netmiko_send_commands, **kwargs)

        ret = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        return ret

    def netbox(
        self, task: str, cache: bool = False, cache_ttl: int = 3600, **kwargs
    ) -> dict:
        nb_ret = self.client.run_job(
            b"netbox",
            task,
            workers="any",
            kwargs=kwargs,
        )

        return nb_ret

    def netconf(self) -> dict:
        pass

    def file(self) -> dict:
        pass

    def gnmi(self) -> dict:
        pass

    def snmp(self) -> dict:
        pass

    def net(self) -> dict:
        pass
