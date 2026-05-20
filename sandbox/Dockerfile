FROM python:3.11-slim

RUN useradd -m sandboxuser
WORKDIR /app
RUN pip install --no-cache-dir pytest
USER sandboxuser

CMD ["pytest", "/app/test_payment.py", "-v", "--tb=short"]
