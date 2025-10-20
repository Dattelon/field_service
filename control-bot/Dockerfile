FROM python:3.11-slim

WORKDIR /app

# Install SSH client
RUN apt-get update && apt-get install -y \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY control_bot.py .
COPY .env .

# Run bot
CMD ["python", "-u", "control_bot.py"]
