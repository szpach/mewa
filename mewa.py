import sys
import time

import linode_api4
from linode_api4 import LinodeClient

import configuration as conf
import hashtopolis_agents as hta
import hashtopolis_server as hts
import misc
import network


def deploy(config: dict, client: LinodeClient, server: bool, linodes: bool, vpc_subnet: str = '10.0.77.0/24'):
    start_time = time.time()
    linode_region_label, linode_region_id = conf.pick_region(client)
    linode_type_label, linode_type_id = '', ''
    linode_amount = 0

    if linodes:
        linode_type_label, linode_type_id = conf.pick_type()
        linode_amount = conf.pick_amount()

    if server and linodes:
        print(f'A Hashcat server and {linode_amount} {linode_type_label} '
              f'instances will be deployed in {linode_region_label} at https://{config['settings']['domain']}. '
              f'Continue?', end=' ')
    elif server:
        print(f'# A hashcat server will be deployed in {linode_region_label} at https://{config['settings']['domain']}. '
              f'Continue?', end=' ')
    elif linodes:
        print(f'# {linode_amount} {linode_type_label} '
              f'instances will be deployed in {linode_region_label}. '
              f'Continue?', end=' ')

    misc.confirmation()
    print('# Setting up VPC network')
    vpc_addresses = network.get_vpc_addr_list(vpc_subnet, linode_amount)
    try:
        network.build_vpc(config, client, linode_region_id)
    except linode_api4.errors.ApiError:
        print(' - VPC already exists')
    print(' - done')

    if server:
        server_firewall_id = network.get_firewall(client, config['settings']['cluster_prefix'] + 'server_firewall')
        hts.deploy_server(config, client, linode_region_id, server_firewall_id, vpc_addresses[0], vpc_subnet)

    if linodes:
        agent_firewall_id = network.get_firewall(client, config['settings']['cluster_prefix'] + 'agent_firewall')
        hta.deploy_linodes(config, client, linode_region_id, agent_firewall_id, linode_type_id, linode_amount, vpc_addresses)

    print(f'# All done, it took {int((time.time() - start_time) // 60):>02}:{int(time.time() - start_time) % 60:>02}s')
    print(f'vist https://{config['settings']['domain']}')


def remove(config: dict, client: LinodeClient, no_prompt=False):
    cluster_prefix = config['settings']['cluster_prefix']
    agents = {i.id: i.label for i in client.linode.instances() if cluster_prefix in i.label}
    firewalls = {i.id: i.label for i in client.networking.firewalls() if cluster_prefix in i.label}
    vpc = {i.id: i.label for i in client.vpcs() if cluster_prefix.replace("_", "-") in i.label}

    if len(agents) == 0 and len(firewalls) == 0 and len(vpc) == 0:
        print('# No entities to remove')
        print('# Exiting')
        sys.exit(0)

    if not no_prompt:
        print('# Following entities will be removed:')
        for a in agents:
            print(f' - {agents[a]}')
        for f in firewalls:
            print(f' - {firewalls[f]}')
        for v in vpc:
            print(f' - {vpc[v]}')
        print(f'# Continue?', end=' ')
        misc.confirmation()

    for a in agents:
        print(f'# Removing {agents[a]}...')
        misc.delete_linode(client.token, a)
        print(' - done')

    for f in firewalls:
        print(f'# Removing {firewalls[f]}...')
        network.remove_firewall(client.token, f)
        print(' - done')

    for v in vpc:
        print(f'# Removing {vpc[v]}')
        network.remove_vpc(client, str(v))
        print(' - done')

    print('# Finished')


def remove_only_agents(config: dict, client: LinodeClient):
    cluster_prefix = config['settings']['cluster_prefix']
    agents = {i.id: i.label for i in client.linode.instances() if cluster_prefix + 'agent_' in i.label}
    if len(agents) == 0:
        print('# No agents to remove')
        print('# Exiting')
        sys.exit(0)

    print('# Following entities will be removed:')
    for a in agents:
        print(f' - {agents[a]}')

    print(f'# Continue?', end=' ')
    misc.confirmation()

    for a in agents:
        print(f'# Removing {agents[a]}...')
        misc.delete_linode(client.token, a)
        print(' - done')


def pick_action():
    print('1. Full deploy')
    print('2. Deploy server')
    print('3. Deploy linodes')
    print('4. Clean up')
    print('5. Configure')
    print('6. Remove only agents')
    print('7. Exit')

    while True:
        action = int(input('# Choose an option: '))
        if 1 <= action <= 6:
            print()
            return action


def main():
    config_filename = 'mewa_config.yaml'
    config = conf.get_config(config_filename)
    client = LinodeClient(config['keys']['linode'])

    try:
        action = pick_action()

        if action == 1:
            deploy(config, client, True, True)
        elif action == 4:
            remove(config, client)
        elif action == 2:
            deploy(config, client, True, False)
        elif action == 3:
            deploy(config, client, False, True)
        elif action == 5:
            conf.reconfig(config_filename)
        elif action == 6:
            remove_only_agents(config, client)
        elif action == 7:
            sys.exit(0)
    except KeyboardInterrupt:
        if str(config['settings']['autoclean_when_failed']) == '1':
            print('\n# Interrupted, cleaning up')
            remove(config, client, no_prompt=True)
        print('\n# Exiting')
        sys.exit(0)


if __name__ == '__main__':
    main()
