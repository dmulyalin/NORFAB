## NORFAB Hooks

Hooks is a set of functions to run during NorFab execution lifespan.

NorFab supports definition of hooks inside `inventory.yaml` file within `hooks` section.

Each hook defined as a dictionary that can contain these keys:

- `function` - Python import path for hook function
- `attachpoint` - one of the attach points indicating when to run hook function e.g. `startup`
- `args` - optional list of function positional arguments
- `kwargs` - optional dictionary of function key-word arguments

Supported attach points:

- `startup` - list of functions to run right after NorFab nfapi fully initialized. Startup hook function must accept `norfab` object as a single argument.
- `exit` - list of functions to run right before NorFab nfapi initiates exit sequence. Exit hook function must accept `norfab` object as a single argument.
- `nornir-startup` - list of functions to run right after Nornir worker fully initialized. Startup hook function must accept `worker` object as a single argument.
- `nornir-exit` - list of functions to run right before Nornir worker initiates exit sequence. Exit hook function must accept `worker` object as a single argument.

Sample hooks definition:

``` yaml title="inventory.yaml"
hooks:
  - attachpoint: startup
    function: "hooks.functions.do_on_startup"
    args: []
    kwargs: {}
    description: "Function to run on startup"
  - attachpoint: exit
    function: "hooks.functions.do_on_exit"
    args: []
    kwargs: {}
    description: "Function to run on startup"
```

Where hook functions are:

``` python title="hooks/functions.py"
def do_on_startup(norfab):
    print("Startup hook executed")

def do_on_exit(norfab):
    print("Exit hook executed")
```

Function import path is a dot separated path used to import module file that contains hook functions, where individual function name is a last item in dot separated path definition. For example `hooks.functions.do_on_startup` path is equivalent of running Python import `from hooks.functions import do_on_startup`.
