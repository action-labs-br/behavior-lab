# Instructor Guide

## Learning outcomes

After the sequence, learners should be able to explain:

- a state (features) and expert action (label);
- behavior cloning as supervised imitation;
- training loss, validation loss, and gameplay success as different signals;
- how dataset size, coverage, and bias affect generalization;
- why distribution shift causes compounding errors;
- how epochs, learning rate, and batch size change training.

The game intentionally uses only four input features and two output values. Keep attention on the learning loop rather than neural-network depth.

## Suggested class format

Use one 60–90 minute session for setup, collection, inspection, and first training. Use a second for controlled experiments and corrective demonstrations. Pair learners: one plays while the other predicts and records observations, then swap.

For each lesson in [lessons.md](lessons.md), require a prediction before running the command, one controlled change, saved artifact metadata, and a short reflection. Assign different seeds or datasets across groups, then compare outcomes. Emphasize that a single stochastic run is evidence, not a general conclusion.

## Preparation

Before class:

1. Test the setup on the classroom operating systems and network.
2. Preinstall dependencies if PyTorch downloads would consume class time.
3. From `projects/behavior-cloning-game/`, run `cd game && venv/bin/python -m unittest discover -s tests -v` on macOS/Linux, or use `venv\Scripts\python` on Windows.
4. Keep a known-working CSV and checkpoint as recovery fixtures.
5. Decide where learners will store generated CSV, `.pth`, and `.json` files; these can be large and should not normally be committed.

## Facilitation prompts

Ask learners to point from a game frame to one CSV row, then from its feature columns through the network to its action columns. When a policy fails, ask whether the problem is optimization, missing data coverage, ambiguous labels, or evaluation noise. Avoid describing lower loss as “understanding.” The policy learns a numerical mapping from observed examples.

## Assessment and common issues

A strong learner explanation connects a failure to evidence in inspection output and proposes a controlled next experiment. Common issues include using too few complete episodes, collecting nearly identical paths, comparing runs with several changed settings, and evaluating from only one random start.

The current evaluator is finite and seeded, so learners can compare the same scenarios using saved JSON results. The unified command-line menu is also available. Comparison charts, a graphical menu, automated corrective-demo capture, and the nine-class classifier remain planned extensions.
