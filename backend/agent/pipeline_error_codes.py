from __future__ import annotations

from enum import StrEnum


class PipelineErrorCode(StrEnum):
    DSL_VALIDATION_FAILED = "DSL_VALIDATION_FAILED"
    DSL_REF_NOT_FOUND = "DSL_REF_NOT_FOUND"
    LLM_AUTOFILL_FAILED = "LLM_AUTOFILL_FAILED"
    TOOL_AUTH_ERROR = "TOOL_AUTH_ERROR"
    TOOL_RATE_LIMITED = "TOOL_RATE_LIMITED"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    VERIFY_COUNT_MISMATCH = "VERIFY_COUNT_MISMATCH"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"
    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"


_RETRYABLE_ERROR_CODES = {
    PipelineErrorCode.TOOL_RATE_LIMITED,
    PipelineErrorCode.TOOL_TIMEOUT,
}


def is_retryable_pipeline_error(code: str | PipelineErrorCode) -> bool:
    try:
        value = PipelineErrorCode(str(code))
    except ValueError:
        return False
    return value in _RETRYABLE_ERROR_CODES
