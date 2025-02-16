def do_on_startup(norfab):
    print("Startup hook executed")


def do_on_exit(norfab):
    print("Exit hook executed")


def nornir_do_on_startup(norfab):
    print("Nornir startup hook executed")


def nornir_do_on_exit(norfab):
    print("Nornir exit hook executed")
