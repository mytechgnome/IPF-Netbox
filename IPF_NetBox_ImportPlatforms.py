'''
Script to import Platforms from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 16, 2025
'''

# region # Imports and setup
from IPFloader import load_ipf_config
from NetBoxloader import load_netbox_config
from IPFexporter import export_ipf_data
import requests
import argparse
from datetime import datetime

starttime = datetime.now()

# region ## Process arguments for branch selection
ap = argparse.ArgumentParser(description="Import Sites from IP Fabric into NetBox")
ap.add_argument("--branch", help="Create a NetBox branch for this import")
args = ap.parse_args()
if args.branch:
    branchurl = f'?_branch={args.branch}'
else:
    branchurl = ''
# endregion

# region ## Load IP Fabric configuration
connected = False
while connected == False:
    try:
        ipfbaseurl, ipftoken, ipfheaders, ipflimit = load_ipf_config()
        connected = True
    except Exception as e:
        print(f"Error loading IP Fabric configuration: {e}")
        print("Please ensure the .env file is configured correctly and try again.")
        input("Press Enter to retry...")

# endregion
# region ## Load NetBox configuration
connected = False
while connected == False:
    try:
        netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = load_netbox_config()
        connected = True
    except Exception as e:
        print(f"Error loading NetBox configuration: {e}")
        print("Please ensure the .env file is configured correctly and try again.")
        input("Press Enter to retry...")
# endregion
# endregion

# region # Export Platforms from IP Fabric
ipf_platforms = export_ipf_data('inventory/summary/families', ['vendor', 'family'])
# endregion

# region # Transform Platforms Vendor to NetBox Manufacturers
# region ## Get Manufacturers from NetBox to build a lookup table
netbox_manufacturers = []
url = f'{netboxbaseurl}dcim/manufacturers/{branchurl}'
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
url = f'{netboxbaseurl}dcim/platforms/{branchurl}'
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
        platformSuccessCount += 1
    else:
        platformFailCount += 1
        print(f'Failed to import platform {platform_name} into NetBox. Status Code: {r.status_code}, Response: {r.text}')
# endregion
# region # Summary and logging
endtime = datetime.now()
duration = endtime - starttime
print(f'Platform import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
print(f'Total platforms processed: {len(ipf_platforms)}')
print(f'Total platforms successfully imported: {platformSuccessCount}')
print(f'Total platforms failed to import: {platformFailCount}')
# endregion