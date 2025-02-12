import pytest
import time
import yaml

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
    yield nf.make_client()  # return nf client
    nf.destroy()  # teardown


@pytest.fixture(scope="class")
def nfclient_dict_inventory():
    """
    Fixture to start NorFab and return client object,
    once tests done destroys NorFab
    """
    data = {
        "broker": {
            "endpoint": "tcp://127.0.0.1:5555",
            "shared_key": "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO",
        },
        "topology": {"broker": True, "workers": ["nornir-worker-1", "nornir-worker-2"]},
        "workers": {
            "nornir-*": ["nornir/common.yaml"],
            "nornir-worker-1*": ["nornir/nornir-worker-1.yaml"],
            "nornir-worker-2": [
                "nornir/nornir-worker-2.yaml",
                "nornir/nornir-worker-2-extra.yaml",
            ],
        },
    }

    nf = NorFab(inventory_data=data, base_dir="./nf_tests_inventory/")
    nf.start()
    time.sleep(3)  # wait for workers to start
    yield nf.make_client()  # return nf client
    nf.destroy()  # teardown
