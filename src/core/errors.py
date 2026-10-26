from __future__ import annotations


class VisionCraftError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 500, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


class AllInferenceProvidersFailedError(VisionCraftError):
    """Raised when every configured inference backend has failed."""

    def __init__(self, failures: dict[str, str]):
        self.failures = dict(failures)
        detail = "; ".join(f"{name}: {reason}" for name, reason in failures.items())
        super().__init__("MODEL_UNAVAILABLE", f"All inference providers failed. {detail}", 503, True)


# code -> (http_status, retryable)  (SPEC section 9)
ERROR_TABLE: dict[str, tuple[int, bool]] = {
    "ACCESS_DENIED": (401, False),
    "AUTH_MISSING": (503, False),
    "AUTH_FAILED": (502, False),
    "CREDITS_EXHAUSTED": (402, False),
    "RATE_LIMITED": (429, True),
    "IMAGE_INVALID": (400, False),
    "IMAGE_TOO_LARGE": (413, False),
    "MODEL_UNAVAILABLE": (503, True),
    "UPSTREAM_TIMEOUT": (504, True),
    "UPSTREAM_ERROR": (502, True),
    "OUTPUT_NOT_HTML": (502, True),
    "REFINE_DISABLED": (403, False),
    "REFINE_UNAVAILABLE": (503, False),
    "REFINE_FAILED": (502, True),
    "INVALID_HTML": (400, False),
    "INTERNAL": (500, False),
}


def error(code: str, message: str) -> VisionCraftError:
    status, retryable = ERROR_TABLE.get(code, (500, False))
    return VisionCraftError(code, message, http_status=status, retryable=retryable)
