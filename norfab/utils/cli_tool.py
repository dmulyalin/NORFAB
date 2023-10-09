__version__ = "0.1.0"

import argparse
from norfab.clients.picle_shell_client import start_picle_shell


def cli_tool():
    # form argparser menu:
    description_text = """
    """
    argparser = argparse.ArgumentParser(
        description="Norfab CLI Tool version {}".format(__version__),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_options = argparser.add_argument_group(description=description_text)

    # extract argparser arguments:
    args = argparser.parse_args()

    # start interactive shell
    start_picle_shell()
