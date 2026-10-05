from pathlib import Path
from unittest.mock import Mock, patch

from behavior_cloning_game import cli


def test_project_directory_is_independent_of_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert (cli.project_directory() / "train.py").is_file()


def test_dispatch_uses_active_python_and_game_directory():
    completed = Mock(returncode=7)
    with patch("behavior_cloning_game.cli.subprocess.run", return_value=completed) as run:
        result = cli.run_workflow("inspect", ["example.csv"])

    assert result == 7
    command = run.call_args.args[0]
    assert command[0] == cli.sys.executable
    assert Path(command[1]).name == "inspect_data.py"
    assert command[2:] == [str(Path("example.csv").resolve())]
    assert run.call_args.kwargs["cwd"] == cli.project_directory()
    assert run.call_args.kwargs["check"] is False


def test_subcommand_forwards_arguments():
    with patch("behavior_cloning_game.cli.run_workflow", return_value=0) as run:
        assert cli.main(["train", "dataset.csv", "--", "--epochs", "2"]) == 0
    run.assert_called_once_with("train", ["dataset.csv", "--epochs", "2"])


def test_menu_can_exit(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "5")
    assert cli.interactive_menu() == 0


def test_menu_collects_training_preset(monkeypatch):
    answers = iter(["3", "dataset.csv", "quick", "5"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    with patch("behavior_cloning_game.cli.run_workflow", return_value=0) as run:
        assert cli.interactive_menu() == 0
    run.assert_called_once_with("train", ["dataset.csv", "--preset", "quick"])


def test_menu_collects_evaluation_episode_count(monkeypatch):
    answers = iter(["4", "model.json", "12", "5"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    with patch("behavior_cloning_game.cli.run_workflow", return_value=0) as run:
        assert cli.interactive_menu() == 0
    run.assert_called_once_with("evaluate", ["model.json", "--episodes", "12"])


def test_text_flag_opens_terminal_menu():
    with patch("behavior_cloning_game.cli.interactive_menu", return_value=0) as menu:
        assert cli.main(["--text"]) == 0
    menu.assert_called_once_with()


def test_no_command_opens_graphical_launcher():
    with patch("behavior_cloning_game.ui.launch", return_value=0) as launch:
        assert cli.main([]) == 0
    launch.assert_called_once_with(cli.run_workflow, cli.project_directory() / "data")
