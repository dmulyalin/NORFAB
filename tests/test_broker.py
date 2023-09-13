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


class TestBrokerUtils:

    def test_show_workers(self, nfclient):
        request = json.dumps(
            {"jid": None, "task": "show_workers", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        
        reply = nfclient.send(b"mmi.broker_utils", request)
        
        ret = json.loads(reply[0])
        pprint.pprint(ret)
    
        assert all(k in ret[0] for k in ["identity", "name", "service", "status"])
        assert ret[0]["name"] == 'nornir-worker-1'
        assert ret[0]["service"] == 'nornir'
        assert ret[0]["status"] == 'active'
        
    def test_show_broker(self, nfclient):
        request = json.dumps(
            {"jid": None, "task": "show_broker", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        
        reply = nfclient.send(b"mmi.broker_utils", request)
        
        ret = json.loads(reply[0])
        pprint.pprint(ret)        
        
        for k, v in {
            'address': 'tcp://0.0.0.0:5555',
               'heartbeat interval': 2500,
               'heartbeat liveness': 3,
               'services count': 1,
               'status': 'active',
               'workers count': 1
        }.items():
            assert k in ret, "Not all broker params returned"
            assert ret[k] == v, "Some broker params seems wrong"