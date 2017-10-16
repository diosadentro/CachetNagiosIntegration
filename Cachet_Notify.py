#!/usr/bin/env python

import argparse
import requests
import sys
from enum import Enum
import re
import json

# Start of the prefix. This script uses app servers to support multiple servers "locking" the incidient, therefore this is the start of the prefix
Prefix = "[Auto Generated]"

# The url of the Cachet API
Url = "https://ENTER YOUR CACHET HOSTNAME HERE/api/v1"

# Your Cachet API Token
ApiToken = "ENTER YOUR API TOKEN HERE"

# If set to true, the script will notify cachet subscribers about incidents
NotifySubscribers = True

# If set to true the incident will be visible in Cachet
IncidentVisible = True

# If set to true, soft states from Nagios will also generate alerts
NotifyOnSoftState = False

# Enum to hold the different Incident Types
class IncidentStatus(Enum):
    CACHET_STATUS_INVESTIGATING = 1
    CACHET_STATUS_IDENTIFIED = 2
    CACHET_STATUS_WATCHING = 3
    CACHET_STATUS_FIXED = 4

# Enum to hold the different component status types
class ComponentStatus(Enum):
    CACHET_COMPONENT_STATUS_OPERATIONAL = 1
    CACHET_COMPONENT_STATUS_PERFORMANCE_ISSUES = 2
    CACHET_COMPONENT_STATUS_PARTIAL_OUTAGE = 3
    CACHET_COMPONENT_STATUS_MAJOR_OUTAGE = 4

class ServerStatus(Enum):
    WARNING = 1
    CRITICAL = 2
    OK = 3

# Recursively gets a component by name. If the component isn't found and there are more than 1 page, 
# This will automatically call the new page url and check it's contents. Else return none
def GetComponentByName(componentName, url):

    # Add the header value
    headers = {'X-Cachet-Token': ApiToken, 'Content-Type': "application/json"}

    # Get the component
    r = requests.get(url = url, verify=False, headers=headers)

    # Get the response as json
    response = r.json()

    # Loop through and get the component
    for component in response["data"]:

        #If we found the component, return it
        if component["name"] == componentName:
            return component

    # If we didn't find the component then look to see if there are additional pages, if so recursively loop through them
    if response["meta"]["pagination"]["total_pages"] > 1:
        return GetComponentByName(componentName, response["meta"]["pagination"]["links"]["next_page"])

    # Else the component must not exist, return none
    return None

# Gets an incident by component Id. If the incident isn't found, this will check if multiple pages exist and recursively call the next page to look up the incident. Returning none if nothing is found
def GetIncident(componentId, url):

    # Add the headers
    headers = {'X-Cachet-Token': ApiToken, 'Content-Type': "application/json"}

    # Get the incident
    r = requests.get(url = url, verify=False, headers=headers)

    # Get the response as json
    response = r.json()

    # Loop through and find the incident
    for incident in response["data"]:

        # If we found the incident, return it
        if incident["component_id"] == componentId and incident["human_status"] != "Fixed" and incident["deleted_at"] == None:
            return incident

    # If we didn't find the incident, look to see if there are multiple incidents, if so recursively loop through them
    if response["meta"]["pagination"]["total_pages"] > 1:
        return GetIncident(componentId, response["meta"]["pagination"]["links"]["next_page"])

    # Else no incident exists, return none
    return None

# This will either create an incident if none exists or update the incident and the component status
def CreateIncident(componentId, serviceName, incidentStatus, componentStatus, message):

    # Add the token to the header
    headers = {'X-Cachet-Token': ApiToken, 'Content-Type': "application/json"}

    # Create the json
    json = {"name": Prefix + " " + serviceName + " Incident", "message": message, "status": incidentStatus.value, "visible": IncidentVisible, "component_id": componentId, "component_status": componentStatus.value, "notify": NotifySubscribers}

    # Send the request
    r = requests.post(Url + "/incidents", verify=False, json=json, headers=headers)

    # Return the incident so we can use it later if needed
    return r

def PutIncident(incidentId, message, componentId, componentStatus):

    # Add the token to the header
    headers = {'X-Cachet-Token': ApiToken, 'Content-Type': "application/json"}

    # Create the json
    json = { "message": message, "component_status": componentStatus.value , "component_id": componentId}

    # Send the request
    r = requests.put(Url + "/incidents/" + str(incidentId), verify=False, json=json, headers=headers)

    # Return the incident so we can use it later
    return r

# Updates the created incident
def UpdateIncident(incidentId, incidentStatus, message):
     # Add the token to the header
    headers = {'X-Cachet-Token': ApiToken, 'Content-Type': "application/json"}

    # Create the json
    json = { "message": message, "status": incidentStatus.value}

    # Send the request
    r = requests.post(Url + "/incidents/" + str(incidentId) + "/updates", verify=False, json=json, headers=headers)

    # Return the incident so we can use it later
    return r

