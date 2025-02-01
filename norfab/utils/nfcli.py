import argparse
import os

from norfab.clients.picle_shell_client import start_picle_shell
from norfab.core.nfapi import NorFab

norfab_base_inventory = """
# broker settings
broker:
  endpoint: "tcp://127.0.0.1:5555"
  public_key: "I%%LVg$#t2Aw(SC/G%UPf&U3gYMk=hZ{p}J4/uFu"
  
# workers inventory section
workers:
  nornir-*:
    - nornir/common.yaml  
  nornir-worker-1:
    - nornir/nornir-worker-1.yaml
    
# list what entities we want to start on this node
topology:
  broker: True
  workers:
    - nornir-worker-1
"""

nornir_service_base_inventory_common = """
service: nornir
broker_endpoint: "tcp://127.0.0.1:5555"

# Nornir inventory and configuration
runner: 
  plugin: RetryRunner
hosts: {}
default: {}
groups: {}
"""

nornir_service_base_inventory_worker = """
hosts:
  ios-device-1:
    hostname: 192.168.1.1
    platform: cisco_ios
    username: admin
    password: admin
"""


def nfcli():
    # form argparser menu:
    description_text = """
    """
    argparser = argparse.ArgumentParser(
        description=(
            f"Norfab PICLE Shell Tool"
            f"\n\n"
            f"Sample Usage:\n"
            f"  nf -i ./norfab_lab/inventory.yaml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_options = argparser.add_argument_group(description=description_text)

    # add CLI arguments
    run_options.add_argument(
        "-i",
        "--inventory",
        action="store",
        dest="INVENTORY",
        default="inventory.yaml",
        type=str,
        help="OS Path to YAML file with NORFAB inventory data",
    )
    run_options.add_argument(
        "-b",
        "--broker",
        action="store_true",
        dest="BROKER",
        default=None,
        help="Start NorFab broker process",
    )
    run_options.add_argument(
        "-w",
        "--workers",
        action="store_true",
        dest="WORKERS",
        default=None,
        help="Start NorFab worker processes as defined in inventory file",
    )
    run_options.add_argument(
        "-c",
        "--client",
        action="store_true",
        dest="CLIENT",
        default=False,
        help="Start NorFab interactive shell client",
    )
    run_options.add_argument(
        "-l",
        "--log-level",
        action="store",
        dest="LOGLEVEL",
        default=None,
        help="Set logging level debug, info, warning, error",
    )
    run_options.add_argument(
        "-s",
        "--shell",
        action="store_true",
        dest="SHELL",
        default=True,
        help="Start local NorFab broker, workers and client interactive shell",
    )
    run_options.add_argument(
        "--create-env",
        action="store",
        dest="CREATE_ENV",
        default=None,
        help="Create NorFab environment",
    )

    # extract argparser arguments:
    args = argparser.parse_args()
    INVENTORY = args.INVENTORY
    WORKERS = args.WORKERS
    INVENTORY = args.INVENTORY
    BROKER = args.BROKER
    LOGLEVEL = args.LOGLEVEL
    SHELL = args.SHELL
    CLIENT = args.CLIENT
    CREATE_ENV = args.CREATE_ENV

    # create NorFab environment
    if CREATE_ENV:
        print(f"Creating NorFab environment '{CREATE_ENV}'")
        # create inventory files
        os.makedirs(CREATE_ENV, exist_ok=True)
        os.makedirs(os.path.join(CREATE_ENV, "nornir"), exist_ok=True)
        with open(os.path.join(CREATE_ENV, "inventory.yaml"), "w") as f:
            f.write(norfab_base_inventory)
        with open(os.path.join(CREATE_ENV, "nornir", "common.yaml"), "w") as f:
            f.write(nornir_service_base_inventory_common)
        with open(os.path.join(CREATE_ENV, "nornir", "nornir-worker-1.yaml"), "w") as f:
            f.write(nornir_service_base_inventory_worker)
        return (
            (f"Done, run 'nfcli' to start NorFab")
            if CREATE_ENV == "."
            else (f"Done, 'cd {CREATE_ENV}' and run 'nfcli' to start NorFab")
        )

    # start broker only
    if BROKER:
        nf = NorFab(inventory=INVENTORY, log_level=LOGLEVEL)
        nf.start(start_broker=True, workers=False)
        nf.run()
    # start workers only
    elif WORKERS:
        nf = NorFab(inventory=INVENTORY, log_level=LOGLEVEL)
        nf.start(start_broker=False, workers=True)
        nf.run()
    # start interactive client shell only
    elif CLIENT:
        start_picle_shell(
            inventory=INVENTORY,
            workers=False,
            start_broker=False,
            log_level=LOGLEVEL,
        )
    # default, start everything locally - interactive shell, broker and all workers
    elif SHELL:
        start_picle_shell(
            inventory=INVENTORY,
            workers=True,
            start_broker=True,
            log_level=LOGLEVEL,
        )
