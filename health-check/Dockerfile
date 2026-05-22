FROM python:3.12-alpine

RUN apk add --no-cache postgresql-client redis

WORKDIR /app
COPY health_server.py /app/

EXPOSE 9100
CMD ["python3", "/app/health_server.py"]
