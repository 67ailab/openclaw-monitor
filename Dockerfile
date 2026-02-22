FROM python:3.12-slim
WORKDIR /app
COPY exporter.py .
# The exporter needs 'openclaw' command which is on the host. 
# Better to just use the host process for the exporter to avoid dependency hell inside docker.
# I will revert the docker-compose change and use 'extra_hosts' to point to host.
EXPOSE 8000
CMD ["python", "exporter.py"]