# Helper method to create a new incident if required otherwise update the incident and add an update if required
def CreateOrUpdateIncident(incidentId, componentId, serviceName, incidentStatus, currentStatus, componentStatus, incidentMessage, updateMessage):

    # If the incident doesn't exist, create one 
    if incidentId is None:
        CreateIncident(componentId, serviceName, incidentStatus, componentStatus, incidentMessage)

    # Else the incident already exists, update it
    else:
        # we need to do a put request (which will not result in an update) adding the new server to the list
        PutIncident(incidentId, incidentMessage, componentId, componentStatus)

        # If the current status is different than what we're about to update it with, then we can update it
        if currentStatus != componentStatus:
            # Add an update to the incident so we send a notification (this only happens if the status is different that what it's currently set as)
            UpdateIncident(incidentId, incidentStatus, updateMessage)

# This gets the hidden (empty link) from the top level Incident message where the server list is constantly updated as requests are coming in
def GetServerListFromMessage(message):

    # Initialize an empty dictionary
    dic = {}

    # Try to perform the match
    match = re.search('\[\]\(ServerInfo:(.*)\)', message, re.MULTILINE)

    # If a match is found, then pull the message apart and populate the dictionary
    if match:
        # Get the match group (number 2 for the selected area)
        serverString = match.group(1)

        # Split the match on comma to break up the servers
        server = serverString.split(",")

        # Loop through all the servers
        for server in server:
            # Split the server list up by a : separating the server name from the current server status
            serverList = server.split(":")

            # Add the information to the dictionary
            # Hack support if else chain for Python v2
            if int(serverList[1]) == 1:
                dic[serverList[0]] = ServerStatus.WARNING
            elif int(serverList[1]) == 2:
                dic[serverList[0]] = ServerStatus.CRITICAL
            elif int(serverList[1]) == 3:
                dic[serverList[0]] = ServerStatus.OK

        # Return the dictionary if a match exists
        return dic

    # Else return none, this incident doesn't have a server list
    return None

# This sets the server list in the message
def SetServerListInMessage(dic, message):

    # Initialize the string
    serverString = "[](ServerInfo:"

    # Loop through the dictionary and create the string
    #for key, value in dic.iteritems():
    for key, status in dic.items():
        # Add each server to the string
        serverString += key + ":" + str(status.value) + ","

    # Remove the trailing ,
    serverString = serverString[:-1]

    # Close the empty link
    serverString += ")"

    # Search for an existing server list in the message if it exists
    match = re.search('\[\]\(ServerInfo:(.*)\)', message, re.MULTILINE)

    # If the list exists, replace it
    if match:
        message = message.replace(match.group(), serverString)

    # Else add the list to the end of the message
    else:
        message += "\n\n" + serverString

    # Return the message
    return message

# Determines what status to set and sets it
def SetStatus(incident, componentId, hostName, serviceName, state, currentStatus, serverCount):

    # Initialize the server list dictionary
    serverList = {}

    # Initialize the incident as None indicating that no incident exists yet
    incidentId = None

    # If the past incident exists, get the server list and add it to the serverList
    if incident:
        # Update the incidentId since it exists
        incidentId = incident["id"]

        # Get the server list from the message
        serverList = GetServerListFromMessage(incident["message"])

        # If the server list exists
        if serverList:
            # If the hostname's status hasn't changed from the last update just return
            if hostName in serverList and serverList[hostName] == state:
                return

    # Add the current list name and status to the dictionary 
    # (This will either update the current status for this host in the existing dictionary or create a 
    # new entry in either the dictionary from the message or the empty one depending on if it existed or not)
    serverList[hostName] = state

    # Start counting the types
    critical = 0
    warning = 0
    ok = 0
    total = int(serverCount)

    # Loop through dictionary and count
    #for key, value in dic.iteritems():
    for key, value in serverList.items():
        if value == ServerStatus.OK:
            ok += 1
        elif value == ServerStatus.CRITICAL:
            critical += 1
        elif value == ServerStatus.WARNING:
            warning += 1

    # If all the server are indicating critical issues, this is a major outage
    if critical == total:
        componentMessage = "A major outage has been reported. This means all app servers running the " + serviceName + " service are reporting a critical issue. The application team has been notified and are investigating."
        componentStatus = ComponentStatus.CACHET_COMPONENT_STATUS_MAJOR_OUTAGE
        incidentStatus = IncidentStatus.CACHET_STATUS_INVESTIGATING

    # Else if any server is reporting a critical incident, report a partial outage
    elif critical > 0:
        componentMessage = "A partial outage has been reported. This means at least one app server running the " + serviceName + " service is reporting a critical issue. The application team has been notified and are investigating."
        componentStatus = ComponentStatus.CACHET_COMPONENT_STATUS_PARTIAL_OUTAGE
        incidentStatus = IncidentStatus.CACHET_STATUS_INVESTIGATING

    # Else if any server is reporting a warning, report a performance issue
    elif warning > 0:
        componentMessage = "Performance issues have been reported. This means at least one app server running the " + serviceName + " service is reporting a warning. The application team has been notified and are investigating."
        componentStatus = ComponentStatus.CACHET_COMPONENT_STATUS_PERFORMANCE_ISSUES
        incidentStatus = IncidentStatus.CACHET_STATUS_WATCHING

    # If all servers are reporting OK, return operational but set it as identified so a human needs to go in and fully close out the incident with root cause
    elif ok == total:
        componentMessage = "The incident has been reported as fixed. This means all app servers running the " + serviceName + " service are reporting OK. The application team will continue to monitor the service and will be closing this incident with a root cause as soon as possible."
        componentStatus = ComponentStatus.CACHET_COMPONENT_STATUS_OPERATIONAL
        incidentStatus = IncidentStatus.CACHET_STATUS_IDENTIFIED

    # Generate the incident message. Since the first incident isn't captured in the timeline but rather in the incident body, 
    # We'll add the first incident into the message so we can be both generic but have some tracability as to the initial event that caused the incident.
    if incident:
        # Update the existing incident message
        incidentMessage = SetServerListInMessage(serverList, incident["message"])
    else:
        # Generate a new message and add the server information to it
        incidentMessage = SetServerListInMessage(serverList, "The " + serviceName + " service is reporting an issue. \n\nThe Application Team has been notified of the issue and are investigating. Further updates will be added to this incident when available.\n\n Initial Incident: " + componentMessage)

    # Actually perform the action on cachet
    CreateOrUpdateIncident(incidentId, componentId, serviceName, incidentStatus, currentStatus, componentStatus, incidentMessage, componentMessage)

