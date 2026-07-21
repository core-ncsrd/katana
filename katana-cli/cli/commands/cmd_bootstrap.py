import requests
import json
import os
import yaml
import click


def load_bootstrap_data(filename):
    """Load a manifest and replace credential file references for transport."""
    try:
        with open(filename, mode="r") as stream:
            data = yaml.safe_load(stream)
    except FileNotFoundError:
        raise click.ClickException(f"File {filename} not found")
    except yaml.YAMLError as exc:
        raise click.ClickException(f"Unable to parse bootstrap manifest: {exc}")
    if not isinstance(data, dict):
        raise click.ClickException("Bootstrap manifest must contain a YAML object")
    base = os.path.dirname(os.path.realpath(filename))
    for kind in ("nfvos", "vims"):
        entries = data.get(kind, [])
        if not isinstance(entries, list):
            raise click.ClickException(f"Bootstrap field {kind} must be an array")
        for entry in entries:
            if not isinstance(entry, dict):
                raise click.ClickException(f"Every {kind[:-1]} entry must be an object")
            reference = entry.pop("credentials_file", None)
            if not reference:
                raise click.ClickException(f"{kind[:-1]} {entry.get('id')} requires credentials_file")
            path = os.path.realpath(os.path.join(base, reference))
            if os.path.commonpath((base, path)) != base:
                raise click.ClickException("Credential paths must remain inside the manifest directory")
            try:
                with open(path, mode="r") as stream:
                    entry["credentials"] = yaml.safe_load(stream)
            except FileNotFoundError:
                raise click.ClickException(f"Credentials file {reference} not found")
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    f"Unable to parse credentials file {reference}: {exc}"
                ) from exc
            credentials = entry.get("credentials") or {}
            if not isinstance(credentials, dict):
                raise click.ClickException(
                    f"Credentials file {reference} must contain a YAML object"
                )
            if kind == "vims" and credentials.get("clouds"):
                cloud_name = entry.get("cloud") or next(iter(credentials["clouds"]))
                cloud = credentials["clouds"].get(cloud_name, {})
                if cloud.get("cacert"):
                    local_ca = os.path.realpath(
                        os.path.join(os.path.dirname(path), cloud["cacert"])
                    )
                    if os.path.commonpath((base, local_ca)) != base or not os.path.isfile(local_ca):
                        raise click.ClickException(f"CA file {cloud['cacert']} not found")
                    cloud["cacert"] = "/bootstrap/" + os.path.relpath(local_ca, base)
            if entry.get("ca_file"):
                ca_path = os.path.realpath(os.path.join(base, entry["ca_file"]))
                if os.path.commonpath((base, ca_path)) != base or not os.path.isfile(ca_path):
                    raise click.ClickException(f"CA file {entry['ca_file']} not found")
                entry["ca_file"] = "/bootstrap/" + os.path.relpath(ca_path, base)
    return data


@click.command()
@click.option("-f", "--file", required=True, type=str, help="file with config details")
def cli(file):
    """Bootstrap Katana"""
    data = load_bootstrap_data(file)

    url = "http://localhost:8000/api/bootstrap"
    r = None
    try:
        r = requests.post(url, json=json.loads(json.dumps(data)), timeout=600)
        r.raise_for_status()

        click.echo(r.content)
    except requests.exceptions.HTTPError as errh:
        detail = r.text if r is not None else str(errh)
        raise click.ClickException(detail) from errh
    except requests.exceptions.ConnectionError as errc:
        raise click.ClickException(f"Error connecting: {errc}") from errc
    except requests.exceptions.Timeout as errt:
        raise click.ClickException(f"Bootstrap timed out: {errt}") from errt
    except requests.exceptions.RequestException as err:
        raise click.ClickException(str(err)) from err
