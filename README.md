# Network Automations Fabric - NORFAB

NORFAB is a tool for extreme network automations.

# Key Features

- Run Anywhere - locally on Windows, MAC or Linux, in a container, on a VM, in the cloud, centralized or distributed
- Extend Anything - extendability is in the core of NORFAB
- Integrate with Everything - Python API, REST API, CLI northbound interfaces
- Manage Anything - develop your own services or use built-in to manage your network infrastructure
- Model and data driven - Pydantic models for API, validation and documentation
- Automate Anything - we mean it, sky is the limit on what you can do with NORFAB automating your networks

# The IDEA

Most of the software to manage networks falls into one of the two categories: 

- heavyweight platforms running on dedicated infrastructure
- lightweight scripts or tools developed and run locally

NORFAB goal is to be both - software you can run equally well from your laptop or on a 
server, centralized or fully distributed, lightweight and feature reach. Capable of 
doing any use cases without the need to throw gazillions of dollars and man hours at 
it. Always ready to serve the purpose of unlocking engineers superpowers managing
modern network and making their life better.

# Architecture

**TLDR** Clients communicate with worker to run the jobs, broker distributes jobs across workers comprising the service.

![architecture][architecture]

Key components include

- Broker
- Clients
- Workers that form services

*Services* expose functionality consumed by *Clients* via *Broker*.

# Built-in Broker

NORFAB comes with modified version of MDP
([Majordomo Protocol](https://rfc.zeromq.org/spec/7/)) broker.

# Built-in Clients

- Python API Client to provide foundation layer for building other clients
- PICLE Client - interactive command line shell interface targeted to be used by humans
- TODO REST API Client based on FastAPI

# Built-in Services

- Nornir Service to manage Network devices
- File services
- Simple Inventory Service a.k.a. SID

# History

NORFAB is a successor of Salt-Nornir SaltStack proxy minion targeting 
to surpass its limitations.

[architecture]:                docs/ArcOverview_v0.png "NORFAB architecture"