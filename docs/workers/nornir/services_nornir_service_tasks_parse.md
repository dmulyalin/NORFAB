---
tags:
  - nornir
---

# Nornir Service Parse Task

## NORFAB Nornir Parse Shell Reference

NorFab shell supports these command options for Nornir `parse` task:

```
nf#man tree nornir.parse
root
└── nornir:    Nornir service
    └── parse:    Parse network devices output
        ├── napalm:    Parse devices output using NAPALM getters
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
        │   └── *getters:    Select NAPALM getters, default 'PydanticUndefined'
        └── ttp:    Parse devices output using TTP templates
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'all'
            ├── add_details:    Add task details to results
            ├── run_num_workers:    RetryRunner number of threads for tasks execution
            ├── run_num_connectors:    RetryRunner number of threads for device connections
            ├── run_connect_retry:    RetryRunner number of connection attempts
            ├── run_task_retry:    RetryRunner number of attempts to run task
            ├── run_connect_check:    RetryRunner test TCP connection before opening actual connection
            ├── run_connect_timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
            ├── run_creds_retry:    RetryRunner list of connection credentials and parameters to retry
            ├── tf:    File group name to save task results to on worker file system
            ├── tf_skip_failed:    Save results to file for failed tasks
            ├── diff:    File group name to run the diff for
            ├── diff_last:    File version number to diff, default is 1 (last)
            ├── progress:    Emit execution progress
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
            ├── *template:    TTP Template to parse commands output, default 'PydanticUndefined'
            └── commands:    Commands to collect form devices
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.parse