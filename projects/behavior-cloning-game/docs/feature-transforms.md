# State Feature Transforms

Select a representation during training:

```bash
python game/train.py DATA.csv --features absolute
python game/train.py DATA.csv --features relative-center
python game/train.py DATA.csv --features relative-containment
```

Transforms run after the episode split and before normalization. They never modify the demonstration CSV. Their name and output feature names are stored in experiment metadata and restored during visible or headless evaluation.

## Absolute

`absolute` is backward-compatible and supplies four values:

```text
blue_x, blue_y, target_x, target_y
```

The network must learn how the two positions relate.

## Relative center

`relative-center` supplies the normalized displacement between the circle and target centers:

```text
(target_center_x - circle_center_x) / screen_width
(target_center_y - circle_center_y) / screen_height
```

Equivalent arrangements in different screen locations produce the same features, which can improve generalization.

## Relative containment

`relative-containment` supplies normalized movement to the nearest position where the circle's bounding box fits inside the target. Each axis becomes zero anywhere within its valid 20-pixel interval.

This representation encodes more knowledge of the task and gives the model an explicit stopping region.

## Comparing experiments

Keep dataset, split seed, network, and training settings identical while changing only `--features`. Compare validation loss and seeded gameplay success. Because the two relative representations both produce two inputs, their `.pth` files are ambiguous by themselves; always execute their paired `.json` experiment files.
