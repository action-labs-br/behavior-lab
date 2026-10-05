"""Remove stationary action labels from the training partition."""

from util.downsampling import DownsampleContext, DownsampleResult


class DropNoOp:
    name = "drop-noop"

    def apply(self, rows, context: DownsampleContext) -> DownsampleResult:
        kept = [row for row in rows if row.action.x != 0 or row.action.y != 0]
        removed = len(rows) - len(kept)
        return DownsampleResult(
            rows=kept,
            description=f"Removed {removed} no-op training sample(s)",
        )


DOWNSAMPLER = DropNoOp()
