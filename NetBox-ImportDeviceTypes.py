'''
Import device types using NetBox DeviceTypeLibrary from a YAML file.

Created by: Dan Kelcher
Date: February 23, 2026
'''

import os

from NetBoxHelper import *
from pathlib import Path
from collections import defaultdict
from git import Repo
from dotenv import load_dotenv
from difflib import get_close_matches
from difflib import SequenceMatcher
import argparse
import yaml


inventory_yaml_file = os.path.join('DataSources', 'Inventory.yaml')
 
ap = argparse.ArgumentParser(description="Import Sites from IP Fabric into NetBox")
ap.add_argument("--branch", help="Create a NetBox branch for this import")
args = ap.parse_args()
if args.branch:
    branchurl = f'?_branch={args.branch}'
    schemaID = args.branch
else:
    branchurl = ''
    schemaID = None

def setup():
    # Load environment variables from .env file
    load_dotenv(override=True)
    reposource = os.getenv('reposource', 'https://github.com/netbox-community/devicetype-library.git')
    vendornamesensitivity = float(os.getenv('vendornamesensitivity', '0.8'))
    # Load NetBox configuration
    #netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = load_netbox_config()
    return reposource, vendornamesensitivity

def get_manufacturers(schemaID=schemaID):
    manufacturers = []
    output = get_netbox_data('dcim/manufacturers',filters={'_branch='+schemaID} if schemaID else None)
    for i in output:
        data = {
            "name": i['name'],
            "id": i['id']
            }
        manufacturers.append(data)
    return manufacturers

def get_device_types(schemaID=schemaID):
    device_types = defaultdict(set)
    # This function can be used to retrieve existing device types from NetBox if needed
    output = get_netbox_data('dcim/device-types',filters={'_branch='+schemaID} if schemaID else None)
    device_types = []
    for i in output:
        manufacturer = i['manufacturer']['name'] if i['manufacturer'] else 'Unknown'
        manufacturerID = i['manufacturer']['id'] if i['manufacturer'] else None
        model = i['model'] if i['model'] else 'Unknown'
        data = {
            "model": model,
            "manufacturer": manufacturer,
            "manufacturerID": manufacturerID
            }
        device_types.append(data)
    return device_types

def get_yaml_data(inventory_yaml_file):
    # This function can be used to load device types from a YAML file
    with open(inventory_yaml_file, 'r') as f:
        inventory_list= yaml.safe_load(f)
    return inventory_list

def get_repo_dir():
    try:
        currentdir = Path(__file__).parent # Get directory of current script
    except:
        currentdir = os.getcwd() # Fallback to current working directory
    repodir = os.path.join(currentdir, 'DataSources', 'DeviceTypeLibraryRepo')
    if not os.path.exists(repodir):
        os.mkdir(repodir)
    return repodir

def pull_repo(repodir, reposource):
    if os.path.exists(os.path.join(repodir, '.git')):
        repo = Repo(repodir)
        origin = repo.remotes.origin
        origin.pull()
    else:
        print(f'Cloning DeviceType-Library repository from {reposource}')
        Repo.clone_from(reposource, repodir)

def manufacturers_to_import(inventory_list, manufacturers):
    import_manufacturers = set()
    for v in inventory_list['devices'] or []:
        vendor = v['manufacturer'] if v.get('manufacturer') else 'Unknown'
        if vendor not in [m['name'] for m in manufacturers]:
            import_manufacturers.add(vendor)
    for v in inventory_list['modules'] or []:
        vendor = v['manufacturer'] if v.get('manufacturer') else 'Unknown'
        if vendor not in [m['name'] for m in manufacturers]:
            import_manufacturers.add(vendor)
    return import_manufacturers

