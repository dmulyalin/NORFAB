PICLE Shell CLient is designed as a modal operating system. The term modal 
describes a system that has various modes of operation, each having its own 
domain of operation. The CLI uses a hierarchical structure for the modes.

You can access a lower-level mode only from a higher-level mode. For example, 
to access the nornir mode, you must be in the privileged EXEC mode. Each mode 
is used to accomplish particular tasks and has a specific set of commands that 
are available in this mode. For example, to configure a router interface, you 
must be in Nornir configuration mode. All configurations that you enter in 
configuration mode apply only to this function.

It is important to remember that in PICLE Shell, when you enter a command, the 
command is executed. If you enter an incorrect command in a production environment, 
it can negatively affect the it.

Mode         Access Method     Prompt      Exit Method           About This Mode

User EXEC    Any, start of     nf#         Enter end or exit     Use this mode to change settings, perform basic tests, or display system information.
             the session





