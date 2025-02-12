import pprint
import json
import time
from uuid import uuid4


class TestNfApi:
    def test_load_inventory_from_dictionary(self, nfclient_dict_inventory):
        # test that NorFab started and workers are started as well
        reply = nfclient_dict_inventory.get("mmi.service.broker", "show_workers")

        ret = reply["results"]
        pprint.pprint(ret)

        for worker in ret:
            assert len(ret) > 0
            assert all(k in worker for k in ["holdtime", "name", "service", "status"])
