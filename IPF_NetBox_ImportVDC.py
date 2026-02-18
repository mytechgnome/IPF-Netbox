'''
Script to import VDCs from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: February 3, 2026
'''

# region # Imports and setup
from IPFloader import load_ipf_config
from NetBoxloader import load_netbox_config
from IPFexporter import export_ipf_data
from NetBoxexporter import export_netbox_data
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

# region # Export VDCs from IP Fabric
ipf_vdcs = export_ipf_data('platforms/devices', ['hostname', 'contextName', 'contextId'])
# endregion

# region # Transform data
# region ## Get existing devices from NetBox to build a lookup table
netbox_devices = []
netbox_devices = export_netbox_data('dcim/devices',filters={'_branch='+schemaID} if schemaID else None)
# endregion
# region ## Build Device Lookup Dictionary
for vdc in ipf_vdcs:
    for device in netbox_devices:
        if device['name'].lower() == vdc['hostname'].lower():
            vdc['device_id'] = device['id']
            vdc['vdc_name'] = vdc['contextName']
            vdc['vdc_id'] = vdc['contextId']
            break
# endregion
# endregion
# region # Load VDCs into NetBox
import_counter = 0
import_success_count = 0
import_fail_count = 0
for vdc in ipf_vdcs:
    url = f'{netboxbaseurl}dcim/virtual-device-contexts/{branchurl}'
    payload = {
        'device': vdc['device_id'],
        'name': vdc['vdc_name'],
        'identifier': vdc['vdc_id'],
        'status': 'active',
        'comments': f'Imported from IP Fabric.'
    }
    r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 201:
        import_success_count += 1
    else:
        import_fail_count += 1
        print(f'Failed to import VDC {vdc["vdc_name"]} on device {vdc["hostname"]} into NetBox. Status Code: {r.status_code}, Response: {r.text}')
    import_counter += 1
    print(f'Import progress: [{"█" * int(import_counter/len(ipf_vdcs)*100):100}]{import_counter/len(ipf_vdcs)*100:.2f}% Complete - ({import_counter}/{len(ipf_vdcs)}) VDCs imported.', end="\r")
print(f'\nVDC import process completed. Total: {len(ipf_vdcs)}, Success: {import_success_count}, Failed: {import_fail_count}')
endtime = datetime.now()
duration = endtime - starttime
print(f'VDC import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
# endregion