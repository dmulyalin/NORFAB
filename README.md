# Network Automations Fabric - NORFAB

NORFAB is a package and a collection of tools to automate networks.

# Features

- Run anywhere - locally on Windows, MAC or Linux, in a container, on a VM, in the cloud, centralized or distributed
- Extend anything - extendability is the core of the NORFAB
- Integrate with everything - Python API, REST API, CLI northbound interfaces
- Manage anything - develop your own services or use built-in to manage your devices and services
- Model and data driven - Pydantic models for API, validation and documentation

# The IDEA

Most of the software to manage network devices falls into one of the two categories: 

- heavyweight platforms running on dedicated infrastructure
- lightweight scripts or tools developed and run locally

NORFAB goal is to be both - software you can run equally well from your laptop or on a 
server, centralized or fully distributed, lightweight and feature reach. Capable of 
doing any use cases without the need to throw gazillion of dollars and man hours at 
it. Always ready to serve the purpose of making engineers life better and fulfilling 
business requirements.

# Architecture

**TLDR** Micro Services

![architecture][architecture]

Key components include

- Broker
- Clients
- Services

*Services* expose functionality consumed by *Clients* via *Broker*.

# Built-in Broker

NORFAB comes with modified version of MDP
([Majordomo Protocol](https://rfc.zeromq.org/spec/7/)) broker.

# Built-in Clients

- Python API Client to provide foundation layer for building other clients
- PICLE Client for interactive command line shell interface targeted to be used by humans
- REST API Client based on FastAPI

# Built-in Services

- Nornir Service to manage Network devices


[architecture]:                docs/ArcOverview_v0.png "NORFAB architecture"