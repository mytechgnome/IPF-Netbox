# region # Import and configure libraries
import requests
import urllib3
import re
import os
import yaml
import json
import pandas as pd
from git import Repo
from pathlib import Path
from difflib import get_close_matches
from dotenv import load_dotenv
# endregion

# region # Define variables
# region ## Set variables from .env file
load_dotenv()
ipfbaseurl = os.getenv('ipfabricbaseurl')
ipftoken = os.getenv('ipfabrictoken')
netboxbaseurl = os.getenv('netboxbaseurl')
netboxtoken = os.getenv('netboxtoken')
reposource = (os.getenv('devicelibraryrepo'))
vendornamesensitivity = float(os.getenv('vendornamesensitivity'))
modellnamesensitivity = float(os.getenv('modellnamesensitivity'))
deviceimagesensitivity = float(os.getenv('deviceimagesensitivity'))
modulenamesensitivity = float(os.getenv('modulenamesensitivity'))
disable_ssl_warning = os.getenv('disable_ssl_warning')
# endregion
# region ## Define paths and headers
homedir = Path.home()
repodir = homedir / 'repo'
ipfheaders = {
    'content-type': 'application/json',
    'accept': 'application/json',
    'x-api-token': ipftoken
    }
netboxheaders = {
    'content-type': 'application/json',
    'accept': 'application/json',
    'Authorization': f'Token {netboxtoken}'
    }
# endregion
# endregion
# region # Disable SSL warnings if specified
if disable_ssl_warning.lower() in ['true', '1', 'yes']:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# endregion

# region # Validate .env settings
# region ## Test IP Fabric connection
url = f'{ipfbaseurl}snapshots/'
try:
    r = requests.get(url,headers=ipfheaders,verify=False)
except:
    print(f'Failed to connect to IP Fabric API.')
    exit()
r = requests.get(url,headers=ipfheaders,verify=False)
if r.status_code != 200:
    print(f'Failed to connect to IP Fabric API. Status code: {r.status_code}')
    exit()
# endregion
# region ## Test NetBox connection
url = f'{netboxbaseurl}dcim/manufacturers/'
try:
    r = requests.get(url=url,headers=netboxheaders,verify=False)
except:
    print(f'Failed to connect to NetBox API.')
    exit()
if r.status_code != 200:
    print(f'Failed to connect to NetBox API. Status code: {r.status_code}')
    exit()
# endregion
# region ## Verify sensitivity settings
for setting in [vendornamesensitivity, modellnamesensitivity, deviceimagesensitivity, modulenamesensitivity]:
    if setting < 0 or setting > 1:
        print('Sensitivity settings must be between 0 and 1. Please update the .env file.')
        exit()
# endregion
# region test repo source
url = reposource
r = requests.get(url,verify=False)
if r.status_code != 200:
    print(f'Failed to access Device Type Library repository. Status code: {r.status_code}')
    exit()
# endregion
# endregion
# region # Initialize counters
duplicate = 0
nomatch = 0
# endregion
# region # Define Functions
def add_device_type_components(yaml_object, objecttype, deviceID, netboxbaseurl, netboxheaders):
    for componenttype in ['interface','front-port','rear-port','console-port','console-server-port','power-port','power-outlet','module-bay','device-bay']:
        componentkey = componenttype + 's'
        if componentkey in yaml_object:
            url = f'{netboxbaseurl}dcim/{componenttype}-templates/'
            componentyaml = yaml_object.get(componentkey, [])
            for component in componentyaml:
                component[f'{objecttype}_type'] = deviceID
                jsondata = json.dumps(component)
                jsondata = json.loads(jsondata)
                r = requests.post(url,headers=netboxheaders,json=jsondata,verify=False)
                if r.status_code == 201:
                    componentname = r.json()['name']
                else:
                    print(url)
                    print(jsondata)
                    print(f'Failed to import {componenttype} into NetBox. Status code: {r.status_code}')
# endregion
# region # DeviceType-Library download
# region ## Create repo directory if it doesn't exist
if not os.path.exists(repodir):
    os.mkdir(repodir)
