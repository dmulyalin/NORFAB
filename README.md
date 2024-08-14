# Network Automations Fabric - NORFAB

NORFAB is a tool for extreme network automations.

Interested? read [documentation](https://dmulyalin.github.io/NORFAB/)

# The IDEA

Most of the software to manage networks falls into one of the two categories: 

- heavyweight platforms running on dedicated infrastructure
- lightweight scripts or tools developed and run locally

NORFAB goal is to be both - software you can run equally well on your laptop or on a 
server, centralized or fully distributed, lightweight and feature reach. Capable of 
doing any use cases without the need to throw gazillions of dollars and man hours at 
it. Always ready to serve the purpose of unlocking engineers superpowers managing
modern network and making their life better.

# Key Features

- Run Anywhere - Windows, MAC, Linux, in a container or VM, on-prem or in cloud, centralized or distributed
- Extend Anything - extendability is in the core of NORFAB
- Integrate with Everything - Python API, REST API, CLI northbound interfaces
- Manage Anything - develop your own services or use built-in to manage your network infrastructure
- Model and data driven - Pydantic models for API, validation and documentation
- Automate Anything - we mean it, sky is the limit on what you can do with NORFAB automating your networks

# Architecture

**TLDR** Service-Oriented Architecture (SOA)

Clients communicate with broker to run the jobs, broker distributes jobs across workers comprising the service.

# History

NORFAB is a successor of Salt-Nornir SaltStack proxy minion aiming 
to surpass its limitations.
