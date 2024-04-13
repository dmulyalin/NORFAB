import pprint
import json
import time
from uuid import uuid4

class TestBrokerUtils:

    def test_show_workers(self, nfclient):       
        reply = nfclient.get(b"mmi.service.broker", "show_workers")
        
        ret = json.loads(reply)
        pprint.pprint(ret)
    
        assert all(k in ret[0] for k in ["holdtime", "name", "service", "status"])
        assert ret[0]["name"] == 'nornir-worker-1'
        assert ret[0]["service"] == 'nornir'
        assert ret[0]["status"] == 'alive'
        
    def test_show_broker(self, nfclient):
        reply = nfclient.get(b"mmi.service.broker", "show_broker")
        
        ret = json.loads(reply)
        pprint.pprint(ret)        
        
        for k, v in {
               'address': 'tcp://127.0.0.1:5555',
               'keepalive': 2500,
               'multiplier': 6,
               'services count': 1,
               'status': 'active',
               'workers count': 1
        }.items():
            assert k in ret, "Not all broker params returned"
            assert ret[k] == v, "Some broker params seems wrong"