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
    print("Creating NetBox branch for import...")
    from NetBoxloader import load_netbox_config
    import requests
    import time
    timestamp = starttime.strftime("%Y%m%d-%H%M%S")
    branchname = f'IPF_import_{timestamp}'
    netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = load_netbox_config()
    url = f'{netboxbaseurl}plugins/branching/branches/'
    r = requests.post(url,headers=netboxheaders,json={"name": branchname},verify=False)
    if r.status_code == 201:
        schemaID = r.json()['schema_id']
        branchID = r.json()['id']
        print(f'Created NetBox branch: {branchname} with schema ID: {schemaID} and branch ID: {branchID}')
    branch_ready = False
    counter = 0
    taskstart = datetime.now()
    while branch_ready == False:
        r = requests.get(f'{url}{branchID}/',headers=netboxheaders,verify=False)
        if r.status_code == 200 and r.json()['status']['value'] == 'ready':
            branch_ready = True
        else:
            print(f'Waiting for branch to be ready. Current status: {r.json()["status"]["value"]}. Waited {(datetime.now() - taskstart).total_seconds()} seconds.', end="\r")
            counter += 1
            time.sleep(5)
    print(f'Branch is ready. Waited {counter} times over {(datetime.now() - taskstart).total_seconds()} seconds.')

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