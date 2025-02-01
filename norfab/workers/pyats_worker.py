"""

### PyATS Worker Inventory Reference

TBD

"""
import json
import logging
import sys
from norfab.core.worker import NFPWorker

log = logging.getLogger(__name__)

try:
    from genie import testbed

    HAS_GENIE = True
except ImportError:
    HAS_GENIE = False
    log.error("PyATS worker - failed to import Genie library.")


class PyAtsWorker(NFPWorker):
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
        base_dir: str,
        broker: str,
        service: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
    ):
        super().__init__(base_dir, broker, service, worker_name, exit_event, log_level)
        self.init_done_event = init_done_event

        # get inventory from broker
        self.inventory = self.load_inventory()

        # pull PyAts inventory from Netbox
        self._pull_netbox_inventory()

        # initiate Nornir
        self._init_pyats()

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def _init_pyats(self):
        self.pyats = testbed.load(
            {
                "devices": self.inventory.get("devices", {}),
            }
        )

    def _pull_netbox_inventory(self):
        """Function to query inventory from Netbox"""
        pass
