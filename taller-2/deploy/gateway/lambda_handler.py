"""Entrypoint de AWS Lambda.

La lógica vive en el paquete `gateway/`; este archivo solo conserva el handler
configurado en la función (`lambda_handler.lambda_handler`).
"""

from gateway.lambda_handler import lambda_handler

__all__ = ["lambda_handler"]
