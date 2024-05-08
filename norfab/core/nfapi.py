"""
NorFab Python API
=================

CLass that implements higher level Python API to work with NorFab.
"""
import logging

from multiprocessing import Process, Event
from norfab.core.broker import NFPBroker
from norfab.core.client import NFPClient
from norfab.core.inventory import NorFabInventory
from norfab.workers.nornir_worker import NornirWorker

log = logging.getLogger(__name__)


def start_broker_process(
    endpoint, exit_event=None, inventory=None, log_level="WARNING"
):
    # broker = MajorDomoBroker(exit_event, inventory)
    broker = NFPBroker(endpoint, exit_event, inventory, log_level)
    # broker.bind(endpoint)
    broker.mediate()


def start_worker_process(
    broker_endpoint: str,
    service: str,
    worker_name: str,
    exit_event=None,
    log_level="WARNING",
):
    if service == "nornir":
        worker = NornirWorker(
            broker_endpoint, b"nornir", worker_name, exit_event, log_level
        )
        worker.work()
    else:
        raise RuntimeError(f"Unsupported service '{service}'")


def start_service_process(broker_endpoint: str, service: str, exit_event=None):
    if service == "nornir":
        service = NornirService(broker_endpoint, "nornir", exit_event)
        service.start()
    else:
        raise RuntimeError(f"Unsupported service '{service}'")


class NorFab:
    """
    Utility class to implement Python API for interfacing with NorFab.
    """

    client = None
    broker = None
    inventory = None
    workers = {}

    def __init__(self, inventory="./inventory.yaml", log_level="WARNING"):
        self.inventory = NorFabInventory(inventory)
        self.log_level = log_level
        self.broker_endpoint = self.inventory.get("broker", {}).get("endpoint")
        self.workers = {}
        self.broker_exit_event = Event()
        self.workers_exit_event = Event()
        self.services_exit_event = Event()

    def start_broker(self):
        if self.broker_endpoint:
            self.broker = Process(
                target=start_broker_process,
                args=(
                    self.broker_endpoint,
                    self.broker_exit_event,
                    self.inventory,
                    self.log_level,
                ),
            )
            self.broker.start()
        else:
            log.error("Failed to start broker, no broker endpoint defined")

    def start_worker(self, worker_name):
        if not self.workers.get(worker_name):
            try:
                worker_inventory = self.inventory[worker_name]
            except FileNotFoundError:
                return

            self.workers[worker_name] = Process(
                target=start_worker_process,
                args=(
                    worker_inventory.get("broker_endpoint", self.broker_endpoint),
                    worker_inventory["service"],
                    worker_name,
                    self.workers_exit_event,
                    self.log_level,
                ),
            )

            self.workers[worker_name].start()

    def make_client(self, broker_endpoint: str = None):
        """
        Make an instance of Norfab client

        :param broker_endpoint: (str), Broker URL to connect with
        """

        if broker_endpoint or self.broker_endpoint:
            client = NFPClient(
                broker_endpoint or self.broker_endpoint, "NFPClient", self.log_level
            )
            if self.client is None:  # own the first client
                self.client = client
            return client
        else:
            log.error("Failed to make client, no broker endpoint defined")
            return None

    def start(
        self,
        start_broker: bool = None,
        workers: list = None,
    ):
        """
        Function to start NorFab component.

        :param start_broker: if True, starts broker process
        :param workers: list of worker names to start processes for
        """
        if workers is None:
            workers = self.inventory.topology.get("workers", [])
        if start_broker is None:
            start_broker = self.inventory.topology.get("broker", False)

        if start_broker is True:
            self.start_broker()

        if workers and isinstance(workers, list):
            for worker_name in workers:
                try:
                    self.start_worker(worker_name)
                except KeyError:
                    log.error(f"No inventory data found for '{worker_name}'")

        self.make_client()

    def destroy(self):
        # stop workers
        self.workers_exit_event.set()
        while self.workers:
            _, w = self.workers.popitem()
            w.join()
        # stop broker
        self.broker_exit_event.set()
        if self.broker:
            self.broker.join()
        # stop client
        self.client.destroy()
