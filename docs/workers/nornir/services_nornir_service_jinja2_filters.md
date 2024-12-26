---
tags:
  - nornir
---

# Nornir Service Jinja2 Templates Filters

Below listed additional Jinja2 filters that supported by 
Nornir service for templates rendering by all service tasks
such as ``cfg``, ``cli``, ``tests`` etc.

## network_hosts

Returns a list of hosts for given network.

Arguments:

- ``pfxlen`` - boolean, default is True, if False skips prefix length for IP addresses 

Example:

``` jinja2
{{ '192.168.1.0/30' | network_hosts }}

{{ '192.168.2.0/30' | network_hosts(pfxlen=False) }}
```

Returns:

``` python
["192.168.1.1/30", "192.168.1.2/30"]

["192.168.2.1", "192.168.2.2"]
```