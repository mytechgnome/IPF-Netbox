"""
Script to import Device Types and Module Types from IP Fabric into NetBox using the Device Type Library
Requires:
 - GitPython library
 - PyYAML library
 - pandas library
 - python-dotenv library
 - NetBox IP Fabric Plugin installed and configured
 - .env file with connection settings

Netbox Configuration changes required:
 - Modify Device Type Transform Map field maps
   - Add mapping source 'model' target 'part_number' and check coalesce
   - Uncheck coalesce from the model -> slug mapping
 - Modify Manufacturer Transform Map field map
   - Remove vendor -> name mapping

Usage:
 - Adjust sensitivity settings in .env file as needed
 - Run script: python IPF-Netbox-ImportDeviceTypes.py

Created by: Dan Kelcher
Date: December 16, 2025

TO-DO:
- Add stack member device types to import # Done, need to test
  - Pull stack member device types from IPF
  - Identify models not present in the Device Inventory
  - Lookup stack master in Device Inventory to find the vendor
  - Add the stack member device types (model and vendor)to the import process
"""

# region # Import and configure libraries
import requests
import re
import os
import yaml
import json
import pandas as pd
from git import Repo
from pathlib import Path
from difflib import get_close_matches
from difflib import SequenceMatcher
from dotenv import load_dotenv
import IPFloader
import IPFexporter
import NetBoxloader
import datetime

starttime = datetime.datetime.now()

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders, ipflimit = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = NetBoxloader.load_netbox_config()
# endregion

# region # Define variables
# region ## Check for .env
if os.path.isfile('.env'):
    pass
else:
    print('.env file not found. Create a .env file with the required settings.')
    import CreateEnvFile
    CreateEnvFile.create_env_file()
# endregion
# region ## Set variables from .env file
load_dotenv(override=True)
vendornamesensitivity = float(os.getenv('vendornamesensitivity', '0.8'))
modellnamesensitivity = float(os.getenv('modellnamesensitivity', '0.8'))
deviceimagesensitivity = float(os.getenv('deviceimagesensitivity', '0.8'))
modulenamesensitivity = float(os.getenv('modulenamesensitivity', '0.8'))
reposource = os.getenv('reposource', 'https://github.com/netbox-community/devicetype-library.git')

# endregion
# region ## Define paths
try:
    currentdir = Path(__file__).parent # Get directory of current script
except:
    currentdir = os.getcwd() # Fallback to current working directory
repodir = os.path.join(currentdir, 'DataSources', 'DeviceTypeLibraryRepo')
# endregion
# endregion

# region ## Create log directory
starttime_str = starttime.strftime("%Y-%m-%d_%H-%M-%S")
log_dir=os.path.join(currentdir, 'Logs', 'IPF_NetBox_ImportDeviceTypes', starttime_str)
print(f'Creating log directory at {log_dir}')
os.makedirs(log_dir, exist_ok=True)
# endregion

# region # Validate .env settings
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
# region # Initialize counters and lists
duplicate = 0
nomatch = 0

errors_matchdevice = ['vendor,model']
errors_matchmodule = ['vendor,module']
errors_matchvendor = ['vendor']
errors_importcomponents = ['devicde_ID,component_type,API_status_code,API_text,Generated_JSON_data']
errors_importdevice = ['device,API_status_code,API_text']
errors_importmodule = ['vendor,module,API_status_code,API_text']
errors_importvendor = ['vendor,API_status_code,API_text']
mappings_device = ['IPF_Model,Success/Fail,DeviceTypeLibrary_Match,Similarity_Score']
mappings_image = ['NetBox_Slug,Success/Fail,Image_Name,Similarity_Score']
mappings_module = ['IPF_Module,Success/Fail,DeviceTypeLibrary_Match,Similarity_Score']
mappings_vendor = ['IPF_Vendor,Success/Fail,DeviceTypeLibrary_Match,Similarity_Score']

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
                if r.status_code != 201:
                    error_text = f'{deviceID},{componenttype},{r.status_code},{r.text},{jsondata}'
                    errors_importcomponents.append(error_text)
# region # DeviceType-Library download
# region ## Create repo directory if it doesn't exist
if not os.path.exists(repodir):
    os.mkdir(repodir)
# endregion
# region ## Clone or pull the latest devicetype-library
if os.path.exists(os.path.join(repodir, '.git')):
    repo = Repo(repodir)
    origin = repo.remotes.origin
    origin.pull()
