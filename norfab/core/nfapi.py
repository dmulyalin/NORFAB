import logging
import time

from multiprocessing import Process, Event
from norfab.core.broker import NFPBroker
from norfab.core.client import NFPClient
from norfab.core.inventory import NorFabInventory
from norfab.workers import NornirWorker, NetboxWorker

log = logging.getLogger(__name__)


def start_broker_process(
    endpoint, exit_event=None, inventory=None, log_level="WARNING"
):
    broker = NFPBroker(endpoint, exit_event, inventory, log_level)
    broker.mediate()


def start_worker_process(
    broker_endpoint: str,
    service: str,
    worker_name: str,
    exit_event=None,
    log_level="WARNING",
    init_done_event=None,
):
    try:
        if service == "nornir":
            worker = NornirWorker(
                broker_endpoint,
                b"nornir",
                worker_name,
                exit_event,
                init_done_event,
                log_level,
            )
            worker.work()
        elif service == "netbox":
            worker = NetboxWorker(
                broker_endpoint,
                b"netbox",
                worker_name,
                exit_event,
                init_done_event,
                log_level,
            )
            worker.work()
        else:
            raise RuntimeError(f"Unsupported service '{service}'")
    except KeyboardInterrupt:
        pass


class NorFab:
    """
    Utility class to implement Python API for interfacing with NorFab.
    """

    client = None
    broker = None
    inventory = None
    workers_processes = {}

    def __init__(
        self, inventory: str = "./inventory.yaml", log_level: str = "WARNING"
    ) -> None:
        """
        NorFab Python API Client initialization class

        ```
        from norfab.core.nfapi import NorFab

        nf = NorFab(inventory=inventory)
        nf.start(start_broker=True, workers=["my-worker-1"])
        NFCLIENT = nf.client
        ```

        :param inventory: OS path to NorFab inventory YAML file
        :param log_level: one or supported logging levels - `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`
        """
        self.inventory = NorFabInventory(inventory)
        self.log_level = log_level
        self.broker_endpoint = self.inventory.get("broker", {}).get("endpoint")
        self.workers_init_timeout = self.inventory.topology.get(
            "workers_init_timeout", 300
        )
        self.broker_exit_event = Event()
        self.workers_exit_event = Event()
        self.clients_exit_event = Event()

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
            log.info(
                f"Started broker, broker listening for connections on '{self.broker_endpoint}'"
            )
        else:
            log.error("Failed to start broker, no broker endpoint defined")

    def start_worker(self, worker_name, worker_data):
        if not self.workers_processes.get(worker_name):
            worker_inventory = self.inventory[worker_name]
            init_done_event = Event()  # for worker to signal if its fully initiated

            # check dependent processes
            if worker_data.get("depends_on"):
                # check if all dependent processes are alive
                for w in worker_data["depends_on"]:
                    if not self.workers_processes[w]["process"].is_alive():
                        raise RuntimeError(f"Dependent process is dead '{w}'")
                # check if all depended process fully initialized
                if not all(
                    self.workers_processes[w]["init_done"].is_set()
                    for w in worker_data["depends_on"]
                ):
                    return

            self.workers_processes[worker_name] = {
                "process": Process(
                    target=start_worker_process,
                    args=(
                        worker_inventory.get("broker_endpoint", self.broker_endpoint),
                        worker_inventory["service"],
                        worker_name,
                        self.workers_exit_event,
                        self.log_level,
                        init_done_event,
                    ),
                ),
                "init_done": init_done_event,
            }

            self.workers_processes[worker_name]["process"].start()

    def start(
        self,
        start_broker: bool = True,
        workers: list = True,
    ):
        """
        Main entry method to start NorFab components.

        :param start_broker: if True, starts broker process as defined in inventory
            ``topology`` section
        :param workers: list of worker names to start processes for or boolean, if True
            starts all workers defined in inventory ``topology`` sections
        :param client: If true return and instance of NorFab client
        """
        # start the broker
        if start_broker is True and self.inventory.topology.get("broker") is True:
            self.start_broker()

        # decide on a set of workers to start
        if workers is False or workers is None:
            workers = []
        elif isinstance(workers, list) and workers:
            workers = workers
        # start workers defined in inventory
        elif workers is True and self.inventory.topology.get("workers"):
            workers = self.inventory.topology["workers"]

        # start worker processes
        if not workers:
            return

        # form a list of workers to start
        workers_to_start = set()
        for worker_name in workers:
            if isinstance(worker_name, dict):
                worker_name = tuple(worker_name)[0]
            workers_to_start.add(worker_name)

        while workers_to_start != set(self.workers_processes.keys()):
            for worker in workers:
                # extract worker name and data/params
                if isinstance(worker, dict):
                    worker_name = tuple(worker)[0]
                    worker_data = worker[worker_name]
                else:
                    worker_name = worker
                    worker_data = {}
                # verify if need to start this worker
                if worker_name not in workers_to_start:
                    continue
                # start worker
                try:
                    self.start_worker(worker_name, worker_data)
                # if failed to start remove from workers to start
                except KeyError:
                    workers_to_start.remove(worker_name)
                    log.error(
                        f"'{worker_name}' - failed to start worker, no inventory data found"
                    )
                except FileNotFoundError as e:
                    workers_to_start.remove(worker_name)
                    log.error(
                        f"'{worker_name}' - failed to start worker, inventory file not found '{e}'"
                    )
                except Exception as e:
                    workers_to_start.remove(worker_name)
                    log.error(f"'{worker_name}' - failed to start worker, error '{e}'")

            time.sleep(0.01)

        # wait for workers to initialize
        start_time = time.time()
        while self.workers_init_timeout > time.time() - start_time:
            if all(w["init_done"].is_set() for w in self.workers_processes.values()):
                break
        else:
            log.error(
                f"TimeoutError - {self.workers_init_timeout}s workers init timeout expired"
            )
            self.destroy()

    def run(self):
        """
        Helper method to run the loop before CTRL+C called
        """
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nInterrupted by user...")
            self.destroy()

    def destroy(self) -> None:
        """
        Stop NORFAB processes.
        """
        # stop client
        self.clients_exit_event.set()
        if self.client:
            self.client.destroy()
        # stop workers
        self.workers_exit_event.set()
        while self.workers_processes:
            _, w = self.workers_processes.popitem()
            w["process"].join()
        # stop broker
        self.broker_exit_event.set()
        if self.broker:
            self.broker.join()

    def make_client(self, broker_endpoint: str = None) -> NFPClient:
        """
        Make an instance of NorFab client

        :param broker_endpoint: (str), Broker URL to connect with
        """

        if broker_endpoint or self.broker_endpoint:
            client = NFPClient(
                broker_endpoint or self.broker_endpoint,
                "NFPClient",
                self.log_level,
                self.clients_exit_event,
            )
            if self.client is None:  # own the first client
                self.client = client
            return client
        else:
            log.error("Failed to make client, no broker endpoint defined")
            return None
