import logging
import logging.config
import time
import os
import signal

from typing import Union
from multiprocessing import Process, Event, Queue
from norfab.core.broker import NFPBroker
from norfab.core.client import NFPClient
from norfab.core.inventory import NorFabInventory

log = logging.getLogger(__name__)

try:
    from norfab.workers.nornir_worker import NornirWorker
except Exception as e:
    log.warning(
        f"Failed to import NornirWorker, error - {e}, "
        f"this can be ignored if not planning to run Nornir worker."
    )

try:
    from norfab.workers.netbox_worker import NetboxWorker
except Exception as e:
    log.warning(
        f"Failed to import NetboxWorker, error - {e}, "
        f"this can be ignored if not planning to run Netbox worker."
    )

try:
    from norfab.workers.agent_worker import AgentWorker
except Exception as e:
    log.warning(
        f"Failed to import AgentWorker, error - {e}, "
        f"this can be ignored if not planning to run Agent worker."
    )

try:
    from norfab.workers.fastapi_worker import FastAPIWorker
except Exception as e:
    log.warning(
        f"Failed to import FastAPIWorker, error - {e}, "
        f"this can be ignored if not planning to run FastAPI worker."
    )


def start_broker_process(
    endpoint,
    exit_event=None,
    inventory=None,
    log_level=None,
    log_queue=None,
    init_done_event=None,
):
    broker = NFPBroker(
        endpoint=endpoint,
        exit_event=exit_event,
        inventory=inventory,
        log_level=log_level,
        log_queue=log_queue,
        init_done_event=init_done_event,
    )
    broker.mediate()


