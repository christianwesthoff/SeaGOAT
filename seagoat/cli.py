import os
import sys
from pathlib import Path

import click
import orjson
import requests
from halo import Halo

from seagoat import __version__
from seagoat.query_service import (
    remove_results_from_unavailable_files,
    search_repo,
)
from seagoat.utils.cli_display import display_results
from seagoat.utils.config import get_config_values
from seagoat.utils.generative import enhance_results
from seagoat.utils.server import ServerDoesNotExist, get_server_info


class ExitCode:
    SERVER_NOT_RUNNING = 3
    SERVER_ERROR = 4


def warn_if_update_available():
    response = requests.get("https://pypi.org/pypi/seagoat/json")
    latest_version = orjson.loads(response.text)["info"]["version"]
    if latest_version != __version__:
        click.echo(
            f"Warning: An updated version {latest_version} of SeaGOAT is available. You have {__version__}.",
            err=True,
        )


def display_accuracy_warning(server_address):
    response = requests.get(
        f"{server_address}/status",
    )
    response_data = orjson.loads(response.text)
    accuracy = response_data["stats"]["accuracy"]["percentage"]

    if accuracy < 100:
        click.echo(
            click.style(
                "Warning: SeaGOAT is still analyzing your repository. "
                + f"The results displayed have an estimated accuracy of {accuracy}%",
                fg="red",
            ),
            err=True,
        )


def query_server(
    query, repo_path, server_address, max_results, context_above, context_below
):
    try:
        response_data = search_repo(
            query=query,
            repo_path=repo_path,
            max_results=max_results,
            context_above=context_above,
            context_below=context_below,
            server_address=server_address,
        )
    except RuntimeError as error:
        click.echo(str(error), err=True)
        sys.exit(ExitCode.SERVER_ERROR)

    return response_data["results"]


SEARCH_HELP = """
Query your codebase for your QUERY in the Git repository REPO_PATH.
Your query can contain keywords, regular expression patterns,
or a description of what you are looking for.

When REPO_PATH is not specified, the current working directory is
assumed to be the repository path.

In order to use seagoat in your repository, you need to run a server
that will analyze your codebase. Check seagoat-server --help for more details.
""".strip()

MCP_SERVER_HELP = "Run the SeaGOAT MCP server."


class SeaGOATGroup(click.Group):
    def resolve_command(self, ctx, args):
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            return super().resolve_command(ctx, ["search", *args])

        return super().resolve_command(ctx, args)

    def format_usage(self, ctx, formatter):
        formatter.write_usage(ctx.command_path, "[OPTIONS] QUERY [REPO_PATH]")

    def format_help_text(self, ctx, formatter):
        if self.help:
            formatter.write_paragraph()
            formatter.write_text(self.help)

    def format_options(self, ctx, formatter):
        search_command = self.get_command(ctx, "search")
        search_params = list(search_command.get_params(ctx))
        version_param = next(
            (
                param
                for param in self.get_params(ctx)
                if getattr(param, "name", None) == "version"
            ),
            None,
        )

        if version_param is not None:
            search_params = [version_param, *search_params]

        rows = []
        for param in search_params:
            help_record = param.get_help_record(ctx)
            if help_record is not None:
                rows.append(help_record)

        if rows:
            with formatter.section("Options"):
                formatter.write_dl(rows)

    def format_commands(self, ctx, formatter):
        command = self.get_command(ctx, "mcp-server")
        if command is None or command.hidden:
            return

        with formatter.section("Additional commands"):
            formatter.write_dl([("mcp-server", command.get_short_help_str())])

    def get_help(self, ctx):
        formatter = ctx.make_formatter()
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_commands(ctx, formatter)
        return formatter.getvalue().rstrip() + "\n"


@click.group(name="seagoat", cls=SeaGOATGroup, help=SEARCH_HELP)
@click.version_option(version=__version__, prog_name="seagoat")
def cli():
    pass


