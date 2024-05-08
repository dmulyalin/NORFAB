from nornir.core.task import Result, Task


def subtask(task: Task) -> Result:
    task.name = "dummy_subtask"
    return Result(host=task.host, result="dummy substask done")


def task(task: Task) -> Result:
    task.name = "dummy"

    # run subtask
    task.run(task=subtask)

    return Result(host=task.host, result="dummy task done")
