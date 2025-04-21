# Use an official Python runtime as a parent image
# Using Python 3.11 based on user's previous error message context
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Default Flask settings (can be overridden)
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000
# Set this environment variable when running the container or use a .env file
# ENV DROPBOX_ACCESS_TOKEN="your_actual_token" # Avoid hardcoding here

# Install system dependencies including ffmpeg
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define the command to run the application
# Uses Flask's built-in server. For production, consider using Gunicorn or uWSGI.
CMD ["flask", "run"]
