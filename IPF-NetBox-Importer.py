'''
Script to run all IP Fabric to NetBox import processes.

Created by: Dan Kelcher
Date: January 29, 2026
'''

import datetime
starttime = datetime.datetime.now()

import subprocess
subprocess.run(["python", "IPF_NetBox_ImportSites.py"])
subprocess.run(["python", "IPF_NetBox_ImportRoles.py"])
subprocess.run(["python", "IPF_NetBox_ImportPlatforms.py"])
subprocess.run(["python", "IPF_NetBox_ImportWireless.py"])
subprocess.run(["python", "IPF_NetBox_ImportVirtualChassis.py"])
subprocess.run(["python", "IPF_NetBox_ImportDeviceTypes.py"])
subprocess.run(["python", "IPF_NetBox_ImportDevices.py"])
subprocess.run(["python", "IPF_NetBox_ImportVDC.py"])
subprocess.run(["python", "IPF_NetBox_ImportModules.py"])
subprocess.run(["python", "IPF_NetBox_ImportCables.py"])
endtime = datetime.datetime.now()
duration = endtime - starttime
print(f'Device import process completed. Duration: {duration}')