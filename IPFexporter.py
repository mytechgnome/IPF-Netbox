'''
Module to export information from IP Fabric

Created by: Dan Kelcher
Date: January 20, 2025
'''

# region # Imports and setup
import IPFloader 
import requests

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders, ipflimit = IPFloader.load_ipf_config()
# endregion
# endregion

'''
Usage Example:
import IPFexporter export_ipf_data
ipf_data = IPFexporter.export_ipf_data('inventory/devices', ['hostname', 'sn', 'siteName'])
print(ipf_data)
This will fetch device hostname, serial number, and site name from IP Fabric's inventory/devices table.

Arguments:
- table_name (str): The name of the IP Fabric table to query (e.g., 'inventory/devices').
- columns (list): A list of column names to retrieve from the specified table.
- snapshot (str): The snapshot to query. Default is "$last" for the latest snapshot.
- attribute_filters (dict): Optional dictionary of attribute filters to apply to the query.
- filters (dict): Optional dictionary of filters to apply to the query.
- ipflimit (int): The maximum number of records to fetch per request. Default is 1000.
Returns:
- list: A JSON formatted list of dictionaries containing the requested data from IP Fabric.
'''

# region # Define function
def export_ipf_data(table_name, columns, snapshot="$last", attribute_filters=None, filters=None, ipflimit=ipflimit):
    url = f'{ipfbaseurl}tables/{table_name}'
    ipfstart = 0
    payload = {
      "attributeFilters": attribute_filters if attribute_filters else {},
      "filters": filters if filters else {},
      "snapshot": snapshot,
      "columns": columns,
      "pagination": {
        "start": ipfstart,
        "limit": ipflimit
      },
    }
    r = requests.post(url,headers=ipfheaders,json=payload,verify=False)
    ipf_data = r.json()['data']
    # Fetch additional pages if necessary
    while r.json()['_meta']['count'] > ipfstart + ipflimit:
        ipfstart += ipflimit
        payload['pagination']['start'] = ipfstart
        print(f'Fetching {table_name} data {ipfstart} to {ipfstart + ipflimit} from IP Fabric...')
        r = requests.post(url,headers=ipfheaders,json=payload,verify=False)
        ipf_data.extend(r.json()['data'])
    return ipf_data
# endregion

# region # Test function
if __name__ == "__main__":
    print('Testing export_ipf_data function...')
    ipf_data = export_ipf_data('platforms/stack', ['master', 'membersCount'])
    print('Test complete.')
    print(ipf_data)
# endregion