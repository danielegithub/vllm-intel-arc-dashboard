import pytest
from app.validators import validate_model_name, validate_and_sanitize_extra_args, ValidationError

def test_valid_model_names():
    assert validate_model_name("Qwen2.5-Coder-7B-Instruct-AWQ") is True
    assert validate_model_name("llama-3-8b-instruct") is True
    assert validate_model_name("my_model_v1.0") is True

def test_invalid_model_names_path_traversal():
    with pytest.raises(ValidationError):
        validate_model_name("../../etc/passwd")

    with pytest.raises(ValidationError):
        validate_model_name("folder/subfolder")

    with pytest.raises(ValidationError):
        validate_model_name("..\\windows\\system32")

def test_invalid_model_names_forbidden_characters():
    with pytest.raises(ValidationError):
        validate_model_name("model; rm -rf /")

    with pytest.raises(ValidationError):
        validate_model_name("model$(whoami)")

def test_valid_extra_args():
    res = validate_and_sanitize_extra_args("--dtype float16 --gpu-memory-utilization 0.7")
    assert "--dtype" in res
    assert "float16" in res
    assert "--gpu-memory-utilization" in res

def test_invalid_extra_args_forbidden_characters():
    with pytest.raises(ValidationError):
        validate_and_sanitize_extra_args("--dtype float16; rm -rf /")

    with pytest.raises(ValidationError):
        validate_and_sanitize_extra_args("--dtype $(whoami)")

def test_invalid_extra_args_unsupported_flags():
    with pytest.raises(ValidationError):
        validate_and_sanitize_extra_args("--malicious-flag value")