else:
    print(f'Cloning DeviceType-Library repository from {reposource}')
    Repo.clone_from(reposource, repodir)
# endregion
# endregion

# region # Import IP Fabric Vendors to NetBox Manufacturers
# region ## Get lists of manufacturers from device types library
manufacturers = os.listdir(os.path.join(repodir, 'device-types'))
lowermanufacturernames = [manufacturer.lower() for manufacturer in manufacturers]
# endregion
# region ## Export list of vendors from IP Fabric
print('Exporting vendors from IP Fabric...')
vendors = json.loads('{"vendors": []}')
ipf_vendors = IPFexporter.export_ipf_data('inventory/pn', ['vendor']) # Collects from PN table to get all vendors, including those only used in modules
# region ### Filter unique vendors
unique_vendors = []
seen_vendors = set()
for vendor_entry in ipf_vendors:
    vendor_name = vendor_entry['vendor']
    if vendor_name not in seen_vendors:
        unique_vendors.append(vendor_entry)
        seen_vendors.add(vendor_name)
ipf_vendors = unique_vendors
# endregion
print(f'Total vendors fetched from IP Fabric: {len(ipf_vendors)}')
# endregion
# region ## Transform vendor data for import
for i in ipf_vendors:
    vendor = i['vendor']
    vendorlibrary = get_close_matches(vendor.lower(),lowermanufacturernames, n=1 , cutoff=vendornamesensitivity)
    score = SequenceMatcher(None, vendor.lower(), vendorlibrary[0]).ratio()
    if score >= vendornamesensitivity:
        vendor_map = f'{vendor},Success,{vendorlibrary[0]},{score:.2f}'
    elif not vendorlibrary:
        vendor_map = f'{vendor},Fail,No Match,'
    else:
        vendor_map = f'{vendor},Fail,{vendorlibrary[0]},{score:.2f}'
    mappings_vendor.append(vendor_map)
    idx = lowermanufacturernames.index(vendorlibrary[0])
    vendorlibrary = manufacturers[idx]
    if not vendorlibrary:
        vendorlibrary = vendor
        error_text = f'{vendor}'
        errors_matchvendor.append(error_text)
    data = {
            "name": vendorlibrary,
            "slug": vendor
    }
    vendors["vendors"].append(data) 
# endregion
# region ## Load vendors into NetBox
netbox_vendors = {}
# region ### Get vendor already in NetBox
url = f'{netboxbaseurl}dcim/manufacturers/'
r = requests.get(url,headers=netboxheaders,verify=False)
for manufacturer in r.json()['results']:
    netbox_vendors[manufacturer['name'].lower()] = manufacturer['id']
# endregion
print('Importing manufacturers into NetBox...')
url = f'{netboxbaseurl}dcim/manufacturers/'
vendorSuccessCount = 0
for i in vendors['vendors']:
    r = requests.post(url,headers=netboxheaders,json=i,verify=False)
    if r.status_code == 201:
        vendorSuccessCount += 1
        netbox_vendors[i['name'].lower()] = r.json()['id']
    else:
        error_text = f"{i['name']},{r.status_code},{r.text}"
        errors_importvendor.append(error_text)
print(f'NetBox manufacturer import complete. {vendorSuccessCount} of {len(ipf_vendors)} manufacturers imported.')
# endregion
# endregion

# region # Import IP Fabric Models to NetBox Device Types
# region ## Export list of models from IP Fabric
# region ### Get list of models from IP Fabric
print('Exporting device types from IP Fabric...')
modelslist = json.loads('{"models": []}')
ipf_models = IPFexporter.export_ipf_data('inventory/summary/models', ['vendor', 'family', 'platform', 'model'])
print(f'Total device types fetched from IP Fabric: {len(ipf_models)}')
# endregion
'''
NOTE: This section is required because IP Fabric does not list stack member devices in the device inventory.
IPF Feature Reequest 357 is open to add this functionality. 
'''
# region ### Get list of stack member models from IP Fabric
ipf_vcmembers = IPFexporter.export_ipf_data('platforms/stack/members', ['master', 'pn'])
print(f'Total stack members fetched from IP Fabric: {len(ipf_vcmembers)}')
# endregion
# region ### Filter unique models
print('Filtering unique device types...')
existing_models = {item['model'] for item in ipf_models}
missing_models = [
    {"master": item["master"], "pn": item["pn"]}
    for item in ipf_vcmembers
    if item["pn"] not in existing_models
    ]
