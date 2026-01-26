'''
Script to import cable connections from IP Fabric into NetBox.
 - Get connectivity matrix from IP Fabric
 - Match devices in IP Fabric to devices in NetBox
 - Match interfaces in IP Fabric to interfaces in NetBox
 - Match interface type to cable and termination types in NetBox
 - Create cables in NetBox via API

Created by: Dan Kelcher
Date: December 16, 2025

TO-DO:
 - Add logging to file
 - Add summary of successes/failures
'''

# region # Imports and setup
import IPFloader 
import NetBoxloader
import requests
import pandas as pd
import json
import os
from pathlib import Path
import InterfaceNameNormalization as ifn
import IPFexporter
import datetime

starttime = datetime.datetime.now()

# region ## Check for NetBoxCableTypeMappings.json file
try:
    currentdir = Path(__file__).parent # Get directory of current script
except:
    currentdir = os.getcwd() # Fallback to current working directory
if not os.path.isfile(os.path.join(currentdir, 'DataSources', 'NetBoxCableTypeMappings.json')):
    print('NetBoxCableTypeMappings.json file not found in DataSources directory. Please create the file with the necessary cable type mappings.')
    exit()
# endregion
# region ## Create log folder
# region ## Create log directory
starttime_str = starttime.strftime("%Y-%m-%d_%H-%M-%S")
log_dir=os.path.join(currentdir, 'Logs', 'IPF_NetBox_ImportCables', starttime_str)
print(f'Creating log directory at {log_dir}')
os.makedirs(log_dir, exist_ok=True)
# endregion
# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders = NetBoxloader.load_netbox_config()
# endregion
# endregion

# region # Export connectivity matrix from IP Fabric
ipf_connections = IPFexporter.export_ipf_data('interfaces/connectivity-matrix', ['siteName', 'localHost', 'localInt', 'localMedia', 'remoteHost', 'remoteInt', 'remoteMedia'])
print(f'Total cables fetched from IP Fabric: {len(ipf_connections)}')
# endregion

# region # Transform connectivity data from IP Fabric
# region ## Get interfaces from NetBox to build a lookup table
netbox_interfaces = []
netboxLimit = 1000
url = f'{netboxbaseurl}dcim/interfaces/?limit={netboxLimit}'
r = requests.get(url,headers=netboxheaders,verify=False)
loopcounter = 1
print(f'Fetching interfaces {(loopcounter - 1) * netboxLimit} to {loopcounter * netboxLimit} from NetBox...')
for interface in r.json()['results']:
    data = [{
        "device": interface['device']['name'],
        "interface": interface['name'],
        "id": interface['id']
    }]
    netbox_interfaces.extend(data)
if r.json()['next']:
    while r.json()['next']:
        print(f'Fetching {(loopcounter - 1) * netboxLimit} to {loopcounter * netboxLimit} from NetBox...')
        r = requests.get(r.json()['next'],headers=netboxheaders,verify=False)
        for interface in r.json()['results']:
            data = [{
                "device": interface['device']['name'],
                "interface": interface['name'],
                "id": interface['id'],
                "type": interface['type']['value']
            }]
            netbox_interfaces.extend(data)
        loopcounter += 1
print(f'Total interfaces in NetBox: {len(netbox_interfaces)}')
# endregion

# region ## Create Pandas Dataframes
# region ### Open JSON of cable type mappings
cablefile = os.path.join(currentdir, 'DataSources', 'NetBoxCableTypeMappings.json')
cable_map_df = pd.read_json(cablefile)
# endregion
# region ### Create DataFrames from IP Fabric and NetBox data
ipf_connections_df = pd.DataFrame(ipf_connections)
netbox_interfaces_df = pd.DataFrame(netbox_interfaces)
# endregion
# endregion

# region ## Match IP Fabric interfaces to NetBox interfaces and create list of cables to create
# region ### Pre-normalize NetBox interfaces for fast matching
_netbox = netbox_interfaces_df.copy()
_netbox["__norm_device"] = _netbox["device"].astype(str).str.strip().str.lower()
_netbox["__norm_interface"] = _netbox["interface"].astype(str).apply(ifn.normalize_iface)
# endregion
# region ### Pre-normalize Cable Map (match by interface type, case-insensitive)
_cable_map = cable_map_df.copy()
_cable_map["__norm_type"] = _cable_map["Interface"].astype(str).str.strip().str.lower()
# endregion