# endregion
# region ## Clone or pull the latest devicetype-library
if os.path.exists(repodir / '.git'):
    repo = Repo(repodir)
    origin = repo.remotes.origin
    origin.pull()
else:
    print("Cloning DeviceType-Library repository...")
    Repo.clone_from('https://github.com/netbox-community/devicetype-library.git', repodir)
# endregion
# endregion

# region # Import IP Fabric Vendors to NetBox Manufacturers
# region ## Get lists of manufacturers from device types library
manufacturers = os.listdir(repodir / 'device-types')
lowermanufacturernames = [manufacturer.lower() for manufacturer in manufacturers]
# endregion
# region ## Get list of vendors from IP Fabric
vendors = json.loads('{"vendors": []}')
url = f'{ipfbaseurl}tables/inventory/summary/vendors'
payload={
  "attributeFilters": {},
  "filters": {},
  "snapshot": "$last",
  "columns": [
    "vendor"
  ],
  "pagination": {
    "start": 0,
    "limit": 10000
  },
  "reports": "/inventory/devices/vendors"
}
r = requests.post(url,headers=ipfheaders,json=payload,verify=False)
for i in r.json()['data']:
    vendor = i['vendor']
    vendorlibrary = get_close_matches(vendor.lower(),lowermanufacturernames, n=1 , cutoff=vendornamesensitivity)
    idx = lowermanufacturernames.index(vendorlibrary[0])
    vendorlibrary = manufacturers[idx]
    if not vendorlibrary:
        vendorlibrary = vendor
    else:
        vendorlibrary = vendorlibrary
    data = {
            "name": vendorlibrary,
            "slug": vendor
    }
    vendors["vendors"].append(data)
# endregion
# region ## Import vendors into NetBox
url = f'{netboxbaseurl}dcim/manufacturers/'
for i in vendors['vendors']:
    r = requests.post(url,headers=netboxheaders,json=i,verify=False)
# endregion
# endregion

# region # Import IP Fabric Models to NetBox Device Types
# region ## Get list of models from IP Fabric
modelslist = json.loads('{"models": []}')
url = f'{ipfbaseurl}tables/inventory/summary/models'
payload={
  "attributeFilters": {},
  "filters": {},
  "snapshot": "$last",
  "columns": [
    "vendor",
    "family",
    "platform",
    "model"
  ],
  "pagination": {
    "start": 0,
    "limit": 10000
  },
  "reports": "/inventory/devices/models"
}

r = requests.post(url,headers=ipfheaders,json=payload,verify=False)
# endregion
# region ## Import data into NetBox
# region ### Find Manufacture ID from NetBox
for i in r.json()['data']:
    objecttype = 'device'
    vendor = i['vendor']
    url = f'{netboxbaseurl}dcim/manufacturers/?slug={vendor}'
    r = requests.get(url=url,headers=netboxheaders,verify=False)
    manufacturerID = r.json()['results'][0]['id']
    if not r.json()['results']:
        print(f'No manufacturer found in NetBox for vendor {vendor}. Please import vendors first.')
        continue
# endregion
# region ### Find Device Type YAML in Device Type Library and import into NetBox
# region #### Find model in Device Type Library
    vendorlibrary = get_close_matches(vendor.lower(),lowermanufacturernames, n=1 , cutoff=vendornamesensitivity)
    idx = lowermanufacturernames.index(vendorlibrary[0])
    vendorlibrary = manufacturers[idx]
    model = i['model']
    models = os.listdir(repodir / 'device-types' / vendorlibrary)
    basemodelnames = [os.path.splitext(model.lower())[0] for model in models]
    devicetypelibrary = get_close_matches(model.lower(),basemodelnames, n=1 , cutoff=modellnamesensitivity)
    if not devicetypelibrary:
        # Try matching with model and vendor combined
        combinedmodel = f'{vendor}-{model}'
        devicetypelibrary = get_close_matches(combinedmodel.lower(), basemodelnames, n=1 , cutoff=modellnamesensitivity)
        if not devicetypelibrary:
            # Try matching with model and family combined
            family = i['family']
            combinedmodel = f'{family}-{model}'
            devicetypelibrary = get_close_matches(combinedmodel.lower(), basemodelnames, n=1 , cutoff=modellnamesensitivity)
            if not devicetypelibrary:
                # Try matching with model add platform combined
                platform = i['platform']
                combinedmodel = f'{platform}-{model}'
                devicetypelibrary = get_close_matches(combinedmodel.lower() , basemodelnames, n=1 , cutoff=modellnamesensitivity)
                if not devicetypelibrary:
                    nomatch += 1
                    print(f'No match found for model {model} under vendor {vendorlibrary}')
