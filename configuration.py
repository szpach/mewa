import requests
import json
import yaml
import os

from linode_api4 import LinodeClient

import misc


def get_config(filename):
    if not os.path.exists(filename):
        print('# No config file found')
        return create_config(filename)
    else:
        return load_config(filename)


def create_config(file_name):
    print('# Creating config file')
    config = dict()

    config['keys'] = {
        'linode': input(' - enter Linode API key: '),
        'godaddy_key': input(' - enter GoDaddy key: '),
        'godaddy_secret': input(' - enter GoDaddy secret: '),
        'hashtopolis': '1234abcd'
    }

    config['stackscripts'] = {
        'server': input(' - enter server StackScripts ID: '),
        'agent': input(' - enter agent StackScripts ID: ')
    }

    default_prefix = 'htp_cluster_'
    cluster_prefix = input(f' - enter cluster prefix (default: {default_prefix}): ')
    config['settings'] = {
        'cluster_prefix': cluster_prefix if cluster_prefix else default_prefix,
        'domain': input(' - enter domain name: '),
        'autoclean_when_failed': 0
    }

    with open(file_name, 'w') as file:
        yaml.dump(dict(config), file, default_flow_style=False)
        print('# Config file created')

    return config


def load_config(filename: str):
    print('# Reading config file')
    with open(filename, 'r') as file:
        config = yaml.safe_load(file)
        return config


def reconfig(config_filename: str):
    if not os.path.exists(config_filename):
        print('# No config file found')
        print('# Create config file?', end=' ')
    else:
        print('# Config file found')
        print('# Reconfigure?', end=' ')

    misc.confirmation()
    create_config(config_filename)


def pick_region(client: LinodeClient):
    available_regions = client.regions()

    for index, item in enumerate(available_regions, start=1):
        print(f'{index:>2}. {item.label}')

    while True:
        try:
            linode_region = int(input('# Choose a region: '))
            if 1 <= linode_region <= len(available_regions):
                print()
                return available_regions[int(linode_region) - 1].label, available_regions[int(linode_region) - 1].id
        except ValueError:
            continue


def pick_type():
    url = 'https://api.linode.com/v4/linode/types'
    headers = {'accept': 'application/json'}

    response = requests.get(url, headers=headers)
    data = json.loads(response.text)['data']

    for index, item in enumerate(data, start=1):
        print(f'{index:>2}. {item['label']}')

    while True:
        linode_type = int(input('# Choose a type: '))
        if 1 <= linode_type <= len(data):
            print()
            return data[linode_type - 1]['label'], data[linode_type - 1]['id']


def pick_amount():
    amount = int(input('# Choose an amount: '))
    while True:
        if 1 <= amount <= 30:
            print()
            return amount
        else:
            amount = int(input(f'# {amount}? Let me rephrase, choose a REASONABLE amount: '))