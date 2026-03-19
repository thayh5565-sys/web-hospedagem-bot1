
# Use a imagem oficial do Python como base
FROM python:3.11-slim-buster

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copia o arquivo de requisitos e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do bot para o diretório de trabalho
COPY bot.py .

# Comando para executar o bot quando o contêiner iniciar usando Gunicorn
CMD ["gunicorn", "bot:app", "-b", "0.0.0.0:$PORT"]
