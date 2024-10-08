import sys
import time

import linode_api4
import requests
from linode_api4 import LinodeClient, StackScript

import network


def deploy_server(config: dict, client: LinodeClient, region: str, firewall_id: str, server_vpc_ip: str, vpc_subnet: str):
    linode_image = 'linode/debian11'
    linode_type = 'g6-standard-2'
    linode_label = config['settings']['cluster_prefix'] + 'server'

    print('# Deploying Hashtopolis server')
    ht_server, p_ = client.linode.instance_create(
        linode_type,
        region,
        image=linode_image,
        label=linode_label,
        firewall=firewall_id,
        booted=False,
        stackscript=StackScript(client, int(config['stackscripts']['server'])),
        stackscript_data={
            'DOMAIN_NAME': config['settings']['domain']
        }
    )

    print(f'# Updating A record for {config['settings']['domain']}')
    network.update_a_record(
        config['keys']['godaddy_key'],
        config['keys']['godaddy_secret'],
        '.'.join(config['settings']['domain'].split('.')[-2:]),
        config['settings']['domain'].split('.')[0],
        ht_server.ipv4[0]
    )

    print(' - waiting for proper DNS resolution')
    if network.wait_for_dns_update(config['settings']['domain'], ht_server.ipv4[0]):
        print('\n - DNS record match')
    else:
        print('\n - no DNS change, timeout')
        sys.exit(1)

    print('# Adding certbot firewall exception, this is temporary')
    network.set_rules(client.token, firewall_id, [
        {
            'label': 'allow-certbot-verification',
            'ports': [80, 443],
            'allowed_ipv4s': ['0.0.0.0/0']
        }
    ])

    network.add_to_vpc_subnet(config, client, ht_server.id, server_vpc_ip)

    print(f'# Booting {linode_label}')
    ht_server.boot()
    print(' - booted')

    print(f'# Waiting for {linode_label} StackScripts to do their job')
    sleep_time = 230
    for i in range(sleep_time, 0, -1):
        print(f'\r - sleeping {int(i // 60)}:{int(i % 60):02} ', end='', flush=True)
        time.sleep(1)

    print('\n - waiting for nginx')
    server_url = 'https://' + config['settings']['domain']
    check_for_nginx(server_url)
    print(' - nginx is up')

    print('# Setting final firewall rules')
    network.set_rules(client.token, firewall_id, [
        {
            'label': 'allow-admin-only',
            'ports': [22, 80, 443],
            'allowed_ipv4s': [network.get_this_machine_ip()]
        }, {
            'label': 'allow-agents',
            'ports': [8080, 443],
            'allowed_ipv4s': [vpc_subnet]
        }
    ])

    print('# Waiting to finish all processes')
    poller = client.polling.event_poller_create(
        'linode',
        'linode_reboot',
        entity_id=ht_server.id,
    )

    while True:
        try:
            ht_server.reboot()
            print('# Rebooting')
            poller.wait_for_next_event_finished()
            break
        except linode_api4.errors.ApiError:
            time.sleep(10)
            continue

    print('# Hashtopolis server deployed successfully')


def check_for_nginx(server_url: str):
    interval = 4
    while True:
        time.sleep(interval)
        try:
            if '502 Bad Gateway' in requests.get(server_url, timeout=4).text:
                break
            else:
                continue
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError, requests.exceptions.SSLError):
            pass
