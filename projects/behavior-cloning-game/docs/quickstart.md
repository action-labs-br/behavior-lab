# Five-Minute Learner Quick Start

This project teaches **behavior cloning**: record how a person moves the blue circle into the white, black-bordered target, then train a neural network to imitate those actions.

## 1. Set up

From the Behavior Cloning Game project root (Python 3.11–3.13):

```bash
python3 -m venv venv
```

Activate the environment:

- macOS/Linux: `source venv/bin/activate`
- Windows PowerShell: `venv\Scripts\Activate.ps1`
- Windows Command Prompt: `venv\Scripts\activate.bat`

Then install dependencies:

```bash
python -m pip install -e .
```

## 2. Open the learning lab

```bash
python -m behavior_cloning_game
```

The graphical launcher opens. Choose **Collect**, then create a new dataset or append
to an existing compatible dataset. Use the arrow keys to move the blue circle fully
inside the outlined white square. Complete several episodes and press Escape when
finished. The launcher returns when collection is complete.

If a graphical launcher is unavailable, use `python -m behavior_cloning_game --text` for the terminal menu.

## 3. Inspect what the model will learn from

Choose **Inspect a dataset** and paste the path printed in the previous step. The equivalent direct command is:

```bash
python -m behavior_cloning_game inspect game/data/demonstrations_YYYYMMDD_HHMMSS.csv
```

Look for the four state features (`blue_x`, `blue_y`, `target_x`, `target_y`) and the two action labels (`action_x`, `action_y`). Check whether one movement direction dominates.

To collect more examples later, choose **Collect → Append to an existing dataset** in
the launcher. The equivalent direct command is:

```bash
python game/play.py --dataset game/data/demonstrations_YYYYMMDD_HHMMSS.csv
```

Episode numbering continues from the highest existing episode. The command validates the schema before opening the game.

## 4. Train

Choose **Train a model**, select the dataset, and review the training configuration.
The Balanced preset is selected initially. You can change the feature representation,
drop no-op actions from the training partition, or edit individual hyperparameters
before starting. For a faster direct run with explicit options, use
`python -m behavior_cloning_game train game/data/FILE.csv -- --preset quick`.

Training reserves whole episodes for validation and saves both model weights (`.pth`) and experiment details (`.json`). Try `--preset balanced` when you have more demonstrations.

If inspection reports many `(0, 0)` actions, compare a second experiment that removes them from the training partition:

```bash
python -m behavior_cloning_game train game/data/FILE.csv -- --downsample drop-noop
```

The original CSV and validation rows remain unchanged, making the comparison reproducible.

You can also compare state representations without changing the CSV:

```bash
python -m behavior_cloning_game train game/data/FILE.csv -- --features relative-center
python -m behavior_cloning_game train game/data/FILE.csv -- --features relative-containment
```

When using relative features, evaluate the generated `.json` file so inference restores the correct transformation.

## 5. Evaluate the policy

Choose **Evaluate a model** and enter the `.json` experiment path printed by training. Choose how many attempts to watch. The game window shows the learned policy moving the blue circle:

```bash
python -m behavior_cloning_game evaluate game/data/model_RUN_ID.json -- --episodes 20
```

For reproducible metrics without opening the window, add `--headless`. Compare the success count, success rate, successful-step average, and failure reasons. A low validation loss does not guarantee successful play: the model may encounter states missing from your demonstrations.
