import json

from norfab.core.worker import MajorDomoWorker
from nornir import InitNornir


class NornirWorker(MajorDomoWorker):
    RUNNER_CONFIG = {
        "plugin": "RetryRunner",
        "options": {
            "num_workers": 100,
            "num_connectors": 10,
            "connect_retry": 3,
            "connect_backoff": 1000,
            "connect_splay": 100,
            "task_retry": 3,
            "task_backoff": 1000,
            "task_splay": 100,
            "reconnect_on_fail": True,
            "task_timeout": 600,
        },
    }
    INVENTORY_CONFIG = {
        "plugin": "DictInventory",
        "options": {
            "hosts": {
                "csr1000v-1": {
                    "hostname": "sandbox-iosxe-1-recomm-1.cisco.com",
                    "platform": "cisco_ios",
                    "username": "developer",
                    "password": "lastorangerestoreball8876",
                },
                "csr1000v-2": {
                    "hostname": "sandbox-iosxe-2-recomm-1.cisco.com",
                    "platform": "cisco_ios",
                    "username": "developer",
                    "password": "lastorangerestoreball8876",
                }
            },
            "groups": {},
            "defaults": {},
        },
    }
    USER_DEFINED_CONFIG = {}
    
    def __init__(self, broker, service, worker_name, exit_event=None):
        super().__init__(broker, service, worker_name, exit_event)
        
        # initiate Nornir
        self.nr = InitNornir(
            logging={"enabled": False},
            runner=self.RUNNER_CONFIG,
            inventory=self.INVENTORY_CONFIG,
            user_defined=self.USER_DEFINED_CONFIG,
        )
        
        
    def work(self):
        reply = None
        while True:
            request = self.recv(reply)
            if request is None:
                break  # Worker was interrupted
                
            data = json.loads(request[0])
            task = data["task"]
            
            if task == "get_nornir_inventory":
                reply = self.nr.inventory.dict()
            elif task == "get_nornir_hosts":
                reply = list(self.nr.inventory.hosts)
            else:
                reply = f"Worker {self.name} unsupported task: '{task}'"
                
            # need to return reply as a list
            reply = [json.dumps(reply).encode("utf-8")]
