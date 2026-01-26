'''
Module for loading IP Fabric configuration to be used in other scripts.

Created by: Dan Kelcher
Date: January 7, 2026
'''

# region # Imports and setup
import requests
import urllib3
from dotenv import load_dotenv
import os

def load_netbox_config():
# region ## Check for .env
    if os.path.isfile('.env'):
        pass
    else:
        print('.env file not found. Create a .env file with the required settings.')
        import CreateEnvFile
        CreateEnvFile.create_env_file()
# endregion
# region ## Load .env variables
    load_dotenv(override=True)
    netboxbaseurl = os.getenv('netboxbaseurl')
    netboxtoken = os.getenv('netboxtoken')
    netboxlimit = int(os.getenv('netboxlimit', '100'))
    disableverifyssl = os.getenv('disableverifyssl')
    if disableverifyssl == 'True':
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# endregion
# region ## Set up NetBox API connection
    netboxheaders = {
        'content-type': 'application/json',
        'accept': 'application/json',
        'Authorization': f'Token {netboxtoken}'
        }
# endregion
# region ## Test NetBox connection
    url = f'{netboxbaseurl}dcim/manufacturers/'
    try:
        r = requests.get(url,headers=netboxheaders,verify=False)
        if r.status_code != 200:
            print(f'Failed to connect to NetBox API. Status code: {r.status_code}')
        else:
            print('Successfully connected to NetBox API.')
            return netboxbaseurl, netboxtoken, netboxheaders, netboxlimit
    except:
        print(f'Failed to connect to NetBox API.')
# endregion

# region # Test function
if __name__ == '__main__':
    netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = load_netbox_config()
    print('NetBox configuration loaded successfully.')
    print(f'NetBox Base URL: {netboxbaseurl}')
    print(f'NetBox API Token: {netboxtoken}')
    print(f'NetBox Limit: {netboxlimit}')
    print(f'NetBox Headers: {netboxheaders}')
# endregion