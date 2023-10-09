"""
NorFab Python API
=================

CLass that implements higher level Python API to work with NorFab.
"""
import logging

from multiprocessing import Process, Event
from norfab.core.broker import MajorDomoBroker
from norfab.core.client import MajorDomoClient
from norfab.services.nornir_worker import NornirWorker

logging.basicConfig(
    format="%(asctime)s.%(msecs)d [%(name)s:%(lineno)d %(levelname)s] -- %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

log = logging.getLogger(__name__)


def start_broker_process(endpoint, exit_event=None):
    exit_event = exit_event or Event()
    broker = MajorDomoBroker(exit_event)
    broker.bind(endpoint)
    broker.mediate()


def start_worker_process(broker_endpoint: str, service: str, worker_name: str, exit_event=None):
    exit_event = exit_event or Event()
    if service == "nornir":
        worker = NornirWorker(
            broker_endpoint, b"nornir", worker_name, exit_event
        )
        worker.work()
    else:
        raise RuntimeError(f"Unsupported service '{service}'")
    

class NorFab:
    """
    Utility class to implement Python API for interfacing with NorFab.
    """
    client = None
    broker = None
    workers = {}
    
    def __init__(self, broker_endpoint="tcp://*:5555"):
        self.broker_endpoint = broker_endpoint
        self.broker_exit_event = Event()
        self.workers_exit_event = Event()
        
    def start_broker(self):
        self.broker = Process(target=start_broker_process, args=(self.broker_endpoint, self.broker_exit_event,))
        self.broker.start()

    def start_worker(self, broker_endpoint="tcp://localhost:5555", service="nornir", worker_name="nornir-worker-1"):
        if worker_name not in self.workers:
            self.workers[worker_name] = Process(target=start_worker_process, args=(broker_endpoint, service, worker_name, self.workers_exit_event,))
            self.workers[worker_name].start()

    def make_client(self, broker_endpoint="tcp://localhost:5555"):
        client = MajorDomoClient(broker_endpoint)
        if self.client is None: # own the first client
            self.client = client
        return client
        
    def start(self):
        self.start_broker()
        self.start_worker()
        return self.make_client()

    def destroy(self):
        # stop workers
        self.workers_exit_event.set()
        while self.workers:
            _, w = self.workers.popitem()
            w.join()
        # stop broker
        self.broker_exit_event.set()
        self.broker.join()
        # stop client
        self.client.destroy()