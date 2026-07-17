FROM python:3.11-slim

WORKDIR /app

# requirements.txt existe mas esta vazio (apenas stdlib)
COPY requirements.txt .
COPY server.py .

# Railway injeta $PORT automaticamente; o server.py ja usa os.environ.get("PORT", "9000")
EXPOSE 9000

CMD ["python", "server.py"]
