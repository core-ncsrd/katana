""" Katana Command Line Tool """

import os
import click

cmd_folder = os.path.join(os.path.dirname(__file__), "commands")
cmd_prefix = "cmd_"


class CLI(click.MultiCommand):
    def list_commands(self, ctx):
        """
        Obtain a list of all available commands.

        :param ctx: Click context
        :return: List of sorted commands
        """
        commands = []

        for filename in os.listdir(cmd_folder):
            if filename.endswith(".py") and filename.startswith(cmd_prefix):
                commands.append(filename[4:-3])

        commands.sort()

        return commands

    def get_command(self, ctx, name):
        """
        Get a specific command by looking up the module.

        :param ctx: Click context
        :param name: Command name
        :return: Module's cli function
        """
        ns = {}

        filename = os.path.join(cmd_folder, cmd_prefix + name + ".py")

        try:
            f = open(filename)
        except FileNotFoundError:
            raise click.ClickException(
                f"Wrong command: {name} \nAvailable commands: {self.list_commands(ctx)}"
            )
        with f:
            code = compile(f.read(), filename, "exec")
            eval(code, ns, ns)

        return ns["cli"]


@click.command(cls=CLI)
def cli():
    """
    katana-cli is a command-line tool that interacts with the katana
    slice manager
    """
    pass
