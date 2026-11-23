FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PORT=7860 EXCAL_DATA_DIR=/data/chaindata EXCAL_CHAIN_NETWORK=fork
WORKDIR /app
COPY . /app
EXPOSE 7860
CMD ["python", "hf_space_app.py"]
