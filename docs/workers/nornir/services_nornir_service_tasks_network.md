---
tags:
  - nornir
---

# Nornir Service Network Task

## NORFAB Nornir Network Shell Reference

NorFab shell supports these command options for Nornir `network` task:

```
nf#man tree nornir.network
root
└── nornir:    Nornir service
    └── network:    Network utility functions - ping, dns etc.
        ├── ping:    Ping devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── add_details:    Add task details to results
        │   ├── run_num_workers:    RetryRunner number of threads for tasks execution
        │   ├── run_num_connectors:    RetryRunner number of threads for device connections
        │   ├── run_connect_retry:    RetryRunner number of connection attempts
        │   ├── run_task_retry:    RetryRunner number of attempts to run task
        │   ├── run_reconnect_on_fail:    RetryRunner perform reconnect to host on task failure
        │   ├── run_connect_check:    RetryRunner test TCP connection before opening actual connection
        │   ├── run_connect_timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
        │   ├── run_creds_retry:    RetryRunner list of connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results to on worker file system
        │   ├── tf_skip_failed:    Save results to file for failed tasks
        │   ├── diff:    File group name to run the diff for
        │   ├── diff_last:    File version number to diff, default is 1 (last)
        │   ├── progress:    Emit execution progress
        │   ├── table:    Table format (brief, terse, extend) or parameters or True
        │   ├── headers:    Table headers
        │   ├── headers_exclude:    Table headers to exclude
        │   ├── sortby:    Table header column to sort by
        │   ├── reverse:    Table reverse the sort by order
        │   ├── FO:    Filter hosts using Filter Object
        │   ├── FB:    Filter hosts by name using Glob Patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts containment of pattern in name
        │   ├── FR:    Filter hosts by name using Regular Expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP Prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Filter hosts excluding them by name
        │   ├── FN:    Negate the match
        │   ├── hosts:    Filter hosts to target
        │   ├── use_host_name:    Ping host's name instead of host's hostname
        │   ├── count:    Number of pings to run
        │   ├── ping_timeout:    Time in seconds before considering each non-arrived reply permanently lost
        │   ├── size:    Size of the entire packet to send
        │   ├── interval:    Interval to wait between pings
        │   ├── payload:    Payload content if size is not set
        │   ├── sweep_start:    If size is not set, initial size in a sweep of sizes
        │   ├── sweep_end:    If size is not set, final size in a sweep of sizes
        │   ├── df:    Don't Fragment flag value for IP Header
        │   ├── match:    Do payload matching between request and reply
        │   └── source:    Source IP address
        └── dns:    Resolve DNS
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'all'
            ├── add_details:    Add task details to results
            ├── run_num_workers:    RetryRunner number of threads for tasks execution
            ├── run_num_connectors:    RetryRunner number of threads for device connections
            ├── run_connect_retry:    RetryRunner number of connection attempts
            ├── run_task_retry:    RetryRunner number of attempts to run task
            ├── run_reconnect_on_fail:    RetryRunner perform reconnect to host on task failure
            ├── run_connect_check:    RetryRunner test TCP connection before opening actual connection
            ├── run_connect_timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
            ├── run_creds_retry:    RetryRunner list of connection credentials and parameters to retry
            ├── tf:    File group name to save task results to on worker file system
            ├── tf_skip_failed:    Save results to file for failed tasks
            ├── diff:    File group name to run the diff for
            ├── diff_last:    File version number to diff, default is 1 (last)
            ├── table:    Table format (brief, terse, extend) or parameters or True
            ├── headers:    Table headers
            ├── headers_exclude:    Table headers to exclude
            ├── sortby:    Table header column to sort by
            ├── reverse:    Table reverse the sort by order
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
            ├── use_host_name:    Ping host's name instead of host's hostname
            ├── servers:    List of DNS servers to use
            ├── dns_timeout:    Time in seconds before considering request lost
            ├── ipv4:    Resolve 'A' record
            └── ipv6:    Resolve 'AAAA' record
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.network