seen = set()
unique_models = []
for item in missing_models:
    if item["pn"] not in seen:
        unique_models.append(item)
        seen.add(item["pn"])
        
# endregion
# region ### Collect data for missing models
ipf_devices = IPFexporter.export_ipf_data('inventory/devices', ['hostname', 'vendor', 'family', 'platform'])
# region #### Build a lookup dictionary for device details
device_lookup = {device['hostname']: device for device in ipf_devices}
# endregion
# region #### Loop through unique stack member models and get vendor, family, platform
for item in unique_models:
    pn = item['pn']
    master = item['master']
    device = device_lookup.get(master, {})
    vendor = device.get('vendor', 'Unknown')
    family = device.get('family', 'Unknown')
    platform = device.get('platform', 'Unknown')
    model_entry = {
        'vendor': vendor,
        'family': family,
        'platform': platform,
        'model': pn
    }
    ipf_models.append(model_entry)
# endregion
print(f'Total unique device types fetched from IP Fabric: {len(ipf_models)}')
# endregion

# endregion
# region ## Transform data prior to loading into NetBox
print(f'Importing device types into NetBox...')
# region ### Lookup NetBox Manufacturer ID
importCounter = 0
taskduration = []
for i in ipf_models:
    taskstart = datetime.datetime.now()
    objecttype = 'device'
    vendor = i['vendor']
    manufacturerID = netbox_vendors.get(vendor.lower(), None)
    if not manufacturerID:
        print(f'No manufacturer found in NetBox for vendor {vendor}. Please import vendors first.')
        continue
# endregion
# region ### Find Device Type YAML in Device Type Library and import into NetBox
# region #### Find model in Device Type Library
    vendorlibrary = get_close_matches(vendor.lower(),lowermanufacturernames, n=1 , cutoff=vendornamesensitivity)
    idx = lowermanufacturernames.index(vendorlibrary[0])
    vendorlibrary = manufacturers[idx]
    model = i['model']
    models = os.listdir(os.path.join(repodir, 'device-types', vendorlibrary))
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
                    error_text = f'{vendorlibrary},{model}'
                    errors_matchdevice.append(error_text)
    if devicetypelibrary:
        score = SequenceMatcher(None, model.lower(), devicetypelibrary[0]).ratio()
        if score >= modellnamesensitivity:
            mapping_device = f'{model},Success,{devicetypelibrary[0]},{score:.2f}'
        elif not devicetypelibrary:
            mapping_device = f'{model},Fail,No Match,'
        else:
            mapping_device = f'{model},Fail,{devicetypelibrary[0]},{score:.2f}'
        mappings_device.append(mapping_device)
# endregion
# region #### Get Device Type YAML and prepare for import
        idx = basemodelnames.index(devicetypelibrary[0])
        devicetypelibrary = models[idx]
        url = f'{netboxbaseurl}dcim/device-types/'
        yamlpath = os.path.join(repodir, 'device-types', vendorlibrary, devicetypelibrary)
        with open(yamlpath, 'r') as yaml_in:
            yaml_object = yaml.safe_load(yaml_in)
        yaml_object['manufacturer'] = manufacturerID # Set Manufacturer ID for NetBox
        yaml_object['front_image'] = None # Clear existing images to avoid import errors
        yaml_object['rear_image'] = None
# region ##### Convert YAML to JSON
        jsondata = json.dumps(yaml_object)
        jsondata = json.loads(jsondata)
# endregion
# endregion
# region #### Load Device Type to NetBox
# region ##### Add Device Type to NetBox
        r = requests.post(url,headers=netboxheaders,json=jsondata,verify=False)
        if r.status_code == 201:
            deviceID = r.json()['id']
            slug = r.json()['slug']
