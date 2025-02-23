"""
#### Sample Fakenos Worker Inventory

``` yaml
service: fakenos
broker_endpoint: "tcp://127.0.0.1:5555"
default:
  password: user
  username: user
  port: [5000, 6000]
  server:
    plugin: ParamikoSshServer
    configuration:
      address: 127.0.0.1
      ssh_key_file: ./ssh-keys/ssh_host_rsa_key
      timeout: 1
  shell:
    configuration: {}
    plugin: CMDShell
  nos:
    configuration: {}
    plugin: cisco_ios
hosts:
  R1:
    password: fakenos
    port: 5001
    username: fakenos
    server:
      plugin: ParamikoSshServer
      configuration:
        address: 0.0.0.0
    shell:
      plugin: CMDShell
      configuration:
        intro: Custom SSH Shell
  R2: {}
  core-router:
    replicas: 2
    port: [5000, 6000]
```

"""
import logging
import time
import threading

from norfab.core.worker import NFPWorker
from fakenos import FakeNOS

SERVICE = "fakenos"

log = logging.getLogger(__name__)


def whatch_stop(network, exit_event):
    while True:
        if exit_event.is_set():
            network.stop()
            break
        else:
            time.sleep(0.01)


class FakenosWorker(NFPWorker):
    inventory = None

    def __init__(
        self,
        inventory,
        broker,
        worker_name,
        exit_event=None,
        log_level="WARNING",
    ):
        super().__init__(inventory, broker, SERVICE, worker_name, exit_event, log_level)

        # get inventory from broker
        self.fakenos_inventory = self.load_inventory()

        # start FakeNOS Network
        self.network = FakeNOS(
            inventory={
                "hosts": self.fakenos_inventory.get("hosts", {}),
                "default": self.fakenos_inventory.get("default", {}),
            }
        )
        self.network.start()
        whatch_stop_thread = threading.Thread(
            target=whatch_stop,
            args=(
                network,
                exit_event,
            ),
        )
        whatch_stop_thread.start()

        log.info(f"{self.name} - Initiated")

    # ----------------------------------------------------------------------
    # FakeNOS Service Functions that exposed for calling
    # ----------------------------------------------------------------------

    def stop(self):
        self.network.stop()
        return "Done"

    def start(self):
        self.network.start()
        return "Done"

    def restart(self):
        self.network.stop()
        self.network.start()
        return "Done"

    def get_inventory(self):
        return dict(self.fakenos_inventory)

    def get_hosts(self):
        return list(self.network.hosts)
