import requests
import json
import yaml
import click
import datetime


@click.group()
def cli():
    """Manage supported Network Functions"""
    pass


@click.command()
def ls():
    """
    List supported Network Functions
    """

    url = "http://localhost:8000/api/function"
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        print(console_formatter("DB_ID", "FUNC_ID", "GEN", "FUNC", "TYPE", "LOCATION", "CREATED AT"))
        for i in range(len(json_data)):
            print(
                console_formatter(
                    json_data[i]["_id"],
                    json_data[i]["func_id"],
                    json_data[i]["gen"],
                    json_data[i]["func"],
                    json_data[i]["type"],
                    json_data[i]["loc"],
                    datetime.datetime.fromtimestamp(json_data[i]["created_at"]).strftime("%Y-%m-%d %H:%M:%S"),
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
    Display detailed information of supported Network Function
    """
    url = "http://localhost:8000/api/function/" + id
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        # indent=2 "beautifies" json
        click.echo(json.dumps(json_data, indent=2))
        if not json_data:
            click.echo(f"Error: No such service: {id}")
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
@click.option("-f", "--file", required=True, type=str, help="yaml file with Network Function details")
def add(file):
    """
    Add new supported Network Function
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/function"
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
    Remove supported Network Function
    """
    url = "http://localhost:8000/api/function/" + id
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
@click.option("-f", "--file", required=True, type=str, help="yaml file with Network Function details")
@click.argument("id")
def update(file, id):
    """
    Update Network Function
    """
    try:
        stream = open(file, mode="r")
    except FileNotFoundError:
        raise click.ClickException(f"File {file} not found")

    with stream:
        data = yaml.safe_load(stream)

    url = "http://localhost:8000/api/function/" + id
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


def console_formatter(uuid, func_id, gen, func, _type, loc, created_at):
    return "{0: <40}{1: <30}{2: <10}{3: <10}{4: <10}{5: <10}{6: <25}".format(uuid, func_id, gen, func, _type, loc, created_at)
