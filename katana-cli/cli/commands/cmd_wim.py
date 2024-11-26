import requests
import json
import yaml
import click
import datetime


@click.group()
def cli():
    """Manage WIM"""
    pass


@click.command()
def ls():
    """
    List WIMs
    """

    url = "http://localhost:8000/api/wim"
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        print(console_formatter("DB_ID", "WIM_ID", "WIM_TYPE", "CREATED AT"))
        for i in range(len(json_data)):
            print(
                console_formatter(
                    json_data[i]["_id"],
                    json_data[i]["wim_id"],
                    json_data[i]["wim_type"],
                    datetime.datetime.fromtimestamp(json_data[i]["created_at"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                )
            )

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
@click.argument("id")
def inspect(id):
    """
    Display detailed information of WIM
    """
    url = "http://localhost:8000/api/wim/" + id
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        # indent=2 "beautifies" json
        click.echo(json.dumps(json_data, indent=2))
        if not json_data:
            click.echo("Error: No such WIM: {}".format(id))
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
@click.option("-f", "--file", required=True, type=str, help="yaml file with wim details")
def add(file):
    """
    Add new WIM
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/wim"
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
@click.argument("id")
def rm(id):
    """
    Remove supported WIM
    """
    url = "http://localhost:8000/api/wim/" + id
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
@click.option("-f", "--file", required=True, type=str, help="yaml file with WIM details")
@click.argument("id")
def update(file, id):
    """
    Update WIM
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/wim/" + id
    r = None
    try:
        r = requests.put(url, json=json.loads(json.dumps(data)), timeout=30)
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
cli.add_command(update)


def console_formatter(uuid, _id, wim_type, created_at):
    return "{0: <40}{1: <20}{2: <20}{3: <25}".format(uuid, _id, wim_type, created_at)
