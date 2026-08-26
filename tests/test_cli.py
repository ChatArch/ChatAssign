from click.testing import CliRunner

from chatassign import __version__
from chatassign.cli import main


def test_version_option_reports_package_version():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert f"chatassign, version {__version__}" in result.output


def test_help_lists_shared_tree_options():
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "--tree" in result.output
    assert "--tree-brief" in result.output
    assert "serve" in result.output


def test_tree_option_prints_registered_cli_tree():
    result = CliRunner().invoke(main, ["--tree"])

    assert result.exit_code == 0, result.output
    assert result.output.startswith("chatassign\n")
    assert "├── --help" in result.output
    assert "├── --version" in result.output
    assert "├── --tree" in result.output
    assert "├── --tree-brief" in result.output
    assert "└── serve" in result.output


def test_tree_brief_option_prints_registered_cli_tree():
    result = CliRunner().invoke(main, ["--tree-brief"])

    assert result.exit_code == 0, result.output
    assert result.output.startswith("chatassign\n")
    assert "├── --tree" in result.output
    assert "├── --tree-brief" in result.output
    assert "└── serve" in result.output


def test_serve_help_lists_service_options():
    result = CliRunner().invoke(main, ["serve", "--help"])

    assert result.exit_code == 0, result.output
    assert "Start the ChatAssign HTTP service" in result.output
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--home" in result.output
