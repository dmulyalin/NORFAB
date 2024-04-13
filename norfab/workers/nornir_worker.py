import json
import logging

from norfab.core.worker import MajorDomoWorker, NFPWorker
from nornir import InitNornir

from nornir_salt.plugins.tasks import netmiko_send_commands
from nornir_salt.plugins.functions import FFun_functions, FFun, ResultSerializer

log = logging.getLogger(__name__)


# class NornirWorker(MajorDomoWorker):
class NornirWorker(NFPWorker):
    __slots__ = ("inventory", "nr")

    def __init__(
        self, broker, service, worker_name, exit_event=None, log_level="WARNING"
    ):
        super().__init__(broker, service, worker_name, exit_event, log_level)

        # get inventory from broker
        self.inventory = self.load_inventory()
        if self.inventory:
            self._initiate_nornir()
        else:
            log.critical(
                f"Broker {self.broker} returned no inventory for {self.name}, killing myself..."
            )
            self.destroy()

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

    def get_nornir_hosts(self, **kwargs):
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        filtered_nornir = FFun(self.nr, **filters)
        return list(filtered_nornir.inventory.hosts)
        
    def get_nornir_inventory(self, **kwargs):
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        filtered_nornir = FFun(self.nr, **filters)
        return filtered_nornir.inventory.dict()

    def cli(self, commands: list, plugin: str = "netmiko", **kwargs) -> dict:
        """
        Function to collect show commands output from devices using
        Command Line Interface (CLI)

        :param commands:
        :param plugin:
        :param hosts:
        """
        cmds = []
        commands = commands if isinstance(commands, list) else [commands]
        
        # extract ResultSerialiser arguments
        add_details = kwargs.pop("add_details", False)
        to_dict = kwargs.pop("to_dict", True)

        # reset failed hosts if any
        self.nr.data.reset_failed_hosts()

        if plugin == "netmiko":
            task_plugin = netmiko_send_commands

        # extract filters arguments and filter Nornir hosts
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        filtered_nornir = FFun(self.nr, **filters)

        # download commands from broker if needed
        for command in commands:
            if command.startswith("nf://"):
                downloaded_cmds = self.fetch_file(command)
                if downloaded_cmds is not None:
                    cmds.extend(downloaded_cmds.splitlines())
                else:
                    log.error(f"{self.name} - command download failed '{command}'")
            else:
                cmds.append(command)
                
        # render commands using Jinja2 on a per-host basis
        
        
        
        # add processors if any
        
        
        
        log.debug(f"{self.name} - running cli with commands '{cmds}', kwargs '{kwargs}'")
        
        # run task and return results
        if plugin == "netmiko":
            res = filtered_nornir.run(
                task=netmiko_send_commands, commands=cmds, **kwargs
            )

        return ResultSerializer(res, add_details=add_details, to_dict=to_dict)
