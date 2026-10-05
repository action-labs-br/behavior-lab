# Guided Behavior-Cloning Lessons

Complete the [quick start](quickstart.md) first. Each lesson follows the same scientific loop: **predict, change one variable, observe, reflect**. Save the terminal output and generated `.json` file for each run. Because training is stochastic, compare patterns across repeated runs rather than treating one result as proof.

## 1. States and actions

**Objective:** identify features and labels. Collect at least five episodes, then run `python inspect_data.py DATA.csv`. Before inspecting, predict which action will be common when the blue circle starts left of the target. In the CSV, compare `blue_x` and `target_x` with `action_x`.

**Reflect:** why does an action need both the blue and target positions? What information is absent from the state?

## 2. Dataset size

**Objective:** see how example quantity affects imitation. Save one dataset after about 5 episodes and another after about 50. Predict which will handle new starting positions better. Train both with the same command and seed:

```bash
python train.py FIVE.csv --preset balanced --seed 7 --output-dir data/five
python train.py FIFTY.csv --preset balanced --seed 7 --output-dir data/fifty
```

Compare best validation loss and several gameplay attempts.

**Reflect:** did more rows also mean more varied situations?

## 3. Bias in demonstrations

**Objective:** connect action imbalance to policy behavior. Deliberately collect one dataset in which the target is approached mostly from one direction, and one with varied approaches. Inspect both before training.

**Reflect:** which actions were rare? Where did the biased model fail? Dataset balance means covering useful situations, not forcing every count to be identical.

## 4. Hyperparameters

**Objective:** understand epochs, learning rate, and batch size. Predict the effect of changing exactly one setting, then run two experiments:

```bash
python train.py DATA.csv --preset balanced --epochs 10 --seed 7 --output-dir data/e10
python train.py DATA.csv --preset balanced --epochs 60 --seed 7 --output-dir data/e60
```

Repeat with `--learning-rate` or `--batch-size`. Use a new output directory because identical configurations are not overwritten.

**Reflect:** did more training improve validation loss, or only training loss? A learning rate controls update size; a batch size controls how many examples estimate each update.

## 5. Validation and generalization

**Objective:** distinguish fitting known data from handling unseen episodes. Open an experiment `.json` and find `train_loss`, `validation_loss`, and the episode IDs in each split. The split is by whole episode to prevent adjacent frames from leaking into both sets.

Predict whether the epoch with the smallest training loss also has the smallest validation loss. Then watch the saved best-validation model play.

**Reflect:** why are validation loss and gameplay success different measurements?

## 6. Distribution shift and corrective demonstrations

**Objective:** observe **covariate shift**—small model errors can lead to states the human demonstrations never visited. Watch the model and note a repeatable failure state. Collect a new demonstration that starts similarly and shows recovery, combine or recollect a larger dataset, then retrain with the same settings.

Automated failure replay and dataset merging are planned features; today, keep the original and corrective CSVs separate or merge them carefully with a spreadsheet while preserving the schema and unique episode IDs.

**Reflect:** why can adding a targeted correction help more than repeating an already common path?

## 7. Regression versus nine action classes

**Objective:** compare two ways to represent actions. The implemented policy uses regression: it predicts two continuous numbers and minimizes mean squared error (MSE). This is simple, but averaging conflicting labels can produce a weak or unusual movement.

An optional future model will classify nine combinations: no-op plus the eight cardinal/diagonal directions. Before it is implemented, inspect the action pairs in a CSV and assign each to a class on paper.

**Reflect:** when is continuous regression useful? What does classification gain, and what does it lose? Consider probabilities, class imbalance, and whether speed should vary.
