FROM python:3.13-alpine3.22

RUN addgroup -S hunt && adduser -S -G hunt hunt
COPY scripts/hunt.py /app/hunt.py
RUN chmod 0555 /app/hunt.py

USER hunt
WORKDIR /app
ENTRYPOINT ["python", "/app/hunt.py"]
