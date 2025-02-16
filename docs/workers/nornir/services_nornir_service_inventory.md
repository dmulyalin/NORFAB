# Nornir Worker Inventory

Content of `inventory.yaml` need to be updated to include Nornir worker details:

``` yaml title="inventory.yaml"
broker: 
  endpoint: "tcp://127.0.0.1:5555" 
  shared_key: "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO"

workers:
  fastapi-worker-1: 
    - nornir/nornir-worker-1.yaml

topology: 
  workers: 
    - nornir-worker-1
```

Sample Nornir worker inventory definition

``` yaml title="nornir/nornir-worker-1.yaml"
service: nornir
watchdog_interval: 30
connections_idle_timeout: null

# these parameters mapped to Nornir inventory
# https://nornir.readthedocs.io/en/latest/tutorial/inventory.html
runner:
  plugin: RetryRunner
  options: 
    num_workers: 100
    num_connectors: 10
    connect_retry: 1
    connect_backoff: 1000
    connect_splay: 100
    task_retry: 1
    task_backoff: 1000
    task_splay: 100
    reconnect_on_fail: True
    task_timeout: 600
hosts: {}
groups: {}
defaults: {}
logging: {}
user_defined: {}

# Netbox Service Nornir Inventory integration
netbox:
  retry: 3
  retry_interval: 1
  instance: prod
  interfaces:
    ip_addresses: True
    inventory_items: True
  connections:
    cables: True
  nbdata: True
  circuits: True
  primary_ip: "ipv4"
  devices:
    - fceos4
    - fceos5
    - fceos8
    - ceos1
  filters: 
    - q: fceos3
    - manufacturer: cisco
      platform: cisco_xr
```

**watchdog_interval**

Watchdog run interval in seconds, default is 30

**connections_idle_timeout**

Watchdog connection idle timeout, default is ``None`` - no timeout, connection always kept alive, if set to 0, connections disconnected imminently after task completed, if positive number, connection disconnected after not being used for over ``connections_idle_timeout``

## Netbox Inventory Integration

NorFab Nornir Worker supports tight integration with Netbox to fetch devices data such as device interfaces, ip addresses, circuits, configuration context. Netbox 3.7.x and 4.x.x supported. 

Sample Nornir Worker inventory parameters to fetch devices data from Netbox

``` yaml
netbox:
  retry: 3
  retry_interval: 1
  instance: prod
  interfaces:
    ip_addresses: True
    inventory_items: True
  connections:
    cables: True
  nbdata: True
  circuits: True
  primary_ip: "ipv4"
  devices:
    - fceos4
    - fceos5
    - fceos8
    - ceos1
  filters: 
    - q: fceos3
    - manufacturer: cisco
      platform: cisco_xr
```

**filters**

List of Netbox GraphQL filters to pull devices data. Up to 10 filters supported.

**devices**

List of exact device names to retrieve from Netbox, names used as hosts' names in Nornir inventory.

**retry**

Specifies the number of Netbox data retrieval retry attempts for network operations. This parameter is useful for ensuring that transient network issues do not cause the operation to fail. 

**retry_interval**

Defines the interval (in seconds) between retry attempts. This parameter works in conjunction with the `retry` parameter to control the timing of retry attempts. 

**instance**

Specifies the name of the NetBox instance to be used. This parameter is useful for environments with multiple NetBox instances, allowing to target a specific instance to fetch devices data.

**interfaces**

Indicates whether to include interface data in the results.

Extras:

- **ip_addresses**: When set to `True`, includes IP address information associated with the interfaces in Netbox. 
- **inventory_items**: When set to `True`, includes inventory items associated with the interfaces in Netbox. 

**connections**

Specifies whether to include connection data in the results. 

Extras:

- **cables**: When set to `True`, includes cable information associated with the interface connections. 

**nbdata**

Specifies whether to merge NetBox devices data into Nornir hosts' `data`. This is useful when need to make Netbox device `config_context` available in Nornir hosts' `data` together with other device information such as Netbox `site`, `tags`, `role` etc.

**circuits**

Indicates whether to fetch circuits data from Netbox and map it to hosts data.

**primary_ip**

Specifies what Netbox device IP address to use for Nornir host's `hostname` parameter, supported values are `ipv4`, `ip4`, `ipv6` or `ip6`, uses Netbox device name instead if no primary IP address mapped to the device in Netbox.