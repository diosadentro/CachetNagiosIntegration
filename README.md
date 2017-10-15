# Cachet Nagios Integration
A Nagios integration for Cachet Status Page that supports multiple app servers

This script supports multiple app servers by using a hidden markdown link at the end of the main incident message. This stores the app servers that have generated an alert for the incident as well as the state of that alert for that app server.

For example, if AppServer1 reported critical and AppServer2 reported critical, `[](ServerInfo:AppServer1:2,AppServer2:2)` will be encoded at the end of the message.

The script uses this encoded information to calculate what the component and incident status should be. 
* If all servers report critical = Major outage
* If any server reports critical = Partial Outage
* If any server reports warning = Performance Issues
* If all servers report ok = Operational

Table of potential values:

| App Server 1 | App Server 2 | Component Status   | Incident Status |
|--------------|--------------|--------------------|-----------------|
| OK           | OK           | Operational        | Identified      |
| CRITICAL     | OK           | Partial Outage     | Investigating   |
| CRITICAL     | WARNING      | Partial Outage     | Investigating   |
| CRITICAL     | CRITICAL     | Major Outage       | Investigating   |
| OK           | WARNING      | Performance Issues | Watching        |
| WARNING      | WARNING      | Performance Issues | Watching        |

The script does not automatically set an incident as Fixed. The reason for this is because I wanted to force a human to put in a conclusion to an incident (such as a root cause).

## Script parameters
1. Url: Be sure to update the Url to include the url to your Cachet Server
2. ApiToken: Be sure to update this to be your Cachet User API Token
3. NotifySubscribers: If set to true, incidents created/updated in cachet will notify subscribers
4. IncidentVisible: If set to true, incidents will be visible on the Cachet site
5. NotifyOnSoftState: If set to true, soft states from Nagios will result in incidents

## Setup Nagios
This script works as an event receive within Nagios. You should setup a nagios command like so:
`cachet_notify.py -c '$_SERVICECOMPONENT$' -num '$_SERVICESERVERCOUNT$' -host '$HOSTNAME$' -name '$SERVICEDESC$' -state '$SERVICESTATE$' -type '$SERVICESTATETYPE$'`

## Parameter Details:
* `-c --component`: This should match the name of the component you setup in Cachet
* `-num --numberServers`: This should be the number of servers that your service is running on
* `-host --hostName`: This should be the server name that the service is running on or some other unique value for your service check.
* `-name --serviceName`: This is the name of the service that will be placed in the Cachet notification message
* `-state --serviceState`: This is the state of the service as reported by Nagios: WARNING, CRITICAL, or OK
* `-type --serviceStateType`: This is the state type of the service as reported by Nagios: HARD or SOFT

## Custom Variables
This also requires you to setup two custom variables on your service:
1. \_COMPONENT This should match the name of the component you setup in Cachet
2. \_SERVERCOUNT This should be set to the number of servers that the service is running on
