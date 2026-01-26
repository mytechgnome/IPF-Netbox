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
ipf_vc = IPFexporter.export_ipf_data('platforms/stack', ['master', 'membersCount'])
print(f'Total virtual chassis fetched from IP Fabric: {len(ipf_vc)}')
# endregion

# region # Transform VC members from IP Fabric
''' No transformation needed for VC members '''
# endregion

# region # Load Virtual Chassis into NetBox
url = f'{netboxbaseurl}dcim/virtual-chassis/'
vcSuccessCount = 0
vcFailCount = 0
for vc in ipf_vc:
    vc_master = vc['master']
    vc_members_count = vc['membersCount']
    payload = {
        'name': vc_master,
        'slug': vc_master.lower().replace(" ", "-"),
        'description': f'Imported from IP Fabric'
    }
    r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 201:
        print(f'Successfully imported virtual chassis {vc_master} into NetBox.')
        vcSuccessCount += 1
    else:
        vcFailCount += 1
        print(f'Failed to import virtual chassis {vc_master} into NetBox. Status Code: {r.status_code}, Response: {r.text}')
# endregion
# region # Summary and logging
endtime = datetime.datetime.now()
duration = endtime - starttime
print(f'Virtual Chassis import process completed. Duration: {duration}')
print(f'Total virtual chassis processed: {len(ipf_vc)}')
print(f'Total virtual chassis successfully imported: {vcSuccessCount}')
print(f'Total virtual chassis failed to import: {vcFailCount}')
# endregion