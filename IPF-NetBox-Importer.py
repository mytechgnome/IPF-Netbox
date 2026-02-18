'''
Script to run all IP Fabric to NetBox import processes.

Created by: Dan Kelcher
Date: January 29, 2026
'''
from datetime import datetime
import subprocess

use_branch = True

starttime = datetime.now()
if use_branch:
    from NetBoxloader import load_netbox_config
    import requests
    timestamp = starttime.strftime("%Y%m%d-%H%M%S")
    branchname = f'IPF_import_{timestamp}'
    netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = load_netbox_config()
    url = f'{netboxbaseurl}plugins/branching/branches/'
    r = requests.post(url,headers=netboxheaders,json={"name": branchname},verify=False)
    if r.status_code == 201:
        schemaID = r.json()['schema_id']
        print(f'Created NetBox branch: {branchname} with schema ID: {schemaID}')


subprocess.run(["python", "IPF_NetBox_ImportSites.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportRoles.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportPlatforms.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportWireless.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportVirtualChassis.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportDeviceTypes.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportDevices.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportVDC.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportModules.py", '--branch', schemaID])
subprocess.run(["python", "IPF_NetBox_ImportCables.py", '--branch', schemaID])
endtime = datetime.now()
duration = endtime - starttime
print(f'Device import process completed. Duration: {duration}')