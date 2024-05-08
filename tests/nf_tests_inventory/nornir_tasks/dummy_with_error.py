from nornir.core.task import Result, Task


def task(task: Task) -> Result:
    task.name = "dummy"
    raise RuntimeError("dummy error")