# endregion
# region #### Get Device Type YAML and prepare for import
    else:
        idx = basemodelnames.index(devicetypelibrary[0])
        devicetypelibrary = models[idx]
        print(f'Match found for model {model} under vendor {vendorlibrary}: {devicetypelibrary}')
        url = f'{netboxbaseurl}dcim/device-types/'
        yamlpath = repodir / 'device-types' / vendorlibrary / devicetypelibrary
        with open(yamlpath, 'r') as yaml_in:
            yaml_object = yaml.safe_load(yaml_in)
        yaml_object['manufacturer'] = manufacturerID # Set Manufacturer ID for NetBox
        yaml_object['front_image'] = None
        yaml_object['rear_image'] = None
# region ##### Convert YAML to JSON
        jsondata = json.dumps(yaml_object)
        jsondata = json.loads(jsondata)
# endregion
# endregion
# region #### Import Device Type to NetBox
# region ##### Add Device Type to NetBox
        r = requests.post(url,headers=netboxheaders,json=jsondata,verify=False)
        if r.status_code == 201:
            deviceID = r.json()['id']
            slug = r.json()['slug']
            #print(f'Successfully imported into Netbox{devicetypelibrary} {deviceID} {slug}')
# endregion
# region ##### Add properties to Device Type
# region ###### Assign image to Device Type
            imagedir = repodir / 'elevation-images' / vendorlibrary
            images = os.listdir(imagedir)
            baseimagenames = [os.path.splitext(image)[0] for image in images]
            netboxheadersimage = {'Authorization': f'Token {netboxtoken}'}
            for i in ['front','rear']:
                image = get_close_matches(slug + '.' + i, baseimagenames, n=1 , cutoff=deviceimagesensitivity)
                if image:
                    idx = baseimagenames.index(image[0])
                    image = [images[idx]]
                    imagepath = imagedir / image[0]
                    file = {i + '_image': (image[0], open(imagedir / image[0], 'rb'))}
                    r = requests.patch(f'{netboxbaseurl}dcim/device-types/{deviceID}/',headers=netboxheadersimage,files=file,verify=False)
# endregion
            add_device_type_components(yaml_object, objecttype, deviceID, netboxbaseurl, netboxheaders)
# region #### Log failed imports
        else:
            print(f'Failed to import {devicetypelibrary} into NetBox. Status code: {r.status_code}, Response: {r.text}')
            if r.text.find('already exists') != -1:
                duplicate += 1
# endregion
# endregion
# endregion
# endregion
# region ## Summary of Device Type Import
print(f'Netbox device import complete. {duplicate} duplicates skipped, {nomatch} models not found in Device Type Library.')
if duplicate > nomatch:
    print(f'Consider increasing the model name sensitivity setting to reduce duplicates. Current setting: {modellnamesensitivity}')
else:
    print(f'Consider decreasing the model name sensitivity setting to find more matches. Current setting: {modellnamesensitivity}')
# endregion
# endregion

