from nornir.core.task import Result, Task


def task(task: Task) -> Result:
    task.name = "dummy"
    return Result(host=task.host, result=True)
