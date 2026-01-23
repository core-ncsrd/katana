import requests
import json
import yaml
import click
import os

@click.group()
def cli():
    """Manage Proxmox clusters and VMs"""
    pass

@click.command()
def ls():
    """
    List registered Proxmox clusters
    """
    url = "http://localhost:8000/api/proxmox/cluster"
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        
        if not json_data:
            click.echo("No Proxmox clusters registered")
            return
        
        # Print header
        click.echo(f"{'CLUSTER ID':<40} {'NAME':<20} {'URL':<40} {'NODE':<15} {'STATUS':<10}")
        click.echo(f"{'-'*40} {'-'*20} {'-'*40} {'-'*15} {'-'*10}")
        
        # Print each cluster
        for cluster in json_data:
            click.echo(f"{cluster['_id']:<40} {cluster['name']:<20} {cluster['url']:<40} {cluster['node']:<15} {cluster['status']:<10}")
    
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        if r:
            click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)

@click.command()
@click.argument("cluster_id")
def inspect(cluster_id):
    """
    Display detailed information of a Proxmox cluster
    """
    url = f"http://localhost:8000/api/proxmox/cluster/{cluster_id}"
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        click.echo(json.dumps(json_data, indent=2))
        if not json_data:
            click.echo(f"Error: No such cluster: {cluster_id}")
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        if r:
            click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)

@click.command()
@click.option("-f", "--file", required=True, type=str, help="YAML file with Proxmox cluster details")
def register(file):
    """
    Register a new Proxmox cluster
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/proxmox/cluster"
    r = None
    try:
        r = requests.post(url, json=json.loads(json.dumps(data)), timeout=30)
        r.raise_for_status()
        json_data = r.json()
        click.echo("Proxmox cluster registered successfully:")
        click.echo(f"Cluster ID: {json_data['cluster_id']}")
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        if r:
            click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)

@click.command()
@click.argument("cluster_id")
def unregister(cluster_id):
    """
    Unregister a Proxmox cluster
    """
    url = f"http://localhost:8000/api/proxmox/cluster/{cluster_id}"
    r = None
    try:
        r = requests.delete(url, timeout=30)
        r.raise_for_status()
        click.echo(f"Proxmox cluster {cluster_id} unregistered successfully")
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        if r:
            click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)

# Register commands
cli.add_command(ls)
cli.add_command(inspect)
cli.add_command(register)
cli.add_command(unregister)

if __name__ == '__main__':
    cli()
