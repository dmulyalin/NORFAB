---
tags:
  - robot
---

# NorFab Robot Client

NORFAB Robot Client integrates with ROBOT framework to interact 
with NORFAB, allowing to construct workflows and tasks using 
ROBOT domain specific language (DSL).

Robot Framework needs to be installed on the client:

```
pip install norfab[robot]
```

## Supported ROBOT Keywords    

* ``Hosts`` - ``Fx`` filters to target specific hosts, if not 
    provided targets all hosts
* ``Workers`` - names of the workers to target, default is ``all``
* ``nr.test`` - run Nornir Service ``test`` task using 
    provided Nornir tests suite
* ``nr.cli`` - run Nornir Service ``cli`` task using 
    provided show commands and arguments
* ``nr.cfg`` - run Nornir Service ``cfg`` task using 
    provided configuration commands and arguments
    
## Nornir Tests Examples

This ROBOT framework test suite runs two tests using ``nr.test``:

``` yaml title="/path/to/robot_suite.robot"
*** Settings ***
Library    norfab.clients.robot_client.NorFabRobot

*** Test Cases ***
Test NTP
    nr.test    suite=nf://tests/test_ntp_config.yaml
    
Test Software Version
    Hosts      FM=arista_eos
    nr.test    suite=nf://tests/test_version.yaml
```
   
Run test suite from client using ``robot`` command line tool:

```
robot /path/to/robot_suite.robot
```