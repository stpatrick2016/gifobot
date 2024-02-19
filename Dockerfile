FROM python:3.9-slim

COPY . /app
WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

RUN python3 -m pip install pip --upgrade
RUN pip install -r requirements.txt

ENTRYPOINT ["python3", "-u", "/app/main.py"]