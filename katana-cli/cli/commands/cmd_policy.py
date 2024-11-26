import requests
import json
import yaml
import click
import datetime


@click.group()
def cli():
    """Manage Policy Engine"""
    pass


@click.command()
def ls():
    """
    List Policy Management Systems
    """

    url = "http://localhost:8000/api/policy"
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        print(console_formatter("DB_ID", "COMPONENT_ID", "TYPE", "CREATED AT"))
        for i in range(len(json_data)):
            print(
                console_formatter(
                    json_data[i]["_id"],
                    json_data[i]["component_id"],
                    json_data[i]["type"],
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
    Display detailed information of Policy Management System
    """
    url = "http://localhost:8000/api/policy/" + id
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        click.echo(json.dumps(json_data, indent=2))
        if not json_data:
            click.echo("Error: No such Policy Management Systems: {}".format(id))
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
@click.option(
    "-f", "--file", required=True, type=str, help="yaml file with Policy Management Systems details"
)
def add(file):
    """
    Add new Policy Management System
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/policy"
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
    Remove Policy Management System
    """
    url = "http://localhost:8000/api/policy/" + id
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
@click.option(
    "-f", "--file", required=True, type=str, help="yaml file with Policy Management Systems details"
)
@click.argument("id")
def update(file, id):
    """
    Update Policy Management Systems
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/policy/" + id
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


def console_formatter(uuid, _id, _type, created_at):
    return "{0: <40}{1: <20}{2: <20}{3: <25}".format(uuid, _id, _type, created_at)
