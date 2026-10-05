# Downsampling Plugins

Training can load trusted preprocessing code from `game/downsamplers/`. A CLI name such as `drop-noop` maps to `drop_noop.py`:

```bash
python game/train.py DATA.csv --downsample drop-noop
python game/train.py --list-downsamplers
```

The episode split happens first. The plugin receives only training rows; validation rows and the raw CSV remain unchanged.

## Contract

Each module exports `DOWNSAMPLER`, an object with a stable name and normalized `apply` method:

```python
from util.downsampling import DownsampleContext, DownsampleResult


class MyDownsampler:
    name = "my-downsampler"

    def apply(self, rows, context: DownsampleContext) -> DownsampleResult:
        kept = list(rows)
        return DownsampleResult(
            rows=kept,
            description="Explain what was retained or removed",
        )


DOWNSAMPLER = MyDownsampler()
```

The returned rows must be a non-empty, ordered subset of the input. The trainer rejects new, modified, or reordered samples. A plugin may remove an entire episode, but the removed episode IDs are reported and stored in experiment metadata.

The context supplies the training seed so randomized plugins can remain reproducible. Metadata also records a SHA-256 hash of the plugin source, ensuring two implementations with the same name produce distinct experiment IDs.

Plugin modules execute Python code when loaded. Only use plugins committed to or intentionally placed in this trusted workspace directory.
