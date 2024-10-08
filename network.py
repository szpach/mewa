import ipaddress
import time

import dns.resolver
import linode_api4
import requests
from linode_api4 import LinodeClient


def get_firewalls_list(client: LinodeClient):
    return client.networking.firewalls()


def firewall_exists(client: LinodeClient, firewall_name: str):
    for firewall in get_firewalls_list(client):
        if firewall.label == firewall_name:
            return firewall.id

    return None


def get_firewall(client: LinodeClient, firewall_label: str):
    print('# Creating firewall...')

    firewall_id = firewall_exists(client, firewall_label)
    if firewall_id:
        print(f' - {firewall_label} already exists')
        return firewall_id

    firewall = client.networking.firewall_create(
        label=firewall_label,
        rules={
            'inbound': [],
            'outbound': [],
            'inbound_policy': 'DROP',
            'outbound_policy': 'ACCEPT'
        }
    )
    print(' - done')
    return firewall.id


def remove_firewall(token: str, firewall_id: int):
    url = f'https://api.linode.com/v4/networking/firewalls/{firewall_id}'
    headers = {
        'accept': 'application/json',
        'authorization': f'Bearer {token}'
    }

    requests.delete(url, headers=headers)


def set_rules(token: str, firewall_id: str, rules: list):
    print('# Modifying firewall inbound rules...')
    for rule in rules:
        print(f' - {rule['label']} ACCEPT TCP {rule['ports']} {', '.join(rule['allowed_ipv4s'])}')

    url = f"https://api.linode.com/v4/networking/firewalls/{firewall_id}/rules"

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    data = {
        'inbound': translate_inbound_rules(rules),
        'outbound': []
    }

    requests.put(url, headers=headers, json=data)


def translate_inbound_rules(rules: list):
    translated_rules = []
    for rule in rules:
        translated_rules.append(
            {
                'label': rule['label'],
                'action': 'ACCEPT',
                'protocol': 'TCP',
                'ports': ', '.join([str(port) for port in rule['ports']]),
                'addresses': {'ipv4': rule['allowed_ipv4s']}
            }
        )

    return translated_rules


def get_this_machine_ip():
    url = 'https://forcedeye.com/ip'
    my_ip = requests.get(url).text.split()[0].strip()
    print(f'# This machine\'s IP: {my_ip}')

    return str(my_ip + '/32')


def update_a_record(api_key, api_secret, domain, record_name, new_ip, ttl=600):
    print('# Updating DNS')
    url = f'https://api.godaddy.com/v1/domains/{domain}/records/A/{record_name}'
    headers = {
        'Authorization': f'sso-key {api_key}:{api_secret}',
        'Content-Type': 'application/json'
    }
    payload = [{
        'data': new_ip,
        'ttl': ttl
    }]

    response = requests.put(url, json=payload, headers=headers)
    if response.json()['message'] == 'Authenticated user is not allowed access':
        print(' - you have fewer than 10 domains on godaddy')
        print(' - this is godaddy\'s policy for allowing api access')
        print(' ! you need to update this record manually')
        print(f' ! {new_ip}')
        print(f' ! {record_name}.{domain}')
    else:
        print(' - updated')


def wait_for_dns_update(domain, expected_ip, timeout=800, interval=11):
    start_time = time.time()
    once_printed = False

    while time.time() - start_time < timeout:
        time_left = int(timeout - (time.time() - start_time))

        if not once_printed and time.time() - start_time > 600:
            print(f'\r - sometimes it takes a while', flush=True)
            once_printed = True

        print(f'\r - 600s TTL: {600 + int(start_time - time.time())} s, timeout in {time_left} s ', end='', flush=True)

        try:
            answers = dns.resolver.resolve(domain, 'A')
            current_ip = answers[0].to_text()
            if current_ip == expected_ip:
                return True
        except dns.resolver.NXDOMAIN:
            pass

        time.sleep(interval)

    return False


def build_vpc(config: dict, client: LinodeClient, region: str, vpc_subnet='10.0.77.0/24'):
    return client.vpcs.create(
        label=config['settings']['cluster_prefix'].replace("_", "-") + 'vpc',
        region=region,
        subnets=[
            {
                'label': config['settings']['cluster_prefix'].replace("_", "-") + 'vpc-subnet',
                'ipv4': vpc_subnet
            }
        ]
    ).id


def get_vpc_info(config: dict, client: LinodeClient):
    related_entities = {}
    vpc_info = client.vpcs()
    for v in vpc_info:
        if config['settings']['cluster_prefix'].replace("_", "-") + 'vpc' == v.label:
            related_entities['vpc'] = {
                'label': v.label,
                'id': v.id,

            }
            for s in v.subnets:
                if config['settings']['cluster_prefix'].replace("_", "-") + 'vpc-subnet' == s.label:
                    related_entities['subnet'] = {
                        'label': s.label,
                        'id': s.id
                    }

    return related_entities


def remove_vpc(client: LinodeClient, vpc_id: str):
    url = 'https://api.linode.com/v4/vpcs/' + vpc_id
    headers = {'authorization': 'Bearer ' + client.token}
    requests.delete(url, headers=headers)


def get_interface_data(client: LinodeClient, linode_id: int):
    url = f'https://api.linode.com/v4/linode/instances/{linode_id}/configs'

    headers = {
        'accept': 'application/json',
        'authorization': 'Bearer ' + client.token
    }

    response = requests.get(url, headers=headers).json()

    interface_data = response['data'][0]['interfaces']
    vpc_interface = next((interface for interface in interface_data if interface['purpose'] == 'vpc'), None)

    return {
        'config_id': response['data'][0]['id'] if response else None,
        'vpc_ip': vpc_interface['ipv4']['vpc'] if vpc_interface else None,
        'vpc_id': vpc_interface['vpc_id'] if vpc_interface else None,
        'subnet_id': vpc_interface['subnet_id'] if vpc_interface else None,
        'interface_id': vpc_interface['id'] if vpc_interface else None
    }


def get_vpc_addr_list(cidr: str, agents_amount: int):
    net = list(ipaddress.ip_network(cidr).hosts())
    return [str(ip) for ip in net[1:2 + agents_amount]]


def add_to_vpc_subnet(config: dict, client: LinodeClient, linode_id: int, vpc_ip: str):
    linode_instance = linode_api4.Instance(client, linode_id)

    print(f'# Configuring VPC for {linode_instance.label}')
    print(f' - VPC IP: {vpc_ip}')
    inter = get_interface_data(client, linode_id)
    vpc = get_vpc_info(config, client)

    url = f'https://api.linode.com/v4/linode/instances/{linode_id}/configs/{inter['config_id']}/interfaces'

    payload = {
        'purpose': 'vpc',
        'primary': True,
        'active': True,
        'ipam_address': None,
        'vpc_id': vpc['vpc']['id'],
        'subnet_id': vpc['subnet']['id'],
        'ipv4': {
            'nat_1_1': linode_instance.ipv4[0],
            'vpc': vpc_ip
        },
        'ip_ranges': []
    }
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'authorization': 'Bearer ' + client.token
    }

    requests.post(url, json=payload, headers=headers)
    print(' - added successfully')
