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
from pathlib import Path

def load_ipf_config():
# region ## Check for .env
    try:
        currentdir = Path(__file__).parent # Get directory of current script
    except:
        currentdir = os.getcwd() # Fallback to current working directory
    if os.path.isfile(os.path.join(currentdir, '.env')):
        pass
    else:
        print('.env file not found. Create a .env file with the required settings.')
        import CreateEnvFile
        CreateEnvFile.create_env_file()
# endregion
# region ## Load .env variables
    load_dotenv(override=True)
    ipfbaseurl = os.getenv('ipfabricbaseurl')
    ipftoken = os.getenv('ipfabrictoken')
    disableverifyssl = os.getenv('disableverifyssl')
    ipflimit = int(os.getenv('ipflimit', '1000'))
    if disableverifyssl == 'True':
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# endregion
# region ## Set up IP Fabric API connection
    ipfheaders = {
        'content-type': 'application/json',
        'accept': 'application/json',
        'x-api-token': ipftoken
        }
# endregion
# region ## Test IP Fabric connection
    url = f'{ipfbaseurl}snapshots/'
    try:
        r = requests.get(url,headers=ipfheaders,verify=False)
        if r.status_code != 200:
            print(f'Failed to connect to IP Fabric API. Status code: {r.status_code}')
        else:
            print('Successfully connected to IP Fabric API.')
            return ipfbaseurl, ipftoken, ipfheaders, ipflimit
    except:
        print(f'Failed to connect to IP Fabric API.')

# endregion

if __name__ == '__main__':
    load_ipf_config()