def start_worker_process(
    inventory: str,
    broker_endpoint: str,
    service: str,
    worker_name: str,
    exit_event=None,
    log_level=None,
    log_queue=None,
    init_done_event=None,
):
    try:
        if service == "nornir":
            worker = NornirWorker(
                inventory=inventory,
                broker=broker_endpoint,
                service=b"nornir",
                worker_name=worker_name,
                exit_event=exit_event,
                init_done_event=init_done_event,
                log_level=log_level,
                log_queue=log_queue,
            )
            worker.work()
        elif service == "netbox":
            worker = NetboxWorker(
                inventory=inventory,
                broker=broker_endpoint,
                service=b"netbox",
                worker_name=worker_name,
                exit_event=exit_event,
                init_done_event=init_done_event,
                log_level=log_level,
                log_queue=log_queue,
            )
            worker.work()
        elif service == "agent":
            worker = AgentWorker(
                inventory=inventory,
                broker=broker_endpoint,
                service=b"agent",
                worker_name=worker_name,
                exit_event=exit_event,
                init_done_event=init_done_event,
                log_level=log_level,
                log_queue=log_queue,
            )
            worker.work()
        elif service == "fastapi":
            worker = FastAPIWorker(
                inventory=inventory,
                broker=broker_endpoint,
                service=b"fastapi",
                worker_name=worker_name,
                exit_event=exit_event,
                init_done_event=init_done_event,
                log_level=log_level,
                log_queue=log_queue,
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
        self,
        inventory: str = "./inventory.yaml",
        log_level: str = None,
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
        self.exiting = False  # flag to signal that Norfab is exiting
        self.inventory = NorFabInventory(inventory)
        self.log_queue = Queue()
        self.log_level = log_level
        self.broker_endpoint = self.inventory.broker["endpoint"]
        self.workers_init_timeout = self.inventory.topology.get(
            "workers_init_timeout", 300
        )
        self.broker_exit_event = Event()
        self.workers_exit_event = Event()
        self.clients_exit_event = Event()

        # create needed folders to kickstart the logs
        os.makedirs(
            os.path.join(self.inventory.base_dir, "__norfab__", "files"), exist_ok=True
        )
        os.makedirs(
            os.path.join(self.inventory.base_dir, "__norfab__", "logs"), exist_ok=True
        )

        self.setup_logging()
        signal.signal(signal.SIGINT, self.handle_ctrl_c)

    def handle_ctrl_c(self, signum, frame):
        if self.exiting is False:
            msg = "CTRL-C, NorFab exiting, interrupted by user..."
            print(f"\n{msg}")
            log.info(msg)
            self.destroy()
            # signal termination to main process
            signal.signal(signal.SIGINT, signal.default_int_handler)
            os.kill(os.getpid(), signal.SIGINT)

    def setup_logging(self):
        # update logging levels for all handlers
        if self.log_level is not None:
            self.inventory["logging"]["root"]["level"] = self.log_level
            for handler in self.inventory["logging"]["handlers"].values():
                handler["level"] = self.log_level
        # configure logging
        logging.config.dictConfig(self.inventory["logging"])
        # start logs queue listener thread to process logs from child processes
        self.log_listener = logging.handlers.QueueListener(
            self.log_queue,
            *logging.getLogger("root").handlers,
            respect_handler_level=True,
        )
        self.log_listener.start()

    def start_broker(self):
        if self.broker_endpoint:
            init_done_event = Event()  # for worker to signal if its fully initiated

            self.broker = Process(
                target=start_broker_process,
                args=(
                    self.broker_endpoint,
                    self.broker_exit_event,
                    self.inventory,
                    self.log_level,
                    self.log_queue,
                    init_done_event,
                ),
            )
            self.broker.start()

            # wait for broker to start
            start_time = time.time()
            while 30 > time.time() - start_time:
                if init_done_event.is_set():
                    break
                time.sleep(0.1)
            else:
                log.info(
                    f"Broker failed to start in 30 seconds on '{self.broker_endpoint}'"
                )
                raise SystemExit()

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
                        self.inventory,
                        self.broker_endpoint,
                        worker_inventory["service"],
                        worker_name,
                        self.workers_exit_event,
                        self.log_level,
                        self.log_queue,
                        init_done_event,
                    ),
                ),
                "init_done": init_done_event,
            }

            self.workers_processes[worker_name]["process"].start()

    def start(
        self,
        start_broker: bool = True,
        workers: Union[bool, list] = True,
    ) -> None:
        """
        Main entry method to start NorFab components.

        :param start_broker: if True, starts broker process as defined in inventory
            ``topology`` section
        :param workers: list of worker names to start processes for or boolean, if True
            starts all workers defined in inventory ``topology`` sections
        :param client: If true return and instance of NorFab client
        """
        workers_to_start = set()

        # start the broker
        if start_broker is True and self.inventory.topology.get("broker") is True:
            self.start_broker()

        # decide on a set of workers to start
        if workers is False or workers is None:
            workers = []
        elif isinstance(workers, list) and workers:
            workers = [w.strip() for w in workers if w.strip()]
        # start workers defined in inventory
        elif workers is True:
            workers = self.inventory.topology.get("workers", [])

        # exit if no workers
        if not workers:
            return

        # form a list of workers to start
        for worker_name in workers:
            if isinstance(worker_name, dict):
                worker_name = tuple(worker_name)[0]
            if worker_name:
                workers_to_start.add(worker_name)
            else:
                log.error(f"'{worker_name}' - worker name is bad, skipping..")
                continue

        while workers_to_start != set(self.workers_processes.keys()):
            for worker in workers:
                # extract worker name and data/params
                if isinstance(worker, dict):
                    worker_name = tuple(worker)[0]
                    worker_data = worker[worker_name]
                elif worker:
                    worker_name = worker
                    worker_data = {}
                else:
                    continue
                # verify if need to start this worker
                if worker_name not in workers_to_start:
                    continue
                # start worker
                try:
                    self.start_worker(worker_name, worker_data)
                # if failed to start remove from workers to start
                except KeyError:
                    workers_to_start.discard(worker_name)
                    log.error(
                        f"'{worker_name}' - failed to start worker, no inventory data found"
                    )
                except FileNotFoundError as e:
                    workers_to_start.discard(worker_name)
                    log.error(
                        f"'{worker_name}' - failed to start worker, inventory file not found '{e}'"
                    )
                except Exception as e:
                    workers_to_start.discard(worker_name)
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
        if not self.broker and not self.workers_processes:
            log.critical(
                f"NorFab detected no broker or worker processes running, exiting.."
            )
            return

        while self.exiting is False:
            time.sleep(0.1)

    def destroy(self) -> None:
        """
        Stop NORFAB processes.
        """
        if self.exiting is not True:
            self.exiting = True  # indicate that NorFab already exiting
            # stop client
            log.info("NorFab is exiting, stopping clients")
            self.clients_exit_event.set()
            if self.client:
                self.client.destroy()
            # stop workers
            log.info("NorFab is exiting, stopping workers")
            self.workers_exit_event.set()
            while self.workers_processes:
                wname, w = self.workers_processes.popitem()
                w["process"].join()
                log.info(f"NorFab is exiting, stopped {wname} worker")
            # stop broker
            log.info("NorFab is exiting, stopping broker")
            self.broker_exit_event.set()
            if self.broker:
                self.broker.join()
            # stop logging thread
            log.info("NorFab is exiting, stopping logging queue listener")
            self.log_listener.stop()

    def make_client(self, broker_endpoint: str = None) -> NFPClient:
        """
        Make an instance of NorFab client

        :param broker_endpoint: (str), Broker URL to connect with
        """

        if broker_endpoint or self.broker_endpoint:
            client = NFPClient(
                self.inventory,
                broker_endpoint or self.broker_endpoint,
                "NFPClient",
                self.clients_exit_event,
            )
            if self.client is None:  # own the first client
                self.client = client
            return client
        else:
            log.error("Failed to make client, no broker endpoint defined")
            return None
