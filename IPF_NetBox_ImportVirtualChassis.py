'''
Script to import Virtual Chassis from IP Fabric into NetBox.

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
from NetBoxexporter import export_netbox_data
import requests
import datetime

starttime = datetime.datetime.now()

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders, ipflimit = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = NetBoxloader.load_netbox_config()
# endregion
# endregion

# region # Export Virtual Chassis from IP Fabric
ipf_vc = []
# region ## Get stack data from IP Fabric
ipf_stack = IPFexporter.export_ipf_data('platforms/stack', ['master'])
for i in ipf_stack:
    ipf_vc.append(i['master'])
# endregion
# region ## Get VSS data from IP Fabric
ipf_vss = IPFexporter.export_ipf_data('platforms/vss/overview', ['hostname'])
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
url = f'{netboxbaseurl}dcim/virtual-chassis/'
vcSuccessCount = 0
vcFailCount = 0
for vc in vc_add:
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
# endregion
# region ## Flag VCs no longer in IP Fabric
for vc in vc_decom:
    url = f'{netboxbaseurl}dcim/virtual-chassis/{vc}/'
    payload = {
        'description': f'Not present in IP Fabric - {starttime.strftime("%Y-%m-%d %H:%M:%S")}'
    }
    r = requests.patch(url,headers=netboxheaders,json=payload,verify=False)
# region # Summary and logging
endtime = datetime.datetime.now()
duration = endtime - starttime
print(f'Virtual Chassis import process completed. Duration: {duration}')
print(f'Total virtual chassis processed: {len(ipf_vc)}')
print(f'Total virtual chassis to import: {len(vc_add)}')
print(f'Total virtual chassis to decommission: {len(vc_decom)}')
print(f'Total virtual chassis successfully imported: {vcSuccessCount}')
print(f'Total virtual chassis failed to import: {vcFailCount}')
# endregion