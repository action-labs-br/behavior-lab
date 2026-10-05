"""Contracts and loading for trusted workspace downsampling plugins."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from util.data import Demonstration


PLUGIN_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class DownsampleContext:
    seed: int


@dataclass(frozen=True)
class DownsampleResult:
    rows: list[Demonstration]
    description: str


class Downsampler(Protocol):
    name: str

    def apply(
        self,
        rows: Sequence[Demonstration],
        context: DownsampleContext,
    ) -> DownsampleResult: ...


@dataclass(frozen=True)
class LoadedDownsampler:
    name: str
    source_hash: str
    implementation: Downsampler

    def apply(
        self,
        rows: Sequence[Demonstration],
        context: DownsampleContext,
    ) -> DownsampleResult:
        result = self.implementation.apply(rows, context)
        validate_downsample_result(rows, result)
        return result


def plugin_directory() -> Path:
    return Path(__file__).parents[1] / "downsamplers"


def available_downsamplers(directory: str | Path | None = None) -> tuple[str, ...]:
    root = Path(directory) if directory is not None else plugin_directory()
    if not root.is_dir():
        return ()
    return tuple(
        sorted(
            path.stem.replace("_", "-")
            for path in root.glob("*.py")
            if path.name != "__init__.py" and not path.name.startswith("_")
        )
    )


def load_downsampler(
    name: str,
    directory: str | Path | None = None,
) -> LoadedDownsampler:
    normalized = name.lower()
    if not PLUGIN_NAME.fullmatch(normalized):
        raise ValueError(
            "Downsampler names may contain lowercase letters, numbers, and hyphens only"
        )
    root = Path(directory) if directory is not None else plugin_directory()
    source = root / f"{normalized.replace('-', '_')}.py"
    if not source.is_file():
        choices = ", ".join(available_downsamplers(root)) or "none installed"
        raise ValueError(f"Unknown downsampler {name!r}. Available: {choices}")

    spec = importlib.util.spec_from_file_location(
        f"behavior_cloning_downsampler_{normalized.replace('-', '_')}",
        source,
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load downsampler module: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(spec.name, None)
        raise ValueError(f"Could not import downsampler {name!r}: {error}") from error
    implementation = getattr(module, "DOWNSAMPLER", None)
    if implementation is None or not callable(getattr(implementation, "apply", None)):
        raise ValueError(f"Downsampler {name!r} must export DOWNSAMPLER with apply()")
    if getattr(implementation, "name", None) != normalized:
        raise ValueError(
            f"Downsampler {name!r} must declare name = {normalized!r}"
        )
    return LoadedDownsampler(
        name=normalized,
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
        implementation=implementation,
    )


def validate_downsample_result(
    original: Sequence[Demonstration],
    result: DownsampleResult,
) -> None:
    if not isinstance(result, DownsampleResult):
        raise ValueError("Downsampler apply() must return DownsampleResult")
    if not result.rows:
        raise ValueError("Downsampling removed every training row")
    if not isinstance(result.description, str) or not result.description.strip():
        raise ValueError("Downsampler must provide a non-empty description")

    original_iterator = iter(original)
    for candidate in result.rows:
        for source in original_iterator:
            if candidate == source:
                break
        else:
            raise ValueError(
                "Downsampler output must be an ordered subset of its input rows"
            )
