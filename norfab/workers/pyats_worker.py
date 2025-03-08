"""

### PyATS Worker Inventory Reference

TBD

"""
import json
import logging
import sys
from norfab.core.worker import NFPWorker

SERVICE = "pyats"

log = logging.getLogger(__name__)

try:
    from genie import testbed

    HAS_GENIE = True
except ImportError:
    HAS_GENIE = False
    log.error("PyATS worker - failed to import Genie library.")


class PyAtsWorker(NFPWorker):
    """
    Args:
        broker: broker URL to connect to
        worker_name: name of this worker
        exit_event: if set, worker need to stop/exit
        init_done_event: event to set when worker done initializing
        log_level: logging level of this worker
    """

    def __init__(
        self,
        inventory: str,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
    ):
        super().__init__(inventory, broker, SERVICE, worker_name, exit_event, log_level)
        self.init_done_event = init_done_event

        # get inventory from broker
        self.pyats_inventory = self.load_inventory()

        # pull PyAts inventory from Netbox
        self._pull_netbox_inventory()

        # initiate Nornir
        self._init_pyats()

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def _init_pyats(self):
        self.pyats = testbed.load(
            {
                "devices": self.pyats_inventory.get("devices", {}),
            }
        )

    def _pull_netbox_inventory(self):
        """Function to query inventory from Netbox"""
        pass
