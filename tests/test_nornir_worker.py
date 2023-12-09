import pytest 
import pprint
import json
import time

from norfab.core.nfapi import NorFab

@pytest.fixture(scope="class")
def nfclient():
    """
    Fixture to start NorFab and return client object,
    once tests done destroys NorFab
    """
    nf = NorFab(inventory="./inventory/inventory.yaml")
    client = nf.start()
    time.sleep(3) # wait for workers to start 
    yield client # return nf client  
    nf.destroy() # teardown      


class TestNornirWorker:

    def test_get_nornir_invenotry(self, nfclient):
        request = json.dumps(
            {"jid": None, "task": "get_nornir_inventory", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        
        reply = nfclient.send(b"nornir", request)
        
        ret = json.loads(reply[0])
        pprint.pprint(ret)
    
        for worker_name, data in ret.items():
            assert all(k in data for k in ["hosts", "groups", "defaults"]), f"{worker_name} inventory incomplete"
        
    def test_get_nornir_hosts(self, nfclient):
        request = json.dumps(
            {"jid": None, "task": "get_nornir_hosts", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        
        reply = nfclient.send(b"nornir", request)
        
        ret = json.loads(reply[0])
        pprint.pprint(ret)
    
        for worker_name, data in ret.items():
            assert isinstance(data, list), "{worker_name} did not return a list of hosts"
            assert len(data) > 0, "{worker_name} host list is empty"
            

    
        