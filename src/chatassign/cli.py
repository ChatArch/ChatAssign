"""CLI entrypoint for chatassign."""

from __future__ import annotations

import click
from chatstyle import add_tree_option

from chatassign import __version__


@click.group(name="chatassign", invoke_without_command=True, no_args_is_help=True)
@click.version_option(__version__, prog_name="chatassign")
@add_tree_option(renderer_options={"root_name": "chatassign"})
def main() -> None:
    """ChatAssign assignment control-plane CLI."""
    pass


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host interface for the service.")
@click.option("--port", default=8765, show_default=True, type=int, help="TCP port for the service.")
@click.option(
    "--home",
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    default=None,
    help="Override ChatAssign data root for this process.",
)
def serve(host: str, port: int, home: str | None) -> None:
    """Start the ChatAssign HTTP service."""

    from pathlib import Path

    from chatassign.server import Handler, build_server

    server = build_server(host, port, Path(home).expanduser() if home else None)
    click.echo(f"ChatAssign serving http://{host}:{port}")
    click.echo(f"Data root: {Handler.store.home}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
