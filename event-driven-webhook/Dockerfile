# Use an official Python runtime as a parent image
FROM python:3.10-slim-bookworm

RUN apt update && \
    apt install -y \
    jq \
    git \
    curl

RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/arm64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    curl https://raw.githubusercontent.com/kagent-dev/kagent/refs/heads/main/scripts/get-kagent | bash

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container at /app
COPY main.py .

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Run the uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