# Main process alert function.
def ProcessAlert(component, serverCount, hostName, serviceName, serviceState, serviceStateType):

    # Get the component
    returnedComponent = GetComponentByName(component, Url + "/components")
    
    # If the component doesn't exist exit. We can't do anything else
    if(returnedComponent == None):
        sys.exit("Could not find component")

    # Get the current status of the component
    # Hack support if else chain for Python v2
    if int(returnedComponent["status"]) == 1:
        status = ComponentStatus.CACHET_COMPONENT_STATUS_OPERATIONAL
    elif int(returnedComponent["status"]) == 2:
        status = ComponentStatus.CACHET_COMPONENT_STATUS_PERFORMANCE_ISSUES
    elif int(returnedComponent["status"]) == 3:
        status = ComponentStatus.CACHET_COMPONENT_STATUS_PARTIAL_OUTAGE
    elif int(returnedComponent["status"]) == 4:
        status = ComponentStatus.CACHET_COMPONENT_STATUS_MAJOR_OUTAGE

    # Get the incident
    incident = GetIncident(returnedComponent["id"], Url + "/incidents")

    # We only care if the type is hard
    if (serviceStateType == "SOFT" and NotifyOnSoftState) or serviceStateType == "HARD":

        # If it's critical, set the state to critical
        if serviceState == "CRITICAL":
            state = ServerStatus.CRITICAL

        # Else if it's warning, set the state to warning
        elif serviceState == "WARNING":
            state = ServerStatus.WARNING

        # Else if it's ok, set the state to ok
        elif serviceState == "OK":
            state = ServerStatus.OK
        
        # Else this is a state we don't understand, exit we can't reliably do anything
        else:
            sys.exit("Could not read server state")
        
        # Now automatically set the status
        SetStatus(incident, returnedComponent["id"], hostName, serviceName, state, status, serverCount)

# Main method for execution
def main():
    # Parse the arguments
    parser = argparse.ArgumentParser(description='Call catchet')

    # The Component Argument specifies what the component name is
    parser.add_argument("-c", "--component", type=str,
                        help = "Catchet Component Name", required=True)

    # The num argument specifies the number of servers that this component is running on. It is used to calculate what status the component should be set to
    parser.add_argument("-num", "--numberServers", type=str,
                        help = "The number of servers the component is running on", required=True)

    # This is the server name that is generating this call. It is used in the server list to keep track of server information
    parser.add_argument("-host", '--hostName', type=str,
                        help='Nagios provided host name should be $HOSTNAME$', required=True)

    # This is the service name that the component represents. It's added to the message for identification information for end users
    parser.add_argument("-name", '--serviceName', type=str,
                        help='Nagios provided service name should be $SERVICEDESC$', required=True)

    # This is the state that nagios is sending us
    parser.add_argument("-state", "--serviceState", type=str,
                        help='Nagios provided service state should be $SERVICESTATE$', required=True)

    # This is the type (Hard or Soft) that we care about
    parser.add_argument('-type', "--serviceStateType", type=str,
                        help="Nagios provided service state type should be $SERVICESTATETYPE$", required=True)

    # Parse the arguments
    args = parser.parse_args()

    # Now process the alert
    ProcessAlert(args.component, args.numberServers, args.hostName, args.serviceName, args.serviceState, args.serviceStateType)

# Call main and start
main()
