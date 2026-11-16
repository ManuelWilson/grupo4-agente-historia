FROM public.ecr.aws/lambda/python:3.12

# Dependencias del gateway
COPY requirements.txt .
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}" --no-cache-dir

# Código: el paquete `gateway/` + el entrypoint `lambda_handler.py`
COPY gateway ${LAMBDA_TASK_ROOT}/gateway
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/lambda_handler.py

# Comando de inicio (sin cambios respecto a la configuración actual)
CMD ["lambda_handler.lambda_handler"]
