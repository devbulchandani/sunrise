FROM python:3.13-slim

WORKDIR /app

# node for the Bright Data CLI auxiliary service
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl nodejs npm \
  && rm -rf /var/lib/apt/lists/* \
  && npm install -g @brightdata/cli

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
