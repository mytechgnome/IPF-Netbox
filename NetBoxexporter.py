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
netbox_data = NetBoxexporter.export_netbox_data('dcim/devices'))
print(netbox_data)
This will fetch device hostname, serial number, and site name from NetBox's inventory/devices table.

Arguments:
- endpoint (str): The name of the NetBox API endpoint to query (e.g., 'dcim/devices'). The base URL already includes "https://netbox.example.com/api/".
- netboxlimit (int): The maximum number of records to fetch per request. Default is 100.
Returns:
- list: A JSON formatted list of dictionaries containing the requested data from NetBox.
'''

# region # Define function
def export_netbox_data(endpoint, netboxlimit=netboxlimit):
    url = f'{netboxbaseurl}{endpoint}/?limit={netboxlimit}'
    netboxstart = 0
    r = requests.get(url,headers=netboxheaders,verify=False)
    netbox_data = r.json()['results']
    # Fetch additional pages if necessary
    while r.json()['next']:
        netboxstart += netboxlimit
        print(f'Fetching {endpoint} data {netboxstart} to {netboxstart + netboxlimit} from NetBox...')
        r = requests.get(r.json()['next'],headers=netboxheaders,verify=False)
        netbox_data.extend(r.json()['results'])
    return netbox_data
# endregion

# region # Test function
if __name__ == "__main__":
    print('Testing export_netbox_data function...')
    # The example endpoint should be contain more items than the NetBox limit to test pagination
    netbox_data = export_netbox_data('dcim/devices')
    if len(netbox_data) > netboxlimit:
        print(f"Pagination test passed: Retrieved {len(netbox_data)} records.")
    else:
        print(f"Pagination test incomplete: Retrieved {len(netbox_data)} records, which may not exceed the limit of {netboxlimit}.")
    print('Test complete.')
    printdata = input('Print fetched data? (y/n): ')
    if printdata.lower() == 'y':
        print(netbox_data)
# endregion