# endregion
# region ##### Add properties to Device Type
# region ###### Assign image to Device Type
            imagedir = os.path.join(repodir, 'elevation-images', vendorlibrary)
            images = os.listdir(imagedir)
            baseimagenames = [os.path.splitext(image)[0] for image in images]
            netboxheadersimage = {'Authorization': f'Token {netboxtoken}'}
            for i in ['front','rear']:
                image = get_close_matches(slug + '.' + i, baseimagenames, n=1 , cutoff=deviceimagesensitivity)
                if image:
                    score = SequenceMatcher(None, slug, image[0]).ratio()
                    if score >= deviceimagesensitivity:
                        mapping_image = f'{slug},Success,{image[0]},{score:.2f}'
                    elif not image:
                        mapping_image = f'{slug},Fail,No Match,'
                    else:
                        mapping_image = f'{slug},Fail,{image[0]},{score:.2f}'
                    mappings_image.append(mapping_image)
                    idx = baseimagenames.index(image[0])
                    image = [images[idx]]
                    imagepath = os.path.join(imagedir, image[0])
                    file = {i + '_image': (image[0], open(imagepath, 'rb'))}
                    r = requests.patch(f'{netboxbaseurl}dcim/device-types/{deviceID}/',headers=netboxheadersimage,files=file,verify=False)
# endregion
            add_device_type_components(yaml_object, objecttype, deviceID, netboxbaseurl, netboxheaders)
# region #### Log failed imports
        else:
            import_error = f'{vendorlibrary},{devicetypelibrary},{r.status_code},{r.text}'
            errors_importdevice.append(import_error)
            if r.text.find('already exists') != -1:
                duplicate += 1
        importCounter += 1
        taskend = datetime.datetime.now()
        taskduration.append((taskend - taskstart).total_seconds())
        remaining = sum(taskduration) / len(taskduration) * (len(ipf_models) - importCounter)
        print(f'Import progress: [{"█" * int(importCounter/len(ipf_models)*100):100}] {importCounter/len(ipf_models)*100:.2f}% Complete - ({importCounter}/{len(ipf_models)}) device types imported. Remaining: {remaining:.2f}s', end="\r")
# endregion
# endregion
# endregion
# endregion
# region ## Summary of Device Type Import
print(f'Netbox device import complete. {duplicate} duplicates skipped, {nomatch} models not found in Device Type Library.')
# endregion
# endregion

# region # Import IP Fabric Modules to NetBox
# region ## Export list of modules from IP Fabric
print('Getting modules from IP Fabric...')
ipf_modules = IPFexporter.export_ipf_data('inventory/pn', ['pid', 'vendor', 'deviceSn', 'dscr', 'pid', 'sn'])
print(f'Total modules fetched from IP Fabric: {len(ipf_modules)}')
# endregion
# region ## Transform module data
# region ### Remove invalid modules - IP Fabric sometimes includes device chassis as modules, filter these out
for m in ipf_modules:
    if m['sn'] == m['deviceSn']:
        ipf_modules.remove(m)
    elif m['pid'] == m['dscr']:
        ipf_modules.remove(m)
    elif m['pid'] == m['model']:
        ipf_modules.remove(m)
print(f'Total valid modules: {len(ipf_modules)}')
# endregion
# region ### Filter unique modules
print('Filtering unique modules...')
objecttype = 'module'
modulesdf = ipf_modules
df = pd.DataFrame(modulesdf)
df['data'] = df['pid'].apply(lambda v: v.get('data') if isinstance(v, dict) else v)
df = df[['vendor', 'data']].dropna()
modules = {"modules": {}}
for vendor, group in df.groupby('vendor'):
    modules["modules"][vendor] = {datum for datum in group['data'].unique()}
unique_modules = sum(len(m) for m in modules["modules"].values())
print(f'Total unique modules from IP Fabric: {unique_modules}')
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
# endregion
# region ## Prepare module data for import
print('Importing modules into NetBox...')
for i in modules['modules']:
    vendor = i
    lowermanufacturernames = [manufacturer.lower() for manufacturer in manufacturers]
    vendorlibrary = get_close_matches(vendor.lower(),lowermanufacturernames, n=1 , cutoff=vendornamesensitivity)
    idx = lowermanufacturernames.index(vendorlibrary[0])
    vendorlibrary = manufacturers[idx]
    if not vendorlibrary:
        vendorlibrary = vendor
    if not os.path.exists(os.path.join(repodir, 'module-types', vendorlibrary)):
        print(f'No module types found for vendor {vendorlibrary}')
        continue
    moduleslist = os.listdir(os.path.join(repodir, 'module-types', vendorlibrary))
    basemodulenames = [os.path.splitext(module.lower())[0] for module in moduleslist]
