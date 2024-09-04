*** Settings ***
Library    norfab.clients.robot_client.NorFabRobot

*** Test Cases ***
Run spine config commands
	Hosts     FB=*spine*
    nr.cfg    config=interface loopback 44
	
	
Run leaf config commands
	Hosts     FB=*leaf*
    nr.cfg    interface loopback 44    description configured by robot