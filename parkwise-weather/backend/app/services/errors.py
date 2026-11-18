"""
Domain errors. Services raise these; app/main.py turns them into JSON error responses.

This keeps services free of HTTP concepts, so they work the same when called
from a script, a notebook, or a teammate's code.
"""


class ParkWiseError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: object | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(ParkWiseError):
    status_code = 404
    code = "not_found"


class InvalidRequestError(ParkWiseError):
    status_code = 400
    code = "invalid_request"


class ModelNotReadyError(ParkWiseError):
    """No trained model (or no history for this park in it) yet: an operator needs to run training."""

    status_code = 503
    code = "model_not_ready"

