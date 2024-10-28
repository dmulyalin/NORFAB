import argparse
import os

from norfab.clients.picle_shell_client import start_picle_shell
from norfab.core.nfapi import NorFab
from norfab.utils.loggingutils import setup_logging

log = setup_logging(__name__)


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
        default="WARNING",
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
    # extract argparser arguments:
    args = argparser.parse_args()
    INVENTORY = args.INVENTORY
    WORKERS = args.WORKERS
    INVENTORY = args.INVENTORY
    BROKER = args.BROKER
    LOGLEVEL = args.LOGLEVEL
    SHELL = args.SHELL
    CLIENT = args.CLIENT

    log.setLevel(LOGLEVEL.upper())

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
    # start interactive shell with broker and all workers
    elif SHELL:
        start_picle_shell(
            inventory=INVENTORY,
            workers=True,
            start_broker=True,
            log_level=LOGLEVEL,
        )
