FROM python:3.12-alpine

WORKDIR /app
COPY cron_dispatcher.py /app/

CMD ["python3", "/app/cron_dispatcher.py", "--daemon"]
