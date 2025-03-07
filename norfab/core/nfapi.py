import logging
import logging.config
import time
import os
import signal
import sys

from typing import Union
from multiprocessing import Process, Event, Queue
from norfab.core.broker import NFPBroker
from norfab.core.client import NFPClient
from norfab.core.inventory import NorFabInventory
from norfab.core import exceptions as norfab_exceptions

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points, EntryPoint
else:
    from importlib.metadata import entry_points, EntryPoint

log = logging.getLogger(__name__)


def start_broker_process(
    endpoint,
    exit_event=None,
    inventory=None,
    log_level=None,
    log_queue=None,
    init_done_event=None,
):
    """
    Thread target function too start a broker process with the given parameters.

    Args:
        endpoint (str): The endpoint for the broker to connect to.
        exit_event (threading.Event, optional): An event to signal the broker to exit. Defaults to None.
        inventory (object, optional): An inventory object to be used by the broker. Defaults to None.
        log_level (int, optional): The logging level for the broker. Defaults to None.
        log_queue (queue.Queue, optional): A queue for logging messages. Defaults to None.
        init_done_event (threading.Event, optional): An event to signal that initialization is done. Defaults to None.
    """
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
    worker_plugin: object,
    inventory: str,
    broker_endpoint: str,
    worker_name: str,
    exit_event=None,
    log_level=None,
    log_queue=None,
    init_done_event=None,
):
    """
    Thread target function to start a worker process using the provided worker plugin.

    Args:
        worker_plugin (object): The worker plugin class to instantiate and run.
        inventory (str): The inventory data or path to be used by the worker.
        broker_endpoint (str): The endpoint of the broker to connect to.
        worker_name (str): The name of the worker.
        exit_event (threading.Event, optional): An event to signal the worker to exit. Defaults to None.
        log_level (int, optional): The logging level for the worker. Defaults to None.
        log_queue (queue.Queue, optional): The queue to use for logging. Defaults to None.
        init_done_event (threading.Event, optional): An event to signal when initialization is done. Defaults to None.
    """
    worker = worker_plugin(
        inventory=inventory,
        broker=broker_endpoint,
        worker_name=worker_name,
        exit_event=exit_event,
        init_done_event=init_done_event,
        log_level=log_level,
        log_queue=log_queue,
    )
    worker.work()


