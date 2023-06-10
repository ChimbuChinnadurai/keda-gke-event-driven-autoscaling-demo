FROM python:3.6-slim
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY app.py .

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

CMD [ "python", "app.py" ]