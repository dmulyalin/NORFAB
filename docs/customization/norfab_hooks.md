## NORFAB Hooks

Hooks is a set of functions to run during NorFab execution lifespan.

NorFab supports definition of hooks inside `inventory.yaml` file within `hooks` section.

Hooks defined as a dictionary keyed by attachpoint name and value being a list of hook function definitions with these keys:

- `function` - Python import path for hook function import
- `args` - optional list of function positional arguments
- `kwargs` - optional dictionary of function key-word arguments
- any other keys - will be ignored by NorFab but will loaded into inventory

Supported attach points:

- `startup` - list of functions to run right after NorFab nfapi fully initialized. Startup hook function must accept `norfab` object as a single argument.
- `exit` - list of functions to run right before NorFab nfapi initiates exit sequence. Exit hook function must accept `norfab` object as a single argument.
- `nornir-startup` - list of functions to run right after Nornir worker fully initialized. Startup hook function must accept `worker` object as a single argument.
- `nornir-exit` - list of functions to run right before Nornir worker initiates exit sequence. Exit hook function must accept `worker` object as a single argument.

Sample hooks definition:

``` yaml title="inventory.yaml"
hooks:
  startup:
    - function: "hooks.functions:do_on_startup"
      args: []
      kwargs: {}
      description: "Function to run on startup"
  exit:
    - function: "hooks.functions:do_on_exit"
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

Function import path is a dot separated path used to import module file that contains hook functions, where individual function name is a last item in dot separated path definition. For example `hooks.functions:do_on_startup` path is equivalent of running Python import `from hooks.functions import do_on_startup`.