class NorFab:
    """
    NorFab is a class that provides an interface for interacting with the NorFab system.

    Attributes:
        client (NFPClient): The client instance for interfacing with the broker.
        broker (Process): The process instance for the broker.
        inventory (NorFabInventory): The inventory instance containing configuration data.
        workers_processes (dict): A dictionary mapping worker names to their process instances and initialization events.
        worker_plugins (dict): A dictionary mapping service names to their worker plugins.

    Args:
        inventory: OS path to NorFab inventory YAML file
        inventory_data: dictionary with NorFab inventory
        base_dir: OS path to base directory to anchor NorFab at
        log_level: one or supported logging levels - `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`

    Example:

        from norfab.core.nfapi import NorFab

        nf = NorFab(inventory="./inventory.yaml")
        nf.start(start_broker=True, workers=["my-worker-1"])
        NFCLIENT = nf.make_client()


    Example using dictionary inventory data:

        from norfab.core.nfapi import NorFab

        data = {
            'broker': {'endpoint': 'tcp://127.0.0.1:5555'},
            'workers': {'my-worker-1': ['workers/common.yaml'],
        }

        nf = NorFab(inventory_data=data, base_dir="./")
        nf.start(start_broker=True, workers=["my-worker-1"])
        NFCLIENT = nf.make_client()
    """

    client = None
    broker = None
    inventory = None
    workers_processes = {}
    worker_plugins = {}

    def __init__(
        self,
        inventory: str = "./inventory.yaml",
        inventory_data: dict = None,
        base_dir: str = None,
        log_level: str = None,
    ) -> None:
        self.exiting = False  # flag to signal that Norfab is exiting
        self.inventory = NorFabInventory(
            path=inventory, data=inventory_data, base_dir=base_dir
        )
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

        # find all workers plugins
        self.register_plugins()

    def register_plugins(self) -> None:
        """
        Registers worker plugins by iterating through the entry points in the
        'norfab.workers' group and registering each worker plugin.

        This method loads each entry point and registers it using the
        `register_worker_plugin` method.

        Raises:
            Any exceptions raised by the entry point loading or registration process.
        """
        # register worker plugins from entrypoints
        for entry_point in entry_points(group="norfab.workers"):
            self.register_worker_plugin(entry_point.name, entry_point)

        # register worker plugins from inventory
        for service_name, service_data in self.inventory.plugins.items():
            if service_data.get("worker"):
                self.register_worker_plugin(service_name, service_data["worker"])

    def register_worker_plugin(
        self, service_name: str, worker_plugin: Union[EntryPoint, object]
    ) -> None:
        """
        Registers a worker plugin for a given service.

        This method registers a worker plugin under the specified service name.
        If a plugin is already registered under the same service name and it is
        different from the provided plugin, an exception is raised.

        Args:
            service_name (str): The name of the service to register the plugin for.
            worker_plugin (object): The worker plugin to be registered.

        Raises:
            norfab_exceptions.ServicePluginAlreadyRegistered: If a different plugin
            is already registered under the same service name.
        """
        existing_plugin = self.worker_plugins.get(service_name)
        if existing_plugin is None:
            self.worker_plugins[service_name] = worker_plugin
        else:
            log.debug(
                f"Worker plugin {worker_plugin} can't be registered for "
                f"service '{service_name}' because plugin '{existing_plugin}' "
                f"was already registered under this service."
            )

    def handle_ctrl_c(self, signum, frame) -> None:
        """
        Handle the CTRL-C signal (SIGINT) to gracefully exit the application.

        This method is called when the user interrupts the program with a CTRL-C
        signal. It logs the interruption, performs necessary cleanup by calling
        `self.destroy()`, and then signals termination to the main process.

        Args:
            signum (int): The signal number (should be SIGINT).
            frame (FrameType): The current stack frame.

        Note:
            This method reassigns the SIGINT signal to the default handler and
            sends the SIGINT signal to the current process to ensure proper
            termination.
        """
        if self.exiting is False:
            msg = "CTRL-C, NorFab exiting, interrupted by user..."
            print(f"\n{msg}")
            log.info(msg)
            self.destroy()
            # signal termination to main process
            signal.signal(signal.SIGINT, signal.default_int_handler)
            os.kill(os.getpid(), signal.SIGINT)

    def setup_logging(self) -> None:
        """
        Sets up logging configuration and starts a log queue listener.

        This method updates the logging levels for all handlers based on the
        inventory, configures the logging system using the provided
        inventory, and starts a log queue listener to process logs from child
        processes.
        """
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

    def start_broker(self) -> None:
        """
        Starts the broker process if a broker endpoint is defined.
        This method initializes and starts a separate process for the broker using the
        provided broker endpoint. It waits for the broker to signal that it has fully
        initiated, with a timeout of 30 seconds. If the broker fails to start within
        this time, the method logs an error message and raises a SystemExit exception.

        Raises:
            SystemExit: If the broker fails to start within 30 seconds.

        Logs:
            Info: When the broker starts successfully.
            Error: If no broker endpoint is defined or if the broker fails to start.
        """
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

    def start_worker(self, worker_name, worker_data) -> None:
        """
        Starts a worker process if it is not already running.

        Args:
            worker_name (str): The name of the worker to start.
            worker_data (dict): A dictionary containing data about the worker, including any dependencies.

        Raises:
            RuntimeError: If a dependent process is not alive.
            norfab_exceptions.ServicePluginNotRegistered: If no worker plugin is registered for the worker's service.

        Returns:
            None
        """
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

            if self.worker_plugins.get(worker_inventory["service"]):
                worker_plugin = self.worker_plugins[worker_inventory["service"]]
                # load entry point on first call
                if isinstance(worker_plugin, EntryPoint):
                    worker_plugin = worker_plugin.load()
                    self.worker_plugins[worker_inventory["service"]] = worker_plugin
            else:
                raise norfab_exceptions.ServicePluginNotRegistered(
                    f"No worker plugin registered for service '{worker_inventory['service']}'"
                )

            self.workers_processes[worker_name] = {
                "process": Process(
                    target=start_worker_process,
                    args=(
                        worker_plugin,
                        self.inventory,
                        self.broker_endpoint,
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
        Starts the broker and specified workers.

        Args:
            start_broker (bool): If True, starts the broker if it is defined in the inventory topology.
            workers (Union[bool, list]): Determines which workers to start. If True, starts all workers defined in the inventory topology.
                                         If False or None, no workers are started. If a list, starts the specified workers.

        Returns:
            None

        Raises:
            KeyError: If a worker fails to start due to missing inventory data.
            FileNotFoundError: If a worker fails to start because the inventory file is not found.
            Exception: If a worker fails to start due to any other error.

        Notes:
            - The method waits for all workers to initialize within a specified timeout period.
            - If the initialization timeout expires, an error is logged and the system is destroyed.
            - After starting the workers, any startup hooks defined in the inventory are executed.
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
                    log.exception(
                        f"'{worker_name}' - failed to start worker, error '{e}'"
                    )

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

        # run startup hooks
        for f in self.inventory.hooks.get("startup", []):
            f["function"](self, *f.get("args", []), **f.get("kwargs", {}))

    def run(self):
        """
        Runs the main loop until a termination signal (CTRL+C) is received.
        This method checks if there are any broker or worker processes running.
        If none are detected, it logs a critical message and exits.
        Otherwise, it enters a loop that continues to run until the `exiting` flag is set to True.
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
        Gracefully stop all NORFAB processes and clean up resources.

        This method performs the following steps:

        1. Executes any registered exit hooks.
        2. Sets the `exiting` flag to indicate that NORFAB is shutting down.
        3. Stops all client processes.
        4. Stops all worker processes and waits for them to terminate.
        5. Stops the broker process and waits for it to terminate.
        6. Stops the logging queue listener.

        Returns:
            None
        """
        # run exit hooks
        for f in self.inventory.hooks.get("exit", []):
            f["function"](self, *f.get("args", []), **f.get("kwargs", {}))

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

    def make_client(self, broker_endpoint: str = None) -> NFPClient:
        """
        Creates and returns an NFPClient instance.

        Args:
            broker_endpoint (str, optional): The broker endpoint to connect to.
                If not provided, the instance's broker_endpoint attribute will be used.

        Returns:
            NFPClient: The created client instance if a broker endpoint is defined.
            None: If no broker endpoint is defined.

        Raises:
            None

        Notes:
            If this is the first client being created, it will be assigned to the
            instance's client attribute.
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