def run_search_command(
    query,
    repo_path,
    no_color,
    max_results,
    context_above,
    context_below,
    context,
    vimgrep,
    reverse: bool,
    generative: bool,
):
    exit_code = 0
    color_enabled = False

    config = get_config_values(Path(repo_path))
    spinner = Halo(text="Generating response...", spinner="dots", stream=sys.stderr)
    spinner.start()

    try:
        if config["client"]["host"] is None:
            server_info = get_server_info(repo_path)
            server_address = server_info["address"]
        else:
            server_address = config["client"]["host"]

        if context is not None:
            context_above = context
            context_below = context

        results = query_server(
            query,
            repo_path,
            server_address,
            max_results,
            context_above if context_above is not None else 3,
            context_below if context_below is not None else 3,
        )

        results = remove_results_from_unavailable_files(results)
        if reverse or generative:
            results = reversed(results)

        if generative:
            if reverse:
                click.echo("--reverse has no effect when using --generative", err=True)

            results = enhance_results(query, results, spinner)

        spinner.succeed()
        color_enabled = os.isatty(0) and not no_color and not vimgrep

        display_results(results, max_results, color_enabled, vimgrep)

        display_accuracy_warning(server_address)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.RequestException,
        ServerDoesNotExist,
    ):
        spinner.fail()
        click.echo(
            f"The SeaGOAT server is not running. "
            f"Please start the server using the following command: "
            f"seagoat-server start {repo_path}",
            err=True,
        )
        exit_code = ExitCode.SERVER_NOT_RUNNING
    finally:
        if exit_code == 0:
            try:
                warn_if_update_available()
            except requests.exceptions.ConnectionError:
                click.echo(
                    "Could not check for updates because the pypi.org API is not accessible",
                    err=True,
                )

    return exit_code


@cli.command(name="search", help=SEARCH_HELP)
@click.argument("query")
@click.argument("repo_path", required=False, default=os.getcwd())
@click.option(
    "--no-color",
    is_flag=True,
    help="Disable formatting. Automatically enabled when part of a bash pipeline.",
)
@click.option(
    "--vimgrep",
    is_flag=True,
    help="Use a vimgrep compatible output format.",
)
@click.option(
    "-l",
    "--max-results",
    type=int,
    default=None,
    help="Limit the number of result lines",
)
@click.option(
    "-B",
    "--context-above",
    type=int,
    default=None,
    help="Include this many lines of context before each result",
)
@click.option(
    "-A",
    "--context-below",
    type=int,
    default=None,
    help="Include this many lines of context after each result",
)
@click.option(
    "-C",
    "--context",
    type=int,
    default=None,
    help="Include this many lines of context after and before each result",
)
@click.option(
    "-r",
    "--reverse",
    is_flag=True,
    default=False,
    help="Display results in the opposite order, with the most relevant at the bottom.",
)
@click.option(
    "-g",
    "--generative",
    is_flag=True,
    default=False,
    help="Use a generative model to enhance results",
)
def search(
    query,
    repo_path,
    no_color,
    max_results,
    context_above,
    context_below,
    context,
    vimgrep,
    reverse: bool,
    generative: bool,
):
    raise SystemExit(
        run_search_command(
            query,
            repo_path,
            no_color,
            max_results,
            context_above,
            context_below,
            context,
            vimgrep,
            reverse,
            generative,
        )
    )


@cli.command(name="mcp-server", help=MCP_SERVER_HELP)
def mcp_server():
    try:
        from seagoat.mcp_server import main
    except ModuleNotFoundError as error:
        if error.name != "seagoat.mcp_server":
            raise

        click.echo(
            "MCP server support is not available in this build yet. "
            "It will be added in a later task.",
            err=True,
        )
        raise SystemExit(1)

    raise SystemExit(main())


seagoat = cli


if __name__ == "__main__":
    cli()
