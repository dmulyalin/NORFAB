---
tags:
  - nornir
---

# Nornir Service File Copy Task

## Nornir File Copy Sample Usage

## NORFAB Nornir File Copy Shell Reference

NorFab shell supports these command options for Nornir `file-copy` task:

```
nf#man tree nornir.file-copy
root
└── nornir:    Nornir service
    └── file-copy:    Copy files to/from devices
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
        ├── progress:    Emit execution progress
        ├── table:    Table format (brief, terse, extend) or parameters or True
        ├── headers:    Table headers
        ├── headers_exclude:    Table headers to exclude
        ├── sortby:    Table header column to sort by
        ├── reverse:    Table reverse the sort by order
        ├── FO:    Filter hosts using Filter Object
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
        ├── *source_file:    Source file to copy
        ├── plugin:    Connection plugin parameters
        │   └── netmiko:    Use Netmiko plugin to copy files
        │       ├── dest-file:    Destination file to copy
        │       ├── file-system:    Destination file system
        │       ├── direction:    Direction of file copy, default 'put'
        │       ├── inline-transfer:    Use inline transfer, supported by Cisco IOS
        │       ├── overwrite-file:    Overwrite destination file if it exists, default 'False'
        │       ├── socket-timeout:    Socket timeout in seconds, default '10.0'
        │       └── verify-file:    Verify destination file hash after copy, default 'True'
        └── dry-run:    Do not copy files, just show what would be done
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.file_copy