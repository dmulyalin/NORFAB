# NorFab Inventory

NorFab comes with Simple Inventory Datastore (SID) hosted by broker.

## Broker Inventory

TBD

## Workers Inventory

To understand how Simple Inventory Datastore serves workers inventory 
it is good to know that each worker has a unique name to identify it.

With that in mind, the goal is to map inventory data to individual worker
by its name.

For example, let's pretend that worker name is `nornir-worker-1` and we have
`common.yaml` and `nornir-worker-1.yaml` files with inventory data  that
we need to provide worker with.

To do the mapping between worker name and inventory files we can put this
in NorFab inventory (`inventory.yaml`) file:

``` 
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

As you can see, `inventory.yaml` file contains `workers` section with a
dictionary keyed by glob patterns to match against workers' names, once
worker name matched by the pattern, all items in the list underneaths that
pattern being loaded and recursively merged. As such, process continues 
until all patterns evaluated. Final output of the process is a combined
inventory data of all the matched files.

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

```
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

Both workers will be served with  `netbox_common.yaml` file content as an
inventory data.

### Workers Inventory Parameters

Workers inventory can contain these common parameters:

1. `service` - name of the service this worker belongs to
2. `broker_endpoint` - Broker URL to connect to

Sample worker base inventory:

``` yaml
service: nornir
broker_endpoint: "tcp://127.0.0.1:5555"
```

The rest of the inventory data is worker specific.

## Topology Inventory

Topology section of NorFab inventory identifies the components
that need to be started on the given node.

