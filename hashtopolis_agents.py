import random
import string
import sys
import time

import requests
from linode_api4 import LinodeClient, StackScript

import network


def deploy_linodes(config: dict, client: LinodeClient, region: str, firewall_id: str, type_id: str, amount: int, vpc_addresses: list):
    print('Deploying Linodes')
    while get_agents(config['settings']['domain'], config['keys']['hashtopolis']) == 0:
        input('# Update your Hashtopolis API key in config file and hit enter')

    linode_image = 'linode/debian11'
    counter = 0
    for voucher in get_x_vouchers(amount, config['settings']['domain'], config['keys']['hashtopolis']):
        counter += 1
        linode_label = config['settings']['cluster_prefix'] + f'agent_{counter:02}'
        print(f'# Deploying {linode_label}...')
        agent, _ = client.linode.instance_create(
            type_id,
            region,
            image=linode_image,
            label=linode_label,
            firewall=firewall_id,
            booted=False,
            stackscript=StackScript(client, int(config['stackscripts']['agent'])),
            stackscript_data={
                'VOUCHER': voucher,
                'DOWNLOAD_URL': f'https://{vpc_addresses[0]}/agents.php?download=1',
                'API_URL': f'http://{vpc_addresses[0]}:8080/api/server.php'
            }
        )

        network.add_to_vpc_subnet(config, client, agent.id, vpc_addresses[counter])
        agent.boot()
        print(f'# {linode_label} done')

    print('# Waiting for Linodes to synchronize with the server...')
    start_time = time.time()
    while True:
        if len(get_agents(config['settings']['domain'], config['keys']['hashtopolis'])) == amount:
            print('\n - synchronized')
            break
        else:
            print(f'\r - elapsed {int(time.time() - start_time)} seconds', end='', flush=True)
            time.sleep(10)


def get_x_vouchers(x: int, domain: str, token: str):
    url = f'https://{domain}/api/user.php'
    vouchers = []

    for i in range(x):
        voucher = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
        payload = {
            'section': 'agent',
            'request': 'createVoucher',
            'voucher': voucher,
            'accessKey': token
        }

        try:
            response = requests.post(url, json=payload).json()
        except requests.exceptions.ConnectionError:
            print(f'# Incorrect domain {domain}')
            sys.exit(1)

        if response.get('response') == 'OK':
            vouchers.append(voucher)
        else:
            print('# Can\'t get hashtopolis vouchers')
            sys.exit(1)

    return vouchers


def get_agents(domain: str, token: str):
    url = f'https://{domain}/api/user.php'
    payload = {
        "section": "agent",
        "request": "listAgents",
        'accessKey': token
    }
    while True:
        try:
            response = requests.post(url, json=payload).json()
            if response.get('response') == 'OK':
                return response['agents']
            elif response.get('message') == 'Invalid access key!':
                return 0
            else:
                print('# Can\'t get hashtopolis agents')
                sys.exit(1)
        except requests.exceptions.ConnectionError:
            time.sleep(5)
            continue
