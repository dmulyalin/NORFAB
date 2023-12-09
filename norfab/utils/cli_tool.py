__version__ = "0.1.0"

import argparse
from norfab.clients.picle_shell_client import start_picle_shell


def cli_tool():
    # form argparser menu:
    description_text = """
    """
    argparser = argparse.ArgumentParser(
        description=(
            f"Norfab PICLE Shell Tool, version {__version__}"
            f"\n\n"
            f"Sample Usage:\n"
            f"  nf -i ./norfab_lab/inventory.yaml -b -w 'nornir-worker-1'"
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
        default=None,
        type=str,
        help="OS Path to YAML file with NORFAB inventory data",
    )
    run_options.add_argument(
        "-w",
        "--workers",
        action="store",
        dest="WORKERS",
        default=None,
        type=str,
        help="Comma separated list of worker names to start processes for",
    )
    run_options.add_argument(
        "-s",
        "--services",
        action="store",
        dest="SERVICES",
        default=None,
        type=str,
        help="Comma separated list of service names to start processes for",
    )
    run_options.add_argument(
        "-b",
        "--broker",
        action="store_true",
        dest="BROKER",
        default=False,
        help="Start NorFab broker process",
    )

    # extract argparser arguments:
    args = argparser.parse_args()
    INVENTORY = args.INVENTORY
    WORKERS = args.WORKERS
    INVENTORY = args.INVENTORY
    BROKER = args.BROKER
    SERVICES = args.SERVICES

    if WORKERS is not None:
        WORKERS = [i.strip() for i in args.WORKERS.split(",")]

    if SERVICES is not None:
        SERVICES = [i.strip() for i in args.SERVICES.split(",")]

    # start interactive shell
    start_picle_shell(
        inventory=INVENTORY, workers=WORKERS, start_broker=BROKER, services=SERVICES
    )
