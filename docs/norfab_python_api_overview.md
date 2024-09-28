# NORFAB Python API
 
NorFab python API exists to run the Automations fabric, components
that need to be started defined in `inventory.yaml` file. To start
working with NorFab need to import core object and instantiate it.

```
from norfab.core.nfapi import NorFab

nf = NorFab(inventory="./inventory.yaml")
nf.start()
nf.destroy()
```

Refer to [Getting Started](norfab_getting_started.md) section on 
how to construct  `inventory.yaml` file.

All interaction with NorFab happens via client. On NorFab start an 
instance of local client created automatically and can be used to 
submit the jobs

```
import pprint
from norfab.core.nfapi import NorFab

nf = NorFab(inventory="./inventory.yaml")
nf.start()

result = nf.client.run_job(
    service="nornir",
    task="cli",
    kwargs={"commands": ["show version", "show clock"]}
)

pprint.pprint(ret)

nf.destroy()
```
