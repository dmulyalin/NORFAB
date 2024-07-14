import argparse
import logging
from norfab.clients.picle_shell_client import start_picle_shell

logging.basicConfig(
    format="%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="WARNING",
)
log = logging.getLogger()


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
        "-w",
        "--workers",
        action="store",
        dest="WORKERS",
        default=None,
        type=str,
        help="Comma separated list of worker names to start processes for",
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
        help="Start NorFab interactive shell",
    )
    # extract argparser arguments:
    args = argparser.parse_args()
    INVENTORY = args.INVENTORY
    WORKERS = args.WORKERS
    INVENTORY = args.INVENTORY
    BROKER = args.BROKER
    LOGLEVEL = args.LOGLEVEL
    SHELL = args.SHELL

    log.setLevel(LOGLEVEL.upper())

    if WORKERS is not None:
        WORKERS = [i.strip() for i in args.WORKERS.split(",")]

    # start interactive shell
    if SHELL:
        try:
            start_picle_shell(
                inventory=INVENTORY,
                workers=WORKERS,
                start_broker=BROKER,
                log_level=LOGLEVEL,
            )
        except KeyboardInterrupt:
            print("\nInterrupted by user...")
