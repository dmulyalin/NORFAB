# NorFab Inventory

NorFab comes with Simple Inventory Datastore (SID) hosted by broker, allowing workers to source inventory data from broker.

NorFab inventory separated in sections, each responsible for configuring different aspects of the system.

``` yaml title="inventory.yaml"
broker: # (1)!
  endpoint: "tcp://127.0.0.1:5555" # (2)!

workers: # (3)!
  nornir-*: # (4)!
    - nornir/common.yaml   
  nornir-worker-1: # (5)!
    - nornir/nornir-worker-1.yaml

topology: # (6)!
  broker: True # (7)!
  workers: # (8)!
    - nornir-worker-1

logging: # (9)!
  handlers:
    terminal:
      level: WARNING
    file: 
      level: INFO
```

1.  Broker configuration inventory section
2.  URL to listen for connections on - ``localhost`` port ``5555`` in this case
3.  Workers configuration inventory section
4.  [glob pattern](https://docs.python.org/3/library/fnmatch.html) that will match all workers with ``nornir-`` in the name and map ``common.yaml`` file content for each of them
5.  Worker definition to map inventory file to a specific worker that has name ``nornir-worker-1``
6.  Topology section to define what components to run
7.  Start broker process
8.  List of workers names to start processes for
9.  Logging configuration section

## Broker Inventory Section

Broker inventory **must** have ``broker_endpoint`` parameter defined for workers and clients to identify how connect with broker, and for broker itself to identify where to listen for connections.

``` yaml title="inventory.yaml"
# broker settings
broker:
  endpoint: "tcp://127.0.0.1:5555"
  shared_key: "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO"
```

In addition these parameters are supported

1. `shared_key` - broker encryption shared key may or may not be needed depending of type of the setup you are running, in case if all components - broker, client and workers run on same machine, configuring `shared_key` parameter is options, as `nfapi` is smart enough to auto-configure all workers and client with correct broker shared key. In case if broker and workers with clients are distributed i.e. running in separate containers or on separate machines, `share_key` parameter **must** be configured on all workers and clients to match shared key used by broker.

## Workers Inventory Section

To understand how Simple Inventory Datastore serves workers inventory it is good to know that each worker has a unique name to identify it.

With that in mind, the goal is to map inventory data to individual worker by its name.

For example, let's pretend that worker name is `nornir-worker-1` and we have `common.yaml` and `nornir-worker-1.yaml` files with inventory data  that we need to provide worker with.

To do the mapping between worker name and inventory files we can put this in NorFab inventory (`inventory.yaml`) file:

``` yaml title="inventory.yaml"
workers:
  nornir-*:
    - nornir/common.yaml  
  nornir-worker-1:
    - nornir/nornir-worker-1.yaml
```

Where files structure would look like this:

```
└───rootfolder
    │   inventory.yaml
    │
    └───nornir
            common.yaml
            nornir-worker-1.yaml
```

As you can see, `inventory.yaml` file contains `workers` section with a dictionary keyed by [glob patterns](https://docs.python.org/3/library/fnmatch.html)  to match against workers' names, once worker name matched by the pattern, all items in the list underneaths that pattern being loaded and recursively merged. As such, process continues until all patterns evaluated. Final output of the process is a combined inventory data of all the matched files.

The recursive logic of combining inventory data files is pretty 
straightforward - each next data file merged into the previous data file 
overriding the overlapping values.

The glob pattern matching logic allows be as specific as required and 
map specific files to individual workers or to map single data file to 
multiple workers or map multiple files to multiple workers, all combinations 
supported.

For example, we have a group of two workers with names `netbox-wroker-1.1` and
`netbox-worker-1.2` and we want to map `netbox_common.yaml` to both of the workers,
in that case NorFab inventory (`inventory.yaml`) file could have this content:

``` yaml title="inventory.yaml"
workers:
  netbox-worker-1.*:
    - nornir/netbox_common.yaml  
```

Where files structure would look like this:

```
└───rootfolder
    │   inventory.yaml
    │
    └───netbox
            netbox_common.yaml
```

Both workers will be served with  `netbox_common.yaml` file content as an inventory data.

### Workers Inventory Parameters

Workers inventory can contain these common parameters:

1. `service` - name of the service this worker belongs to

Sample worker base inventory:

``` yaml title=""
service: nornir
```

The rest of the inventory data is worker specific.

## Topology Inventory Section

Topology section of NorFab inventory identifies the components that need to be started on the given node.

## Logging Inventory Section

Logging inventory section allows to configure logging parameters such file retention option, logging to remote hosts, logging levels etc.

## Jinja2 Support

Starting with version 0.3.0 NorFab supports Jinja2 syntax rendering of inventory files, in addition, `env` dictionary variable available to source environment variables:

``` yaml title="inventory.yaml"
logging:
  handlers:
    terminal:
      level: {{ env.get("TERMINAL_LOGGING_LEVEL", "WARNING") }}
    file: 
      level: {{ env.get("FILE_LOGGING_LEVEL", "INFO") }}
```

Above example demonstrates how terminal and file logging level can be sourced from environment using Jinja2 syntax. 

All workers inventory files also passed through Jinja2 renderer with access to `env` dictionary variable:

``` yaml title="nornir/common.yaml"
defaults:
  username: {{ env.get("NORNIR_USERNAME", "nornir") }}
  password: {{ env.get("NORNIR_PASSWORD", "password" ) }}
```

`env` variable passed onto Jinja2 context as a **dictionary** that contains environment variables keys and values supporting all Jinja2 dictionary access operations:

``` yaml title="nornir/common.yaml"
defaults:
  username: {{ env["NORNIR_USERNAME"] }}
  password: {{ env.NORNIR_PASSWORD }}
  port: {{ env.get("NORNIR_PORT", 22) }}
```

## Loading Inventory from Dictionary

By default NorFab supports loading inventory from `inventory.yaml` file together with `workers` section items referring to a list of OS paths to YAML files with workers inventory data. As an alternative it is possible to load full NorFab and its workers inventory from dictionary, this can be useful when working with NorFab Python API directly:

``` python title="Instantiate NorFab out of Dictionary Inventory"
from norfab.core.nfapi import NorFab

data = {
    "broker": {
        "endpoint": "tcp://127.0.0.1:5555",
        "shared_key": "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO",
    },
    "workers": {
        "nornir-*": [
            {
                "service": "nornir",
                "watchdog_interval": 30,
                "runner": {
                    "plugin": "RetryRunner",
                    "options": {
                        "num_workers": 100,
                        "num_connectors": 10,
                    }
                }
            }
        ],
        "nornir-worker-1*": ["nornir/nornir-worker-1.yaml"],
        "nornir-worker-2": [
            "nornir/nornir-worker-2.yaml",
            "nornir/nornir-worker-2-extra.yaml",
        ],
    },
    "topology": {
        "broker": True,
        "workers": [
            "nornir-worker-1",
            "nornir-worker-2",
        ],
    },
}

if __name__ == "__main__":
    nf = NorFab(inventory_data=data, base_dir="./norfab/")
    nf.start()
    client = nf.make_client()
    
    job_result = client.run_job("nornir", "get_nornir_hosts")
    print(job_result)

    nf.destroy()
```

In above example, `data` dictionary contains complete NorFab inventory and passed onto `NorFab` object together with `base_dir` argument to inform NorFab where to search for inventory YAML files, for example `"nornir/nornir-worker-2.yaml"` file will be searched within this path ``"./norfab/nornir/nornir-worker-2.yaml"`` since `./norfab/` is a base directory. Base directory argument is optional and will be automatically set by NorFab to current directory.