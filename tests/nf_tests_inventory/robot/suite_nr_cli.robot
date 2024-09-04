*** Settings ***
Library    norfab.clients.robot_client.NorFabRobot

*** Test Cases ***
Run spine commands
	Hosts     FB=*spine*
    nr.cli    commands=show clock
	
	
Run leaf commands
	Hosts     FB=*leaf*
    nr.cli    show clock    show version    
    
 