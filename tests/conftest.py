import pytest
import time
from norfab.core.nfapi import NorFab


@pytest.fixture(scope="class")
def nfclient():
    """
    Fixture to start NorFab and return client object,
    once tests done destroys NorFab
    """
    nf = NorFab(inventory="./nf_tests_inventory/inventory.yaml")
    nf.start()
    time.sleep(3)  # wait for workers to start
    yield nf.client  # return nf client
    nf.destroy()  # teardown
