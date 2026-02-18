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
from datetime import datetime
from IPFloader import load_ipf_config
from NetBoxloader import load_netbox_config
from IPFexporter import export_ipf_data
import requests
import argparse

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

# region # Export Sites from IP Fabric
ipf_sites = export_ipf_data('inventory/sites', ['siteName'])
# endregion

# region # Transform Sites from IP Fabric
''' No transformation needed for sites '''
# endregion

# region # Load Sites into NetBox
url = f'{netboxbaseurl}dcim/sites/{branchurl}'
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
        siteSuccessCount += 1
    else:
        siteFailCount += 1
        print(f'Failed to import site {site_name} into NetBox. Status Code: {r.status_code}, Response: {r.text}')
endtime = datetime.now()
duration = endtime - starttime
print(f'Site import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
print(f'Total sites processed: {len(ipf_sites)}')
print(f'Total sites successfully imported: {siteSuccessCount}')
print(f'Total sites failed to import: {siteFailCount}')
# endregion