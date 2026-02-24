from agent.pipeline_error_codes import PipelineErrorCode, is_retryable_pipeline_error


def test_pipeline_error_codes_retryable_subset():
    assert is_retryable_pipeline_error(PipelineErrorCode.TOOL_RATE_LIMITED)
    assert is_retryable_pipeline_error(PipelineErrorCode.TOOL_TIMEOUT)
    assert not is_retryable_pipeline_error(PipelineErrorCode.DSL_VALIDATION_FAILED)


def test_pipeline_error_codes_unknown_code_is_not_retryable():
    assert not is_retryable_pipeline_error("UNKNOWN_CODE")

