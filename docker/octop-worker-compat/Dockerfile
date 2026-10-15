FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /worker
COPY requirements.lock wheels.lock /worker/
COPY archives /worker/archives
RUN python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: --require-hashes --index-url https://pypi.org/simple -r requirements.lock \
    && python -m pip install --disable-pip-version-check --no-cache-dir --no-deps --require-hashes -r wheels.lock
COPY harness /worker/harness
COPY source-receipt.json worker_rpc.py /worker/
ENV PYTHONPATH=/worker/harness/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65534:65534
ENTRYPOINT ["python", "/worker/worker_rpc.py"]