# region # Import IP Fabric Modules to NetBox
# region ## Get list of modules from IP Fabric
url = f'{ipfbaseurl}tables/inventory/pn'
payload = {
  "attributeFilters": {},
  "filters": {},
  "snapshot": "$last",
  "columns": [
    "pid",
    "vendor"
  ],
  "pagination": {
    "start": 0,
    "limit": 10000
  },
  "reports": "/inventory/part-numbers"
}
r = requests.post(url,headers=ipfheaders,json=payload,verify=False)
# endregion
# region ## Process module data
objecttype = 'module'
modulesdf = r.json()['data']
df = pd.DataFrame(modulesdf)
df['data'] = df['pid'].apply(lambda v: v.get('data') if isinstance(v, dict) else v)
df = df[['vendor', 'data']].dropna()
modules = {"modules": {}}
for vendor, group in df.groupby('vendor'):
    modules["modules"][vendor] = {datum for datum in group['data'].unique()}
# endregion
# region ### Get module profiles from NetBox
url = f'{netboxbaseurl}dcim/module-type-profiles/'
r = requests.get(url=url,headers=netboxheaders,verify=False)
for profile in r.json()['results']:
    if profile['name'] == 'Fan':
        profilefanID = profile['id']
    elif profile['name'] == 'Power supply':
        profilepowersupplyID = profile['id']
    elif profile['name'] == 'Expansion card':
        profileexpansioncardID = profile['id']
# endregion
# region ## Prepare module data for import
for i in modules['modules']:
    vendor = i
    lowermanufacturernames = [manufacturer.lower() for manufacturer in manufacturers]
    vendorlibrary = get_close_matches(vendor.lower(),lowermanufacturernames, n=1 , cutoff=vendornamesensitivity)
    idx = lowermanufacturernames.index(vendorlibrary[0])
    vendorlibrary = manufacturers[idx]
    if not vendorlibrary:
        vendorlibrary = vendor
    if not os.path.exists(repodir / 'module-types' / vendorlibrary):
        print(f'No module types found for vendor {vendorlibrary}')
        continue
    moduleslist = os.listdir(repodir / 'module-types' / vendorlibrary)
    basemodulenames = [os.path.splitext(module.lower())[0] for module in moduleslist]
# region ### Find Manufacture ID from NetBox
    url = f'{netboxbaseurl}dcim/manufacturers/?slug={vendor}'
    r = requests.get(url=url,headers=netboxheaders,verify=False)
    manufacturerID = r.json()['results'][0]['id']
# endregion
# region ### Find Module Type YAML in Device Type Library and prepare for import
    for module in modules['modules'][i]:
        moduletypelibrary = get_close_matches(module.lower(),basemodulenames, n=1 , cutoff=modulenamesensitivity)
        if moduletypelibrary:
            idx = basemodulenames.index(moduletypelibrary[0])
            moduletypelibrary = moduleslist[idx]
            print(f'Match found for module {module} under vendor {vendorlibrary}: {moduletypelibrary}')
            yamlpath = repodir / 'module-types' / vendorlibrary / moduletypelibrary
            with open(yamlpath, 'r') as yaml_in:
                yaml_object = yaml.safe_load(yaml_in)
            yaml_object['manufacturer'] = manufacturerID # Set Manufacturer ID for NetBox
            if 'power-ports' in yaml_object:
                yaml_object['profile'] = profilepowersupplyID
            elif 'interfaces' in yaml_object:
                yaml_object['profile'] = profileexpansioncardID
            elif re.search('fan', str(yaml_object), re.IGNORECASE):
                yaml_object['profile'] = profilefanID
# endregion
# endregion
# region ## Import Module Type to NetBox
            url = f'{netboxbaseurl}dcim/module-types/'
            jsondata = json.dumps(yaml_object)
            jsondata = json.loads(jsondata)
            r = requests.post(url,headers=netboxheaders,json=jsondata,verify=False)
            if r.status_code == 201:
                modulename = r.json()['model']
                deviceID = r.json()['id']
                print(f'Successfully imported into Netbox {moduletypelibrary} {modulename}')
                add_device_type_components(yaml_object, objecttype, deviceID, netboxbaseurl, netboxheaders)
            else:
                print(f'Failed to import {moduletypelibrary} into NetBox. Status code: {r.status_code}, Response: {r.text}')
                print(jsondata)
        else:
            print(f'No match found for module {module} under vendor {vendorlibrary}')
# endregion
# endregion
