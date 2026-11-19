"""
Loads the trained climate model and its metrics from trained_models/.

Both are cached in memory and reloaded automatically when the file on disk changes,
so re-running scripts.train_models takes effect without restarting the API.
"""

import json
import logging
from pathlib import Path

import joblib
import sklearn

from app.config import get_settings
from app.services.errors import ModelNotReadyError

BUNDLE_FILE = "climate_model.joblib"
METRICS_FILE = "metrics.json"

_cache: dict[Path, tuple[float, object]] = {}
logger = logging.getLogger("parkwise.models")


def _load_bundle(path: Path) -> dict:
    bundle = joblib.load(path)
    trained_with = bundle.get("sklearn_version")
    if trained_with and trained_with != sklearn.__version__:
        # Pickled models aren't guaranteed to work across versions. Predictions may still
        # run, but retrain (or pin the version in requirements.txt) to be safe.
        logger.warning("Model was trained with scikit-learn %s but %s is installed.",
                       trained_with, sklearn.__version__)
    return bundle


def _load(path: Path, loader):
    if not path.exists():
        raise ModelNotReadyError(
            "The climate model hasn't been trained yet. From backend/, run "
            "`python -m scripts.train_models`."
        )
    mtime = path.stat().st_mtime
    cached = _cache.get(path)
    if cached is None or cached[0] != mtime:
        _cache[path] = (mtime, loader(path))
    return _cache[path][1]


def get_bundle() -> dict:
    return _load(get_settings().model_dir / BUNDLE_FILE, _load_bundle)


def get_metrics() -> dict:
    return _load(get_settings().model_dir / METRICS_FILE, lambda p: json.loads(p.read_text(encoding="utf-8")))
