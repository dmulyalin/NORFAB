---
tags:
  - nfcli
---

NORFAB comes with interactive command line shell interface invoked using ``nfcli`` to work with the system.

NORFAB CLI designed as a *modal* operating system. The term modal 
describes a system that has various modes of operation, each having its own 
domain of operation. The CLI uses a hierarchical structure for the modes.

You can access a lower-level mode only from a higher-level mode. For example, 
to access the Nornir mode, you must be in the privileged EXEC mode. Each mode 
is used to accomplish particular tasks and has a specific set of commands that 
are available in this mode. For example, to configure a router interface, you 
must be in Nornir configuration mode. All configurations that you enter in 
configuration mode apply only to this function.

NORFAB CLI build using [PICLE package](https://github.com/dmulyalin/picle).

It is important to remember that in PICLE Shell, when you enter a command, the 
command is executed. If you enter an incorrect command in a production environment, 
it can negatively impact it.








