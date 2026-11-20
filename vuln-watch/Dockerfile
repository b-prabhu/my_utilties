FROM python:3.13-slim
WORKDIR /app
COPY . .
ENV VULNWATCH_DATA_DIR=/data
RUN mkdir -p /data && chown 1000 /data
VOLUME ["/data"]
EXPOSE 8085
USER 1000
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8085"]