def model_to_import(inventory_list, existing_device_types):
    import_model = []
    for v in inventory_list['devices']:
        vendor = v['manufacturer'] if v.get('manufacturer') else 'Unknown'
        for m in v['models'] or []:
            model = m if m else 'Unknown'
            if model not in existing_device_types.get(vendor, []):
                import_model.append((vendor, model))
        else:
            print(f"Device type {vendor} {model} already exists in NetBox and will be skipped.")
    return import_model

def create_manufacturer(import_manufacturers):
    # This function can be used to create manufacturers in NetBox if needed
    for m in import_manufacturers:
        print(f'Creating manufacturer {m} in NetBox...')
        payload = {}
        data = {
            'name': m,
            'slug': m.lower().replace(' ', '-')
            }
        payload.update(data)
        print(payload)
        r = post_netbox_data('dcim/manufacturers', payload)
        if r.get('id'):
            print(f'Manufacturer {m} created successfully with ID {r["id"]}.')
        else:
            print(f'Failed to create manufacturer {m}. Response: {r}')

def get_manufacturer_folder(manufacturer, repodir, lookup_type, vendornamesensitivity):
    if lookup_type == 'device' or lookup_type == 'module':
        folder = 'device-types' if lookup_type == 'device' else 'module-types'
        manufacturer_folder = os.path.join(repodir, folder, manufacturer)
        if os.path.isdir(manufacturer_folder):
            return manufacturer_folder
        else:
            manufacturer_folder = get_close_matches(manufacturer, os.listdir(os.path.join(repodir, folder)), n=1, cutoff=vendornamesensitivity)
            if manufacturer_folder:
                return os.path.join(repodir, folder, manufacturer_folder[0])
            else:print(f'Manufacturer folder for {manufacturer} not found in repository under {folder}.')
            return None

def get_device_yaml(model, manufacturer_folder):
    yaml_file = os.path.join(manufacturer_folder, f'{model}.yaml')
    if os.path.isfile(yaml_file):
        with open(yaml_file, 'r') as f:
            device_yaml = yaml.safe_load(f)
        return device_yaml
    else:
        print(f'YAML file for model {model} not found in repository.')
        return None

def enrich_device_type_data(import_model, manufacturers, device_yaml):
    enriched_data = []
    for vendor, model in import_model:
        manufacturer_id = next((m['id'] for m in manufacturers if m['name'] == vendor), None)
        enriched_data.append({
            'manufacturer': manufacturer_id,
            'model': model
        
        })
    return enriched_data

def main():
    reposource, vendornamesensitivity = setup()
    existing_device_types = get_device_types()
    inventory_list = get_yaml_data(inventory_yaml_file)
    repodir = get_repo_dir()
    pull_repo(repodir, reposource)
    manufacturers = get_manufacturers()
    import_manufacturers = manufacturers_to_import(inventory_list, manufacturers)
    create_manufacturer(import_manufacturers)
    manufacturers = get_manufacturers() # Refresh manufacturers list after potential imports
    import_models = model_to_import(inventory_list, existing_device_types)
    for i in import_models:
        manufacturer_folder = get_manufacturer_folder(i[0], repodir, 'device', vendornamesensitivity)
        if manufacturer_folder:
            device_yaml = get_device_yaml(i[1], manufacturer_folder)
            if device_yaml:
                enriched_data = enrich_device_type_data(import_models, manufacturers, device_yaml)
                print(f'Enriched data for {i[0]} {i[1]}: {enriched_data}')
                # Here you would add the code to create the device type in NetBox using the enriched data
    
    print('Task completed successfully.')
    print('Existing device types retrieved from NetBox:')
    print(existing_device_types)
    print('--------------------------------------------------------------')
    print('Device types loaded from YAML file:')
    print(inventory_list)
    print('--------------------------------------------------------------')
    print(f'DeviceType-Library repository is located at: {repodir}')
    print('--------------------------------------------------------------')
    print('Vendors to import:')
    print(import_manufacturers)
    print('--------------------------------------------------------------')
    print('Models to import:')
    print(model_to_import)
    print('--------------------------------------------------------------')

if __name__ == "__main__":
    main()