*** Settings ***
Library    norfab.clients.NorFabRobot

*** Test Cases ***
Run Tests
	Hosts      FB=*spine*
    nr.test    suite=nf://nornir_test_suites/suite_1.txt
    
# Run More Tests
#     Hosts      FB=*leaf*
#     nr.test    suite=nf://nornir_test_suites/suite_2.txt