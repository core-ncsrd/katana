import requests
import json
import yaml

import click
import datetime


@click.group()
def cli():
    """Manage slices"""
    pass


@click.command()
def ls():
    """
    List slices
    """

    url = "http://localhost:8000/api/slice"
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        print(console_formatter("SLICE_ID", "SLICE_NAME", "CREATED AT", "STATUS"))
        for i in range(len(json_data)):
            print(console_formatter(json_data[i]["_id"], json_data[i]["name"], datetime.datetime.fromtimestamp(json_data[i]["created_at"]).strftime("%Y-%m-%d %H:%M:%S"), json_data[i]["status"],))

    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)


@click.command()
@click.argument("uuid")
def inspect(uuid):
    """
    Display detailed information of slice
    """
    url = "http://localhost:8000/api/slice/" + uuid
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        click.echo(json.dumps(json_data, indent=2))
        if not json_data:
            click.echo(f"Error: No such slice: {uuid}")
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)


@click.command()
@click.argument("uuid")
def deployment_time(uuid):
    """
    Display deployment slice of slice
    """
    url = "http://localhost:8000/api/slice/{0}/time".format(uuid)
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        click.echo(json.dumps(json_data, indent=2))
        if not json_data:
            click.echo("Error: No such slice: {}".format(uuid))
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)


@click.command()
@click.argument("uuid")
def errors(uuid):
    """
    Display errors of slice
    """
    url = "http://localhost:8000/api/slice/{0}/errors".format(uuid)
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        click.echo(json.dumps(json_data, indent=2))
        if not json_data:
            click.echo("Error: No such slice: {}".format(uuid))
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)


@click.command()
@click.option("-f", "--file", required=True, type=str, help="yaml file with slice details")
def add(file):
    """
    Add new slice
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/slice"
    r = None
    try:
        r = requests.post(url, json=json.loads(json.dumps(data)), timeout=30)
        r.raise_for_status()

        click.echo(r.content)
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)


@click.command()
@click.argument("id_list", nargs=-1)
@click.option("--force", required=False, default=False, is_flag=True, help="Force delete a slice")
def rm(id_list, force):
    """
    Remove slices
    """
    for _id in id_list:

        force_arg = "?force=true" if force else ""

        url = "http://localhost:8000/api/slice/" + _id + force_arg
        r = None
        try:
            r = requests.delete(url, timeout=30)
            r.raise_for_status()
            click.echo(r.content)
        except requests.exceptions.HTTPError as errh:
            print("Http Error:", errh)
            click.echo(r.content)
        except requests.exceptions.ConnectionError as errc:
            print("Error Connecting:", errc)
        except requests.exceptions.Timeout as errt:
            print("Timeout Error:", errt)
        except requests.exceptions.RequestException as err:
            print("Error:", err)


@click.command()
@click.option("-f", "--file", required=True, type=str, help="yaml file with slice details")
@click.argument("id")
def modify(file, id):
    """
    Update slice
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/slice/" + id + "/modify"
    r = None
    try:
        r = requests.post(url, json=json.loads(json.dumps(data)), timeout=30)
        r.raise_for_status()

        click.echo(r.content)
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        click.echo(r.content)
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Error:", err)


cli.add_command(ls)
cli.add_command(inspect)
cli.add_command(add)
cli.add_command(rm)
cli.add_command(modify)
cli.add_command(deployment_time)
cli.add_command(errors)


def console_formatter(uuid, slice_name, created_at, status):
    return "{0: <40}{1: <25}{2: <25}{3: <20}".format(uuid, slice_name, created_at, status)
