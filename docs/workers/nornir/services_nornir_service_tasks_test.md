---
tags:
  - nornir
---

# Nornir Service Test Task

The Nornir Service Test Task is a critical component of NorFab's Nornir service, designed to facilitate the execution of network tests. This task provides network operations engineers and network automation developers with powerful tools to validate network configurations, ensure compliance, and monitor network performance. By leveraging the capabilities of the Nornir service, users can automate the testing process, identify issues proactively, and maintain a robust network infrastructure.

Nornir service `test` task uses Nornir [TestsProcessor](https://nornir-salt.readthedocs.io/en/latest/Processors/TestsProcessor.html) to run the tests and support test suites definition in YAML format, where test suite YAML files can be stored on and sourced from broker.

## Nornir Test Sample Usage

## Outputting Test Text Tables

NorFab interactive shell allows you to format the results of network tests into text tables. This is particularly useful for presenting test results in a clear and organized manner, making it easier to analyze and interpret the data. The NorFab interactive shell supports the `table` command, which relies on the [tabulate](https://pypi.org/project/tabulate/) module to generate text tables. By outputting test results in table format, you can quickly identify issues and take appropriate action.

## Using Jinja2 Templates

Using Jinja2 Templates enables you to create dynamic test suites based on variables defined in your inventory or passed as job data. This approach allows you to tailor tests to specific devices or scenarios, ensuring that the tests are relevant and accurate. Jinja2 templates provide a powerful way to automate the creation of complex test cases, incorporating conditional logic, loops, and other advanced features to meet your testing requirements.

## Templating Tests with Inline Job Data

Inline Job Data allows you to define test parameters directly within the `job_data` argument, making it easy to customize tests on the fly. This feature is particularly useful for scenarios where test parameters need to be adjusted frequently or based on specific conditions. By templating tests with inline job data, you can ensure that your tests are always up-to-date and aligned with the current network state.

## Using Dry Run

The Using Dry Run feature allows you to generate the content of network test suites without actually performing any actions on the devices. This is useful for validation purposes, as it enables you to verify the correctness of your tests before running them. By using dry run, you can identify potential issues and make necessary adjustments, ensuring that your tests will execute successfully when run for real.

## Running a Subset of Tests

Running a Subset of Tests allows you to execute only a specific set of tests, rather than running the entire test suite. This is useful for targeted testing, such as validating changes in a particular part of the network configuration or focusing on specific devices features. By running a subset of tests, you can save time and resources, while still ensuring that critical aspects of the network are thoroughly tested.

## Returning Only Failed Tests

Returning only failed tests enables you to filter the test results to show only the tests that have failed. This is particularly useful for quickly identifying and addressing issues, as it allows you to focus on the areas that require attention. By returning only failed tests, you can streamline the troubleshooting process and ensure that network problems are resolved efficiently.

## NORFAB Nornir Test Shell Reference

The NORFAB Nornir Test Shell Reference provides a comprehensive set of command options for the Nornir `test` task. These commands allow you to control various aspects of the test execution, such as setting job timeouts, filtering devices, adding task details to results, and configuring retry mechanisms. By leveraging these command options, you can tailor the behavior of the tests to meet your specific network management needs, ensuring that your network remains reliable and performant.

NorFab shell supports these command options for Nornir `test` task:

```
nf#man tree nornir.test
root
└── nornir:    Nornir service
    └── test:    Run network tests
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
        ├── *suite:    Nornir suite nf://path/to/file.py, default 'PydanticUndefined'
        ├── dry_run:    Return produced per-host tests suite content without running tests
        ├── subset:    Filter tests by name
        ├── failed_only:    Return test results for failed tests only
        ├── remove_tasks:    Include/Exclude tested task results
        └── job_data:    Path to YAML file with job data
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.test