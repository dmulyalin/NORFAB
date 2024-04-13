import pprint
import json
import time

class TestNornirWorker:

    def test_get_nornir_invenotry(self, nfclient):        
        ret = nfclient.run_job(b"nornir", "get_nornir_inventory")
        pprint.pprint(ret)
    
        for worker_name, data in ret.items():
            assert all(k in data for k in ["hosts", "groups", "defaults"]), f"{worker_name} inventory incomplete"
        
    def test_get_nornir_hosts(self, nfclient):        
        ret = nfclient.run_job(b"nornir", "get_nornir_hosts")
        pprint.pprint(ret)
    
        for worker_name, data in ret.items():
            assert isinstance(data, list), "{worker_name} did not return a list of hosts"
            assert len(data) > 0, "{worker_name} host list is empty"
            

    
        