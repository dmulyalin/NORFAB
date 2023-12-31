import pytest 
import pprint
import json

from norfab.core.nfapi import NorFab

@pytest.fixture(scope="class")
def nfclient():
    """
    Fixture to start NorFab and return client object,
    once tests done destroys NorFab
    """
    nf = NorFab()
    yield nf.start() # return nf client  
    nf.destroy() # teardown    


class TestNornirWorker:

    def test_get_nornir_invenotry(self, nfclient):
        request = json.dumps(
            {"jid": None, "task": "get_nornir_inventory", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        
        reply = nfclient.send(b"nornir", request)
        
        ret = json.loads(reply[0])
        pprint.pprint(ret)
    
        assert all(k in ret for k in ["hosts", "groups", "defaults"])
        
    def test_get_nornir_hosts(self, nfclient):
        request = json.dumps(
            {"jid": None, "task": "get_nornir_hosts", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        
        reply = nfclient.send(b"nornir", request)
        
        ret = json.loads(reply[0])
        pprint.pprint(ret)
    
        assert isinstance(ret, list), "Did not return a list of hosts"
        assert len(ret) > 0, "Host list is empty"