# region ### Find Manufacture ID from NetBox
    url = f'{netboxbaseurl}dcim/manufacturers/?slug={vendor}'
    vendor = vendorlibrary
    manufacturerID = netbox_vendors.get(vendor.lower(), None)
# endregion
# region ### Find Module Type YAML in Device Type Library and prepare for import
    importCounter = 0
    taskduration = []
    for module in modules['modules'][i]:
        taskstart = datetime.datetime.now()
        moduletypelibrary = get_close_matches(module.lower(),basemodulenames, n=1 , cutoff=modulenamesensitivity)
        if moduletypelibrary:
            score = SequenceMatcher(None, module.lower(), moduletypelibrary[0]).ratio()
            idx = basemodulenames.index(moduletypelibrary[0])
            moduletypelibrary = moduleslist[idx]
            if score >= modulenamesensitivity:
                mapping_module = f'{module},Success,{moduletypelibrary},{score:.2f}'
            elif not moduletypelibrary:
                mapping_module = f'{module},Fail,No Match,'
            else:
                mapping_module = f'{module},Fail,{moduletypelibrary},{score:.2f}'
            mappings_module.append(mapping_module)
            yamlpath = os.path.join(repodir, 'module-types', vendorlibrary, moduletypelibrary)
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
# region ## Load Module Type to NetBox
            url = f'{netboxbaseurl}dcim/module-types/'
            jsondata = json.dumps(yaml_object)
            jsondata = json.loads(jsondata)
            r = requests.post(url,headers=netboxheaders,json=jsondata,verify=False)
            if r.status_code == 201:
                modulename = r.json()['model']
                deviceID = r.json()['id']
                add_device_type_components(yaml_object, objecttype, deviceID, netboxbaseurl, netboxheaders)
            else:
                import_error = f'{vendorlibrary},{moduletypelibrary},{r.status_code},{r.text}'
                errors_importmodule.append(import_error)
        else:
            nomatch += 1
            error_text = f'{vendorlibrary},{module}'
            errors_matchmodule.append(error_text)
        importCounter += 1
        taskend = datetime.datetime.now()
        taskduration.append((taskend - taskstart).total_seconds())
        remaining = sum(taskduration) / len(taskduration) * (len(modules['modules'][i]) - importCounter)
        print(f'Import progress: [[{"█" * int(importCounter/len(modules["modules"][i])*100):100}]{importCounter/len(modules["modules"][i])*100:.2f}% Complete - ({importCounter}/{len(modules["modules"][i])}) {i} modules imported. Remaining: {remaining:.2f}s', end="\r")
    print('\n')
print(f'Netbox module import complete.')
# endregion
# endregion
# region # Output logs and summaries
with open(os.path.join(log_dir, 'DeviceTypeImport_Errors_MatchDevice.csv'), 'w') as f:
    for item in errors_matchdevice:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Errors_MatchModule.csv'), 'w') as f:
    for item in errors_matchmodule:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Errors_MatchVendor.csv'), 'w') as f:
    for item in errors_matchvendor:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Errors_ImportComponents.csv'), 'w') as f:
    for item in errors_importcomponents:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Errors_ImportDevice.csv'), 'w') as f:
    for item in errors_importdevice:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Errors_ImportModule.csv'), 'w') as f:
    for item in errors_importmodule:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Mappings_Device.csv'), 'w') as f:
    for item in mappings_device:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Mappings_Image.csv'), 'w') as f:
    for item in mappings_image:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Mappings_Module.csv'), 'w') as f:
    for item in mappings_module:
        f.write("%s\n" % item)
with open(os.path.join(log_dir, 'DeviceTypeImport_Mappings_Vendor.csv'), 'w') as f:
    for item in mappings_vendor:
        f.write("%s\n" % item)
endtime = datetime.datetime.now()
duration = endtime - starttime
print(f'Device Type and Module Type import process completed in {duration}')
print(f'Total device types processed: {len(ipf_models)}')
print(f'Total module types processed: {len(ipf_modules)}')
print(f'Total device types failed to import: {len(errors_importdevice)-1}')
print(f'Total module types failed to import: {len(errors_importmodule)-1}')
print(f'Total device types failed to match: {len(errors_matchdevice)-1}')
print(f'Total module types failed to match: {len(errors_matchmodule)-1}')
print(f'Total component errors: {len(errors_importcomponents)-1}')
# endregion