# region ### Process each connection from IP Fabric
cabledata = []
for row in ipf_connections_df.itertuples(index=False):
    site = getattr(row, "siteName", None)
    l_host = getattr(row, "localHost", None)
    l_int  = getattr(row, "localInt", None)
    r_host = getattr(row, "remoteHost", None)
    r_int  = getattr(row, "remoteInt", None)

    l_host_norm = (str(l_host).strip().lower() if l_host is not None else "")
    l_int_norm  = ifn.normalize_iface(str(l_int)) if l_int is not None else ""

    r_host_norm = (str(r_host).strip().lower() if r_host is not None else "")
    r_int_norm  = ifn.normalize_iface(str(r_int)) if r_int is not None else ""
    
# region #### Local interface lookup
    l_matches = _netbox[
        (_netbox["__norm_device"] == l_host_norm) &
        (_netbox["__norm_interface"] == l_int_norm)
    ]
       
    if l_matches.empty:
        print(f"[Missing] NetBox interface not found for local '{l_host} {l_int}'")
        l_id = None
        l_type = None
        continue  # Skip cable creation if local interface not found
    else:
        l_id = int(l_matches.iloc[0]["id"])
        l_type = str(l_matches.iloc[0]["type"]).strip().lower()
# endregion
# region #### Remote interface lookup
    r_matches = _netbox[
        (_netbox["__norm_device"] == r_host_norm) &
        (_netbox["__norm_interface"] == r_int_norm)
    ]
    if r_matches.empty:
        print(f"[Missing] NetBox interface not found for remote '{r_host} {r_int}'")
        r_id = None
        r_type = None
        continue  # Skip cable creation if remote interface not found
    else:
        r_id = int(r_matches.iloc[0]["id"])
        r_type = str(r_matches.iloc[0]["type"]).strip().lower()
# endregion   
# region #### Type mismatch notice
    type_match = (l_type == r_type) if (l_type and r_type) else None
    if type_match is False:
        print(f"[Mismatch] Local '{l_host} {l_int}' type '{l_type}' != Remote '{r_host} {r_int}' type '{r_type}'")
# endregion
# region #### Determine cable type and color from cable map
    cable = None
    color = None
    if l_type:
        c_matches = _cable_map[_cable_map["__norm_type"] == l_type]
        if c_matches.empty:
            print(f"[Missing] Cable map not found for interface type '{l_type}' (local '{l_host} {l_int}')")
            continue
        else:
            cable = c_matches.iloc[0]["Cable"]
            color = c_matches.iloc[0]["Color"]
# endregion
# region #### Append processed data to cable list
    cabledata.append({
        "siteName": site,
        "localHost": l_host,
        "localInt": l_int,
        "local_netbox_id": l_id,
        "local_type": l_type,
        "remoteHost": r_host,
        "remoteInt": r_int,
        "remote_netbox_id": r_id,
        "remote_type": r_type,
        "type_match": type_match,
        "cable": cable,
        "color": color,
    })
# endregion
# endregion
# endregion
# endregion

# region # Load cables into NetBox
url = f'{netboxbaseurl}dcim/cables/'
for i in cabledata:
    cable_payload = {
        "type": i["cable"],
        "a_terminations": [
            {
                "object_type": "dcim.interface",
                "object_id": int(i["local_netbox_id"])
            }
        ],
        "b_terminations": [
            {
                "object_type": "dcim.interface",
                "object_id": int(i["remote_netbox_id"])
            }
        ],
        "status": "connected",
        "label": f"{i["localHost"]} to {i["remoteHost"]}",
        "description": f"Cable from IP Fabric import - Site: {i["siteName"]}",
        "comments": "Imported from IP Fabric"
        }
    if i['color']:      # Only add color if defined in mapping
        cable_payload['color'] = i['color'].lower()
    cable_payload_json = json.dumps(cable_payload)
    r = requests.post(url,headers=netboxheaders,data=cable_payload_json,verify=False)
    if r.status_code == 201:
        print(f'Created cable between {i["localHost"]} ({i["localInt"]}) and {i["remoteHost"]} ({i["remoteInt"]}) successfully.')
    else:
        print(f'Failed to create cable between {i["localHost"]} and {i["remoteHost"]}. Status code: {r.status_code}')
# endregion
endtime = datetime.datetime.now()
duration = endtime - starttime
print(f'Cable import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')