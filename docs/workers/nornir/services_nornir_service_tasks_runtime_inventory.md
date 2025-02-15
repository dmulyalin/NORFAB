---
tags:
  - nornir
---

# Nornir Service Runtime Inventory Task

> task api name: `runtime_inventory`

The Nornir Service `runtime_inventory` task designed to work with Nornir inventory content at a runtime. This task uses nornir-salt `InventoryFun` functions to create, read, update or delete hosts.

## Sample Usage

Sample NorFab client call to invoke inventory host creation:

``` python
result = nfclient.run_job(
    "nornir",
    "runtime_inventory",
    workers=["nornir-worker-1"],
    kwargs={
        "action": "create_host",
        "name": "foobar"
    },
)
```

Supported actions are:

- `create_host` or `create` - creates new host or replaces existing host object
- `read_host` or `read` - read host inventory content
- `update_host` or `update` - non recursively update host attributes if host exists in Nornir inventory, do not create host if it does not exist
- `delete_host` or `delete` - deletes host object from Nornir Inventory
- `load` - to simplify calling multiple functions
- `read_inventory` - read inventory content for groups, default and hosts
- `read_host_data` - to return host's data under provided path keys
- `list_hosts` - return a list of inventory's host names
- `list_hosts_platforms` - return a dictionary of hosts' platforms
- `update_defaults` - non recursively update defaults attributes

Sample nfcli command to create host:

```
nf#nornir inventory create-host name foobar
--------------------------------------------- Job Events -----------------------------------------------
15-Feb-2025 11:12:38.908 d42e073070b94d408225af2a880d1d26 job started
15-Feb-2025 11:12:38.939 INFO nornir-worker-5 running nornir.runtime_inventory  - Performing 'create_host' action
15-Feb-2025 11:12:39.162 d42e073070b94d408225af2a880d1d26 job completed in 0.254 seconds

--------------------------------------------- Job Results --------------------------------------------

{
    "nornir-worker-5": {
        "foobar": true
    }
}
nf#
```

## NORFAB Nornir Runtime Inventory Shell Reference

NorFab shell supports these command options for Nornir `runtime_inventory` task:

```
nf#man tree nornir.inventory
root
└── nornir:    Nornir service
    └── inventory:    Work with Nornir inventory
        ├── create-host:    Create new host
        │   ├── timeout:    Job timeout
        │   ├── workers:    Nornir workers to target, default 'any'
        │   ├── *name:    Name of the host
        │   ├── username:    Host connections username
        │   ├── password:    Host connections password
        │   ├── platform:    Host platform recognized by connection plugin
        │   ├── hostname:    Hostname of the host to initiate connection with, IP address or FQDN
        │   ├── port:    TCP port to initiate connection with, default '22'
        │   ├── connection-options:    JSON string with connection options
        │   ├── groups:    List of groups to associate with this host
        │   ├── data:    JSON string with arbitrary host data
        │   └── progress:    Display progress events, default 'True'
        ├── update-host:    Update existing host details
        │   ├── timeout:    Job timeout
        │   ├── workers:    Nornir workers to target, default 'all'
        │   ├── *name:    Name of the host
        │   ├── username:    Host connections username
        │   ├── password:    Host connections password
        │   ├── hostname:    Hostname of the host to initiate connection with, IP address or FQDN
        │   ├── port:    TCP port to initiate connection with, default '22'
        │   ├── connection-options:    JSON string with connection options
        │   ├── groups:    List of groups to associate with this host
        │   ├── groups-action:    Action to perform with groups, default 'append'
        │   ├── data:    JSON string with arbitrary host data
        │   └── progress:    Display progress events, default 'True'
        ├── delete-host:    Delete host from inventory
        │   ├── timeout:    Job timeout
        │   ├── workers:    Nornir workers to target, default 'all'
        │   ├── *name:    Name of the host
        │   └── progress:    Display progress events, default 'True'
        └── read-host-data:    Return host data at given dor-separated key path
            ├── timeout:    Job timeout
            ├── workers:    Nornir workers to target, default 'all'
            ├── FO:    Filter hosts using Filter Object
            ├── FB:    Filter hosts by name using Glob Patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts containment of pattern in name
            ├── FR:    Filter hosts by name using Regular Expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP Prefix
            ├── FL:    Filter hosts by names list
            ├── FM:    Filter hosts by platform
            ├── FX:    Filter hosts excluding them by name
            ├── FN:    Negate the match
            ├── hosts:    Filter hosts to target
            ├── *keys:    Dot separated path within host data, examples: config.interfaces.Lo0
            └── progress:    Display progress events, default 'True'
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.runtime_inventory