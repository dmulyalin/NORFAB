from nornir.core.task import Result, Task


def task(task: Task, **kwargs) -> Result:
    task.name = "echo"
    return Result(host=task.host, result=kwargs)
