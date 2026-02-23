'''
Import device types using NetBox DeviceTypeLibrary from a YAML file.

Created by: Dan Kelcher
Date: February 23, 2026
'''

import os

from NetBoxloader import load_netbox_config
from NetBoxHelper import *
from pathlib import Path
from collections import defaultdict
from git import Repo
from dotenv import load_dotenv
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
    # Load NetBox configuration
    netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = load_netbox_config()
    return reposource

def get_device_types(schemaID=schemaID):
    device_types = defaultdict(set)
    # This function can be used to retrieve existing device types from NetBox if needed
    data = export_netbox_data('dcim/device-types',filters={'_branch='+schemaID} if schemaID else None)
    for i in data:
        vendor = i['manufacturer']['name'] if i['manufacturer'] else 'Unknown'
        model = i['model'] if i['model'] else 'Unknown'
        device_types[vendor].add(model)
    existingdevicetypes = {vendor: list(models) for vendor, models in device_types.items()}
    return existingdevicetypes

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

def to_import(inventory_list, existing_device_types):
    vendors_to_import = []
    model_to_import = []
    for v in inventory_list['devices']:
        vendor = v['manufacturer'] if v.get('manufacturer') else 'Unknown'
        if vendor not in existing_device_types:
            vendors_to_import.append(vendor)
        for m in v['models'] or []:
            model = m if m else 'Unknown'
            if model not in existing_device_types.get(vendor, []):
                model_to_import.append((vendor, model))
        else:
            print(f"Device type {vendor} {model} already exists in NetBox and will be skipped.")
    return vendors_to_import, model_to_import

def create_manufacturer(vendors_to_import):
    # This function can be used to create manufacturers in NetBox if needed
    for vendor in vendors_to_import:
        print(f'Creating manufacturer {vendor} in NetBox...')



def main():
    reposource = setup()
    existing_device_types = get_device_types()
    inventory_list = get_yaml_data(inventory_yaml_file)
    repodir = get_repo_dir()
    pull_repo(repodir, reposource)
    vendors_to_import, model_to_import = to_import(inventory_list, existing_device_types)
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
    print(vendors_to_import)
    print('--------------------------------------------------------------')
    print('Models to import:')
    print(model_to_import)
    print('--------------------------------------------------------------')

if __name__ == "__main__":
    main()