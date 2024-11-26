import requests
import json
import click


@click.group()
def cli():
    """Query added GSTs"""
    pass


@click.command()
def ls():
    """
    List GSTs
    """
    url = "http://localhost:8000/api/gst"
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        print(console_formatter("GST_ID"))
        for i in range(len(json_data)):
            print(console_formatter(json_data[i]["_id"]))
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
    Display detailed information of GST
    """
    url = "http://localhost:8000/api/gst/" + id
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        json_data = json.loads(r.content)
        click.echo(json.dumps(json_data, indent=2))
        if not json_data:
            click.echo("Error: No such GST: {}".format(id))
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


def console_formatter(uuid):
    return "{0: <40}".format(uuid)
