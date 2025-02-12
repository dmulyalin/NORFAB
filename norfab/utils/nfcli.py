import argparse
import os
import logging

from norfab.core.nfapi import NorFab

log = logging.getLogger(__name__)

try:
    from norfab.clients.picle_shell_client import start_picle_shell
except ImportError as e:
    log.warning(f"Failed to import NorFab Shell, needed libs not found - {e}")

norfab_base_inventory = """
# broker settings
broker:
  endpoint: "tcp://127.0.0.1:5555"
  
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
            f"  nfcli -i ./norfab_lab/inventory.yaml"
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
        "-wl",
        "--workers-list",
        action="store",
        dest="WORKERS_LIST",
        default=None,
        help="Comma-separated list of NorFab worker processes names to start",
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
    run_options.add_argument(
        "--show-broker-shared-key",
        action="store_true",
        dest="SHOW_BROKER_SHARED_KEY",
        default=False,
        help="Show broker shared key",
    )

    # extract argparser arguments:
    args = argparser.parse_args()
    WORKERS = args.WORKERS
    WORKERS_LIST = args.WORKERS_LIST
    INVENTORY = args.INVENTORY
    BROKER = args.BROKER
    LOGLEVEL = args.LOGLEVEL
    SHELL = args.SHELL
    CLIENT = args.CLIENT
    CREATE_ENV = args.CREATE_ENV
    SHOW_BROKER_SHARED_KEY = args.SHOW_BROKER_SHARED_KEY

    if WORKERS_LIST is not None:
        WORKERS_LIST = [i.strip() for i in WORKERS_LIST.split(",") if i.strip()]

    # retrieve broker shared key
    if SHOW_BROKER_SHARED_KEY:
        if not os.path.exists(
            os.path.join("__norfab__", "files", "broker", "public_keys", "broker.key")
        ):
            return (
                f"\nCurrent folder '{os.getcwd()}' does not contain"
                f"__norfab__ environment, \nplease create one and start "
                f" NorFab broker first:\n\n"
                f" - run 'nfcli --create-env my-norfab-env' to create NorFab folders\n"
                f" - run 'cd my-norfab-env' and run 'nfcli -b -l INFO' to start broker\n"
                f" - press CTRL+C to exit and run `nfcli --show-broker-shared-key`\n"
            )
        with open(
            os.path.join("__norfab__", "files", "broker", "public_keys", "broker.key"),
            "r",
        ) as f:
            content = f.read()
            key_value = [
                i.split("public-key = ")[1]
                for i in content.splitlines()
                if "public-key" in i
            ][0]
            return (
                f"\nNorFab broker public key content:\n\n'''\n{content}\n'''\n\n"
                f"Key file location: '{os.path.join('__norfab__', 'files', 'broker', 'public_keys', 'broker.key')}'\n\n"
                f"Copy above key into NorFab clients and workers 'public_keys/broker.key' "
                f"file or \nput public-key value into clients and workers inventory.yaml "
                f"'broker' section \nunder 'shared_key' parameter:\n\n"
                f"broker:\n  shared_key: {key_value}\n"
            )

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
            (f"\nDone, run 'nfcli' to start NorFab\n")
            if CREATE_ENV == "."
            else (f"\nDone, 'cd {CREATE_ENV}' and run 'nfcli' to start NorFab\n")
        )

    # start broker only
    if BROKER:
        nf = NorFab(inventory=INVENTORY, log_level=LOGLEVEL)
        nf.start(start_broker=True, workers=False)
        nf.run()
    # start workers only
    elif WORKERS or WORKERS_LIST:
        nf = NorFab(inventory=INVENTORY, log_level=LOGLEVEL)
        nf.start(start_broker=False, workers=WORKERS_LIST if WORKERS_LIST else True)
        nf.run()
    # start broker and workers
    elif BROKER and (WORKERS or WORKERS_LIST):
        nf = NorFab(inventory=INVENTORY, log_level=LOGLEVEL)
        nf.start(start_broker=True, workers=WORKERS_LIST if WORKERS_LIST else True)
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
            workers=WORKERS_LIST if WORKERS_LIST else True,
            start_broker=True,
            log_level=LOGLEVEL,
        )
