import pytest
import pprint
import json

from norfab.core.inventory import NorFabInventory


class TestInventoryLoad:
    inventory = NorFabInventory(path="./nf_tests_inventory/inventory.yaml")

    def test_broker_inventory(self):
        assert self.inventory.broker, "No broker data"
        assert isinstance(self.inventory.broker, dict), "Broker data not a dictionary"
        assert (
            "endpoint" in self.inventory.broker
        ), "Broker inventory has no 'endpoint' data"

    def test_workers_inventory(self):
        assert self.inventory.workers.data, "No workers data"
        assert isinstance(
            self.inventory.workers.data, dict
        ), "Workers data not a dictionary"
        assert isinstance(
            self.inventory.workers.path, str
        ), "Workers inventory path not a string"


class TestWorkersInventory:
    inventory = NorFabInventory(path="./nf_tests_inventory/inventory.yaml")

    def test_get_item(self):
        nornir_worker_1 = self.inventory.workers["nornir-worker-1"]
        assert isinstance(
            nornir_worker_1, dict
        ), "No dictionary data for nornir-worker-1"

    def test_nornir_worker_1_common_data(self):
        nornir_worker_1 = self.inventory.workers["nornir-worker-1"]
        assert "service" in nornir_worker_1, "No 'service' in inventory"
        assert nornir_worker_1["service"] == "nornir", "'service' is not 'nornir'"
        assert "runner" in nornir_worker_1, "No 'runner' in inventory"
        assert isinstance(nornir_worker_1["runner"], dict), "Runner is not a dictionary"
        assert "plugin" in nornir_worker_1["runner"]

    def test_nornir_worker_1_nornir_inventory(self):
        nornir_worker_1 = self.inventory.workers["nornir-worker-1"]
        assert "hosts" in nornir_worker_1, "No 'hosts' in inventory"
        assert len(nornir_worker_1["hosts"]) > 0, "hosts' inventory is empty"
        assert "groups" in nornir_worker_1, "No 'groups' in inventory"
        assert "defaults" in nornir_worker_1, "No 'defaults' in inventory"

    def test_non_existing_worker_inventory(self):
        with pytest.raises(KeyError):
            nornir_worker_1 = self.inventory.workers["some-worker-111"]

    def test_non_existing_file(self):
        with pytest.raises(FileNotFoundError):
            nornir_worker_3 = self.inventory.workers["nornir-worker-3"]

    def test_list_expansion(self):
        nornir_worker_2 = self.inventory.workers["nornir-worker-2"]

        assert len(nornir_worker_2["hosts"]) == 3

    def test_dict_merge(self):
        nornir_worker_2 = self.inventory.workers["nornir-worker-2"]

        assert "foo" in nornir_worker_2["groups"], "'foo' group missing"
        assert (
            "foobar" in nornir_worker_2["groups"]
        ), "'foobar' group data was not merged"

    def test_value_overwirte(self):
        nornir_worker_2 = self.inventory.workers["nornir-worker-2"]

        assert (
            nornir_worker_2["groups"]["valueoverwrite"]["port"] == 777
        ), "'valueoverwrite.port' not overriden by nested group"
