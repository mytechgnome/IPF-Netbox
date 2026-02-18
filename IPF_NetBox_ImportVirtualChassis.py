'''
Script to import Virtual Chassis from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 16, 2025

TO-DO:
 - Create log directory if not exists
 - Add logging to file
'''

# region # Imports and setup
from IPFloader import load_ipf_config
from IPFexporter import export_ipf_data
from NetBoxloader import load_netbox_config
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

# region # Export Virtual Chassis from IP Fabric
ipf_vc = []
# region ## Get stack data from IP Fabric
ipf_stack = export_ipf_data('platforms/stack', ['master'])
for i in ipf_stack:
    ipf_vc.append(i['master'])
# endregion
# region ## Get VSS data from IP Fabric
ipf_vss = export_ipf_data('platforms/vss/overview', ['hostname'])
for i in ipf_vss:
    ipf_vc.append(i['hostname'])
print(f'Total virtual chassis fetched from IP Fabric: {len(ipf_vc)}')
# endregion
# endregion

# region # Transform VC members from IP Fabric
# region ## Get existing VC configuration
nb_vc = export_netbox_data('dcim/virtual-chassis')
existing_vc = {}
for i in nb_vc:
    existing_vc[i['name'].lower()] = i['id']
print(f'NetBox current has {len(existing_vc)} virtual chassis')
# endregion
# region ## Remove existing VCs from import list
vc_add = []
for vc in ipf_vc:
    if vc.lower() not in existing_vc.keys():
        vc_add.append(vc)
print(f'Virtual chassis not existing in NetBox (will be imported): {len(vc_add)}')
# endregion
# region ## Identify VC in NetBox that are no longer in IP Fabric
ipf_vc_lower = [i.lower() for i in ipf_vc]
vc_decom = []
for vc in existing_vc.keys():
    if vc not in ipf_vc_lower:
        vc_decom.append(existing_vc[vc])
# endregion

# region # Load Virtual Chassis into NetBox
url = f'{netboxbaseurl}dcim/virtual-chassis/{branchurl}'
importCounter = 0
taskduration = []
vcSuccessCount = 0
vcFailCount = 0
for vc in vc_add:
    taskstart = datetime.now()
    vc_master = vc
    payload = {
        'name': vc_master,
        'slug': vc_master.lower().replace(" ", "-"),
        'description': f'Imported from IP Fabric'
    }
    r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 201:
        vcSuccessCount += 1
    else:
        vcFailCount += 1
    importCounter += 1
    taskend = datetime.now()
    taskduration.append((taskend - taskstart).total_seconds())
    remaining = sum(taskduration) / len(taskduration) * (len(vc_add) - importCounter)
    print(f'Import progress: [{"█" * int(importCounter/len(vc_add)*100):100}] {importCounter/len(vc_add)*100:.2f}% Complete - ({importCounter}/{len(vc_add)}) virtual chassis imported. Remaining: {remaining:.2f}s', end="\r")

# endregion
# region ## Flag VCs no longer in IP Fabric
for vc in vc_decom:
    url = f'{netboxbaseurl}dcim/virtual-chassis/{vc}/{branchurl}'
    payload = {
        'description': f'Not present in IP Fabric - {starttime.strftime("%Y-%m-%d %H:%M:%S")}'
    }
    r = requests.patch(url,headers=netboxheaders,json=payload,verify=False)
# region # Summary and logging
endtime = datetime.now()
duration = endtime - starttime
print(f'\nVirtual Chassis import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
print(f'Total virtual chassis processed: {len(ipf_vc)}')
print(f'Total virtual chassis to import: {len(vc_add)}')
print(f'Total virtual chassis to decommission: {len(vc_decom)}')
print(f'Total virtual chassis successfully imported: {vcSuccessCount}')
print(f'Total virtual chassis failed to import: {vcFailCount}')
# endregion