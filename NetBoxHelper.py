'''
Module to export information from NetBoxx

Created by: Dan Kelcher
Date: January 20, 2025
'''

# region # Imports and setup
import NetBoxloader 
import requests

# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = NetBoxloader.load_netbox_config()
# endregion
# endregion

'''
Usage Example:
import Netboxloader
netbox_data = NetBoxexporter.get_netbox_data('dcim/devices'))
print(netbox_data)
This will fetch device hostname, serial number, and site name from NetBox's inventory/devices table.

Arguments:
- endpoint (str): The name of the NetBox API endpoint to query (e.g., 'dcim/devices'). The base URL already includes "https://netbox.example.com/api/".
- netboxlimit (int): The maximum number of records to fetch per request. Default is 100.
Returns:
- list: A JSON formatted list of dictionaries containing the requested data from NetBox.
'''

# region # Define functions
# region ## Get data from NetBox
def get_netbox_data(endpoint, netboxlimit=netboxlimit, filters=[]):
    netboxfilter = ''
    for f in filters or []:
        netboxfilter += f'&{f}'
    url = f'{netboxbaseurl}{endpoint}/?limit={netboxlimit}{netboxfilter}'
    netboxstart = 0
    r = requests.get(url,headers=netboxheaders,verify=False)
    netbox_data = r.json()['results']
    # Fetch additional pages if necessary
    while r.json()['next']:
        netboxstart += netboxlimit
        print(f'Fetching {endpoint} data {netboxstart} to {netboxstart + netboxlimit} from NetBox...',end="\r")
        r = requests.get(r.json()['next'],headers=netboxheaders,verify=False)
        netbox_data.extend(r.json()['results'])
    return netbox_data
# region ## Post data to NetBox
def post_netbox_data(endpoint, payload):
    url = f'{netboxbaseurl}{endpoint}/'
    r = requests.post(url, headers=netboxheaders, json=payload, verify=False)
    netbox_data = r.json()['results']
    # Fetch additional pages if necessary
    return netbox_data
# endregion
# region ## Put data to NetBox
def put_netbox_data(endpoint, payload):
    url = f'{netboxbaseurl}{endpoint}/'
    r = requests.put(url, headers=netboxheaders, json=payload, verify=False)
    netbox_data = r.json()['results']
    # Fetch additional pages if necessary
    return netbox_data
# endregion
# region ## Patch data to NetBox
def patch_netbox_data(endpoint, payload):
    url = f'{netboxbaseurl}{endpoint}/'
    r = requests.patch(url, headers=netboxheaders, json=payload, verify=False)
    netbox_data = r.json()['results']
    # Fetch additional pages if necessary
    return netbox_data
# endregion
# endregion

# region # Test function
if __name__ == "__main__":
    print('This is a helper module to export data from NetBox. Please import and use the export_netbox_data function in your script to fetch data from NetBox.')
    print('Testing get_netbox_data function...')
    # The example endpoint should be contain more items than the NetBox limit to test pagination
    netbox_data = get_netbox_data('dcim/devices')
    if len(netbox_data) > netboxlimit:
        print(f"Pagination test passed: Retrieved {len(netbox_data)} records.")
    else:
        print(f"Pagination test incomplete: Retrieved {len(netbox_data)} records, which may not exceed the limit of {netboxlimit}.")
    print('Test complete.')
    printdata = input('Print fetched data? (y/n): ')
    if printdata.lower() == 'y':
        print(netbox_data)
# endregion