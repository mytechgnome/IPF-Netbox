'''
Script to import Sites from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 16, 2025

TO-DO:
 - Create log directory if not exists
 - Add logging to file
 - Add duration of import process
'''

# region # Imports and setup
import IPFloader
import IPFexporter
import NetBoxloader
import requests


# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders = NetBoxloader.load_netbox_config()
# endregion
# endregion

# region # Export Sites from IP Fabric
ipf_sites = IPFexporter.export_ipf_data('inventory/sites', ['siteName'])
print(f'Total sites fetched from IP Fabric: {len(ipf_sites)}')
# endregion

# region # Transform Sites from IP Fabric
''' No transformation needed for sites '''
# endregion

# region # Load Sites into NetBox
url = f'{netboxbaseurl}dcim/sites/'
siteSuccessCount = 0
siteFailCount = 0
for site in ipf_sites:
    site_name = site['siteName']
    payload = {
        'name': site_name,
        'slug': site_name.lower().replace(" ", "-"),
        'description': f'Imported from IP Fabric'
    }
    r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 201:
        print(f'Successfully imported site {site_name} into NetBox.')
        siteSuccessCount += 1
    else:
        siteFailCount += 1
        print(f'Failed to import site {site_name} into NetBox. Status Code: {r.status_code}, Response: {r.text}')
print('Site import process completed.')
print(f'Total sites processed: {len(ipf_sites)}')
print(f'Total sites successfully imported: {siteSuccessCount}')
print(f'Total sites failed to import: {siteFailCount}')
# endregion