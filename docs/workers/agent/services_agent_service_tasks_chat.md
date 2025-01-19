---
tags:
  - agent
---

# Agent Service Chat Task

## Agent Chat Sample Usage

## NORFAB Agent Chat Shell Reference

NorFab shell supports these command options for Agent `chat` task:

```
nf#man tree agent
root
└── agent:    AI Agent service
    ├── timeout:    Job timeout
    ├── workers:    Filter worker to target, default 'all'
    ├── show:    Show Agent service parameters
    │   ├── inventory:    show agent inventory data
    │   ├── version:    show agent service version report
    │   └── status:    show agent status
    ├── chat:    Chat with the agent
    └── progress:    Emit execution progress, default 'True'
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.agent_worker.AgentWorker.chat