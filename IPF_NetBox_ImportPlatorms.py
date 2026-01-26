'''
Script to import Platforms from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 16, 2025
'''

# region # Imports and setup
import IPFloader
import IPFexporter
import NetBoxloader
import requests
import datetime

starttime = datetime.datetime.now()

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders = NetBoxloader.load_netbox_config()
# endregion
# endregion

# region # Export Platforms from IP Fabric
ipf_platforms = IPFexporter.export_ipf_data('inventory/summary/families', ['vendor', 'family'])
print(f'Total platforms fetched from IP Fabric: {len(ipf_platforms)}')
# endregion

# region # Transform Platforms Vendor to NetBox Manufacturers
# region ## Get Manufacturers from NetBox to build a lookup table
netbox_manufacturers = []
url = f'{netboxbaseurl}dcim/manufacturers/'
r = requests.get(url,headers=netboxheaders,verify=False)
netbox_manufacturers = r.json()['results']
# endregion
# region ## Build Manufacturer Lookup Dictionary
manufacturer_lookup = {}
for manufacturer in netbox_manufacturers:
    manufacturer_lookup[manufacturer['name']] = manufacturer['id']
# endregion
# endregion

# region # Load Platforms into NetBox
url = f'{netboxbaseurl}dcim/platforms/'
platformSuccessCount = 0
platformFailCount = 0
for platform in ipf_platforms:
    platform_name = platform['family']
    payload = {
        'name': platform_name,
        'slug': platform_name.lower().replace(" ", "-"),
        'manufacturer': manufacturer_lookup.get(platform['vendor'], None),
        'description': f'Imported from IP Fabric'
    }
    r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 201:
        print(f'Successfully imported platform {platform_name} into NetBox.')
        platformSuccessCount += 1
    else:
        platformFailCount += 1
        print(f'Failed to import platform {platform_name} into NetBox. Status Code: {r.status_code}, Response: {r.text}')
# endregion
# region # Summary and logging
endtime = datetime.datetime.now()
duration = endtime - starttime
print(f'Platform import process completed in {duration}.')
print(f'Total platforms processed: {len(ipf_platforms)}')
print(f'Total platforms successfully imported: {platformSuccessCount}')
print(f'Total platforms failed to import: {platformFailCount}')
# endregion