"""GET /api/models/performance — how accurate the climate-estimate models are."""

from fastapi import APIRouter

from app.models.schemas import ErrorResponse
from app.services import model_store

router = APIRouter(prefix="/models", tags=["models"])


@router.get(
    "/performance",
    responses={503: {"model": ErrorResponse}},
    summary="Validation and test metrics for each forecasting model",
)
def model_performance():
    """
    MAE / RMSE (°C) for daily highs and lows and the Brier score for wet days, on the
    validation years (used to pick the model) and the held-out test years, for every
    model. Also: which model was selected, 80%-range coverage, and per-park / per-month
    test errors of the selected model. Written by `python -m scripts.train_models`.
    """
    return model_store.get_metrics()
