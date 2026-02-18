'''
Script to import Device Roles from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 16, 2025
'''

# region # Imports and setup
import json
from IPFloader import load_ipf_config
from NetBoxloader import load_netbox_config
from IPFexporter import export_ipf_data
import requests
from pathlib import Path
import os
import argparse
from datetime import datetime

starttime = datetime.now()

# region ## Process arguments for branch selection
ap = argparse.ArgumentParser(description="Import Sites from IP Fabric into NetBox")
ap.add_argument("--branch", help="Create a NetBox branch for this import")
args = ap.parse_args()
if args.branch:
    branchurl = f'?_branch={args.branch}'
    schemaID = args.branch
else:
    branchurl = ''
    schemaID = None
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

# region ## Check for NetBoxCableTypeMappings.json file
try:
    currentdir = Path(__file__).parent # Get directory of current script
except:
    currentdir = os.getcwd() # Fallback to current working directory
if not os.path.isfile(os.path.join(currentdir, 'DataSources', 'NetBoxDeviceRoleColorMappings.json')):
    print('NetBoxDeviceRoleColorMappings.json file not found in DataSources directory.')
    print('Device color will default to grey.')
    print('If device roles require specific colors, please create the file with the necessary mappings.')

# region # Export Device Types from IP Fabric
ipf_device_types = export_ipf_data('inventory/devices', ['devType'])
# endregion

# region # Transform Device Types into unique list
devType = []
for t in ipf_device_types:
    if t['devType'] not in devType and t['devType'] != '':
        devType.append(t['devType'])
# endregion
print(f'Total unique device types fetched from IP Fabric: {len(devType)}')

# region ## Load NetBoxCableTypeMappings.json file
try:
    with open(os.path.join(currentdir, 'DataSources', 'NetBoxDeviceRoleColorMappings.json')) as f:
        role_color_mappings = json.load(f)
except FileNotFoundError:
    role_color_mappings = {}
# endregion

# region # Load Device Roles into NetBox
url = f'{netboxbaseurl}dcim/device-roles/{branchurl}'
roleSuccessCount = 0
roleFailCount = 0
for role in devType:
    color = next((item['Color'] for item in role_color_mappings if item['role'] == role), '696969') # Default to grey if not found
    role_name = role
    payload = {
        'name': role_name,
        'slug': role_name.lower().replace(" ", "-"),
        'color': color.lower(),
        'description': f'Imported from IP Fabric'
    }
    r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 201:
        roleSuccessCount += 1
    else:
        print(f'Failed to import Device Role {role_name} into NetBox. Status Code: {r.status_code}, Response: {r.text}')
        roleFailCount += 1
# endregion
# region # Summary and logging
endtime = datetime.now()
duration = endtime - starttime
print(f'Device Role import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
print(f'Total Device Roles processed: {len(devType)}')
print(f'Total Device Roles successfully imported: {roleSuccessCount}')
print(f'Total Device Roles failed to import: {roleFailCount}')
# endregion