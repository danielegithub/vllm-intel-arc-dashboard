"""
Input validation and sanitization for vLLM Intel Arc Dashboard.
Prevents path traversal, shell injection, and malformed requests.
"""

import re
import shlex
from typing import List


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


def validate_model_name(model_name: str) -> bool:
    """
    Validates model name to prevent path traversal and injection attacks.
    
    Allowed: alphanumeric, dash, underscore, dot (e.g., 'Qwen2.5-7B-Instruct-AWQ')
    Forbidden: '..' (traversal), '/', '\' (path separators), shell metacharacters
    
    Args:
        model_name: The model name to validate
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: If model name is invalid
    """
    if not model_name:
        raise ValidationError("Model name cannot be empty")
    
    if len(model_name) > 255:
        raise ValidationError("Model name must be 255 characters or less")
    
    # Forbid path traversal
    if ".." in model_name:
        raise ValidationError("Model name cannot contain '..' (path traversal)")
    
    if "/" in model_name or "\\" in model_name:
        raise ValidationError("Model name cannot contain path separators (/ or \\)")
    
    # Allow only: letters, numbers, dash, underscore, dot
    if not re.match(r'^[\w\-\.]+$', model_name):
        raise ValidationError(
            "Model name can only contain letters, numbers, dash (-), underscore (_), and dot (.)"
        )
    
    return True


def validate_and_sanitize_extra_args(extra_args: str) -> List[str]:
    """
    Validates and sanitizes extra vLLM/Podman arguments.
    
    Uses a whitelist of allowed flags to prevent shell injection and
    unintended command execution.
    
    Allowed flags:
    - --dtype (float16, float32, bfloat16)
    - --gpu-memory-utilization (0.0-1.0)
    - --max-model-len (integer)
    - --tensor-parallel-size (integer)
    - --pipeline-parallel-size (integer)
    - --num-scheduler-steps (integer)
    - --max-num-seqs (integer)
    
    Args:
        extra_args: Space-separated extra arguments
        
    Returns:
        List of validated argument tokens
        
    Raises:
        ValidationError: If any argument is invalid or forbidden
    """
    if not extra_args or not extra_args.strip():
        return []
    
    # Whitelist of allowed vLLM flags
    ALLOWED_FLAGS = {
        "--dtype",
        "--gpu-memory-utilization",
        "--max-model-len",
        "--tensor-parallel-size",
        "--pipeline-parallel-size",
        "--num-scheduler-steps",
        "--max-num-seqs",
        "--max-model-seq-len",
        "--enable-lora",
        "--trust-remote-code",
    }
    
    # Forbidden shell metacharacters that could lead to injection
    FORBIDDEN_CHARS = {';', '|', '&', '`', '$', '(', ')', '<', '>', '*', '?', '[', ']', '{', '}', '\n', '\r'}
    
    # Check for forbidden characters
    for char in FORBIDDEN_CHARS:
        if char in extra_args:
            raise ValidationError(f"Extra args contains forbidden character: '{char}'")
    
    # Parse using shlex to properly handle quoted strings
    try:
        tokens = shlex.split(extra_args)
    except ValueError as e:
        raise ValidationError(f"Invalid shell syntax in extra_args: {str(e)}")
    
    if not tokens:
        return []
    
    result = []
    i = 0
    
    while i < len(tokens):
        token = tokens[i]
        
        if token.startswith("--"):
            # Extract flag name (part before '=')
            if "=" in token:
                flag, value = token.split("=", 1)
            else:
                flag = token
                value = None
            
            # Check if flag is in whitelist
            if flag not in ALLOWED_FLAGS:
                raise ValidationError(f"Flag not allowed: {flag}")
            
            # Validate the value
            if value is not None:
                # Value is provided with '=' (e.g., --dtype=float16)
                if not _is_valid_flag_value(flag, value):
                    raise ValidationError(f"Invalid value for {flag}: {value}")
                result.append(token)
            else:
                # Value might be in next token
                result.append(token)
                if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                    # Next token is the value
                    value = tokens[i + 1]
                    if not _is_valid_flag_value(flag, value):
                        raise ValidationError(f"Invalid value for {flag}: {value}")
                    result.append(value)
                    i += 1
        else:
            raise ValidationError(f"Unexpected token (must start with --): {token}")
        
        i += 1
    
    return result


def _is_valid_flag_value(flag: str, value: str) -> bool:
    """
    Validates the value of a specific flag.
    
    Args:
        flag: The flag name (e.g., '--dtype')
        value: The value to validate
        
    Returns:
        True if valid
    """
    if not value:
        return False
    
    # Basic alphanumeric + dot/dash/underscore (no shell chars)
    if not re.match(r'^[a-zA-Z0-9\.\-_]+$', value):
        return False
    
    # Flag-specific validations
    if flag == "--dtype":
        allowed_dtypes = {"float16", "float32", "bfloat16", "float8", "int8"}
        return value in allowed_dtypes
    
    elif flag == "--gpu-memory-utilization":
        try:
            val = float(value)
            return 0.0 <= val <= 1.0
        except ValueError:
            return False
    
    elif flag in {
        "--max-model-len",
        "--tensor-parallel-size",
        "--pipeline-parallel-size",
        "--num-scheduler-steps",
        "--max-num-seqs",
        "--max-model-seq-len"
    }:
        try:
            val = int(value)
            return val > 0
        except ValueError:
            return False
    
    elif flag in {"--enable-lora", "--trust-remote-code"}:
        return value.lower() in {"true", "false"}
    
    # Default: allow if it matches basic pattern
    return True
