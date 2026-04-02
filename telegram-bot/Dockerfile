FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY *.py ./

# Non-root user for security
RUN useradd -m botuser && chown -R botuser /app
USER botuser

EXPOSE 8443

CMD ["python", "bot.py"]
