import requests
import json
import yaml
import os
import click
import datetime


@click.group()
def cli():
    """Manage K8s clusters"""
    pass


@click.command()
def ls():
    """
    List Kubernetes clusters
    """
    url = "http://localhost:8000/api/k8s"
    r = None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        # Decode and parse JSON data
        try:
            json_data = json.loads(r.content.decode('utf-8', errors='replace'))
        except json.JSONDecodeError:
            click.echo("Error: API response is not valid JSON.")
            click.echo(r.content)
            return

        # Display clusters
        if isinstance(json_data, list) and json_data:
            click.echo(console_formatter("DB_ID", "NAME", "VIM_ACCOUNT", "CREATED AT"))
            for cluster in json_data:
                click.echo(
                    console_formatter(
                        cluster["_id"],
                        cluster["name"],
                        cluster["vim_account"],
                        datetime.datetime.fromtimestamp(cluster["created_at"]).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    )
                )
        else:
            click.echo("No clusters found.")

    except requests.exceptions.RequestException as err:
        click.echo(f"Error: {err}")
        if r is not None:
            click.echo(r.content)

@click.command()
@click.option("-f", "--file", required=True, type=str, help="YAML file with K8s cluster data")
def add(file):
    """
    Add a new Kubernetes cluster
    """
    try:
        with open(file, mode="r") as stream:
            data = yaml.safe_load(stream)

        url = "http://localhost:8000/api/k8s"
        r = None
        try:
            r = requests.post(url, json=json.loads(json.dumps(data)), timeout=30)
            r.raise_for_status()
            click.echo(r.content.decode("utf-8"))
        except requests.exceptions.HTTPError as errh:
            click.echo(f"HTTP Error: {errh.response.content.decode('utf-8')}", err=True)
        except requests.exceptions.RequestException as err:
            click.echo(f"Request Error: {err}", err=True)

    except FileNotFoundError as e:
        raise click.ClickException(f"File not found: {e.filename}")
    except yaml.YAMLError as e:
        raise click.ClickException(f"Error parsing file: {e}")


@click.command()
@click.option("-f", "--file", required=True, type=str, help="Path to the YAML file with K8s credentials")
def uploadCreds(file):
    """
    Upload Kubernetes credentials file
    """
    try:
        # Verify that the file exists
        if not os.path.exists(file):
            raise click.ClickException(f"File {file} not found")

        # Prepare the API URL
        url = "http://localhost:8000/api/k8s"

        # Upload the file as multipart/form-data
        with open(file, "rb") as creds_file:
            files = {"file": (os.path.basename(file), creds_file, "application/x-yaml")}
            r = requests.post(url, files=files, timeout=30)
            r.raise_for_status()
            click.echo(r.content.decode("utf-8"))

    except requests.exceptions.HTTPError as errh:
        click.echo(f"HTTP Error: {errh.response.content.decode('utf-8')}", err=True)
    except requests.exceptions.RequestException as err:
        click.echo(f"Request Error: {err}", err=True)
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")



@click.command()
@click.argument("id")
def rm(id):
    """
    Remove Kubernetes cluster
    """
    url = f"http://localhost:8000/api/k8s/{id}"
    r = None
    try:
        r = requests.delete(url, timeout=30)
        r.raise_for_status()
        click.echo(r.content.decode("utf-8"))
    except requests.exceptions.HTTPError as errh:
        click.echo(f"HTTP Error: {errh.response.content.decode('utf-8')}", err=True)
    except requests.exceptions.RequestException as err:
        click.echo(f"Request Error: {err}", err=True)


cli.add_command(ls)
cli.add_command(add)
cli.add_command(uploadCreds)
cli.add_command(rm)


def console_formatter(uuid, name, vim_account, created_at):
    return "{0: <40}{1: <20}{2: <20}{3: <25}".format(uuid, name, vim_account, created_at)
