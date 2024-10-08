import sys
import requests


def confirmation():
    while True:
        response = input('[y/n]: ')
        if response.lower() == 'y':
            break
        elif response.lower() == 'n':
            print('# Exiting')
            sys.exit(0)
        else:
            print(end='# ')


def delete_linode(token: str, linode_id: str):
    url = f'https://api.linode.com/v4/linode/instances/{linode_id}'
    headers = {
        'accept': 'application/json',
        'authorization': f'Bearer {token}'
    }

    requests.delete(url, headers=headers)
