---
tags:
  - nornir
---

# Nornir Service Parse Task

> task api name: `parse`

The Nornir Service Parse Task is an integral part of NorFab's Nornir service, designed to facilitate the parsing and extraction of valuable information from network device outputs. This task provides network automation and developer engineers with powerful tools to transform raw command outputs into structured data, enabling more efficient network management and automation workflows.

Key features of the Nornir Service Parse Task include:

- **TextFSM Parsing**: This task allows you to use TextFSM templates to parse command outputs into structured data. TextFSM is a powerful text processing tool that uses templates to define how to extract data from unstructured text. By leveraging TextFSM, you can convert complex command outputs into easily readable and processable data formats, which can then be used for further analysis or automation tasks.

- **TTP Parsing**: The Template Text Parser (TTP) is a robust parsing tool supported by the Nornir Service Parse Task. TTP allows you to define templates for parsing text data, similar to TextFSM, but with additional flexibility and features. Using TTP, you can extract specific information from command outputs and transform it into structured data, making it easier to integrate with other systems and processes.

- **NAPALM Getters**: The Nornir Service Parse Task leverages NAPALM getters to retrieve and parse structured data directly from network devices. NAPALM getters are pre-defined methods that extract specific pieces of information from devices, such as interface details, routing tables, ARP tables, and more.

The Nornir Service Parse Task is essential for network automation and developer engineers who need to process and analyze large volumes of network data. By transforming raw command outputs into structured data, you can automate complex workflows, generate insightful reports, and ensure that your network devices are configured and operating correctly.

This document also includes a reference for the NorFab shell commands related to the Nornir `parse` task, detailing the available options and parameters. These commands provide granular control over the parsing tasks.

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