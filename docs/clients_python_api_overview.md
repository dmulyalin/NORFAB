# NORFAB Python API
 
NorFab Python API can be used to interact with automations fabric To start working with Python API need to import `NorFab` object and instantiate it.

```
from norfab.core.nfapi import NorFab

nf = NorFab(inventory="./inventory.yaml")
nf.start()
nf.destroy()
```

Refer to [Getting Started](norfab_getting_started.md) section on 
how to construct  `inventory.yaml` file.

All interaction with NorFab happens via client, to create a client need to call `make_client` method:

```
import pprint
from norfab.core.nfapi import NorFab

nf = NorFab(inventory="./inventory.yaml")
nf.start()

client = nf.make_client()

result = nf.client.run_job(
    service="nornir",
    task="cli",
    kwargs={"commands": ["show version", "show clock"]}
)

pprint.pprint(ret)

nf.destroy()
```

Calling `destroy` method will kill all the clients as well.