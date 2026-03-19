
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import requests
from flask import Flask, request
from threading import Thread

# Configurar logging
logging.basicConfig(
    format=\'%(asctime)s - %(name)s - %(levelname)s - %(message)s\',
    level=logging.INFO
)
logging.getLogger(\'httpx\').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Variáveis de ambiente
TELEGRAM_BOT_TOKEN = os.getenv(\'TELEGRAM_BOT_TOKEN\')
NETLIFY_AUTH_TOKEN = os.getenv(\'NETLIFY_AUTH_TOKEN\')
WEBHOOK_URL = os.getenv(\'WEBHOOK_URL\') # URL do webhook fornecida pelo Koyeb
PORT = int(os.getenv(\'PORT\', 8000))

# Inicializar o Flask app para o webhook e health check
app = Flask(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem quando o comando /start é emitido."""
    user = update.effective_user
    await update.message.reply_html(
        f"Olá, {user.mention_html()}!\n\n" \
        "Eu sou o **WEB HOSPEDAGEM BOT**! Envie-me um arquivo `.zip` contendo o seu site estático (com um `index.html` na raiz) e eu o hospedarei gratuitamente para você.\n\n" \
        "**Instruções:**\n" \
        "1. Prepare seu site estático em um arquivo `.zip`. Certifique-se de que o `index.html` esteja na raiz do `.zip`.\n" \
        "2. Envie o arquivo `.zip` para mim.\n" \
        "3. Aguarde enquanto eu faço o deploy do seu site. Você receberá um link quando estiver pronto!\n\n" \
        "**Observação:** Este bot utiliza o Netlify para hospedagem gratuita. Sites dinâmicos ou com backend não são suportados.",
        parse_mode=ParseMode.HTML
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lida com o recebimento de documentos (arquivos .zip)."""
    if not update.message.document:
        return

    document = update.message.document

    if not document.file_name.endswith(\".zip\"):
        await update.message.reply_text(
            "Por favor, envie um arquivo `.zip` contendo seu site estático."
        )
        return

    await update.message.reply_text("Recebi seu arquivo! Fazendo upload para o Netlify...")

    try:
        # Baixar o arquivo do Telegram
        new_file = await context.bot.get_file(document.file_id)
        zip_file_path = f"/tmp/{document.file_name}"
        await new_file.download_to_drive(zip_file_path)

        # Fazer upload para o Netlify
        if not NETLIFY_AUTH_TOKEN:
            await update.message.reply_text(
                "Erro: O token de autenticação do Netlify não foi configurado. Por favor, peça ao administrador do bot para configurá-lo."
            )
            logger.error("NETLIFY_AUTH_TOKEN não configurado.")
            return

        headers = {
            \'Content-Type\': \'application/zip\',
            \'Authorization\': f\'Bearer {NETLIFY_AUTH_TOKEN}\'
        }

        netlify_api_url = \'https://api.netlify.com/api/v1/sites\'

        with open(zip_file_path, \'rb\') as f:
            response = requests.post(netlify_api_url, headers=headers, data=f)

        if response.status_code == 201:
            site_info = response.json()
            site_url = site_info.get(\'ssl_url\') or site_info.get(\'url\')
            site_name = site_info.get(\'name\')

            await update.message.reply_html(
                f"🎉 Seu site foi hospedado com sucesso!\n\n" \
                f"**Nome do Site:** `{site_name}`\n" \
                f"**URL:** <a href=\"{site_url}\">{site_url}</a>\n\n" \
                "Lembre-se que pode levar alguns minutos para o site ficar totalmente disponível.",
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Site {site_name} ({site_url}) hospedado com sucesso.")
        else:
            error_message = response.json().get(\'message\', \'Erro desconhecido\')
            await update.message.reply_text(
                f"Ocorreu um erro ao hospedar seu site no Netlify: {error_message}. Código de status: {response.status_code}"
            )
            logger.error(f"Erro ao fazer upload para o Netlify: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        await update.message.reply_text(
            "Ocorreu um erro inesperado ao processar seu arquivo. Por favor, tente novamente mais tarde."
        )
    finally:
        # Limpar o arquivo zip temporário
        if os.path.exists(zip_file_path):
            os.remove(zip_file_path)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error("Update \'%s\' caused error \'%s\'", update, context.error)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Desculpe, ocorreu um erro interno. Por favor, tente novamente mais tarde."
        )

# Handler para o webhook do Telegram
@app.route(\'/telegram\', methods=[\'POST\'])
async def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return \'ok\'

# Health check para o Koyeb
@app.route(\'/\', methods=[\'GET\'])
def health_check():
    return \'Bot is running\', 200

def run_flask():
    app.run(host=\'0.0.0.0\', port=PORT)

def main() -> None:
    """Inicia o bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN não configurado. Por favor, defina a variável de ambiente.")
        print("Erro: TELEGRAM_BOT_TOKEN não configurado. O bot não pode ser iniciado.")
        return

    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL não configurado. O bot não pode ser iniciado em modo webhook.")
        print("Erro: WEBHOOK_URL não configurado. O bot não pode ser iniciado em modo webhook.")
        return

    global application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ZIP, handle_document))
    application.add_error_handler(error_handler)

    # Configurar webhook
    application.bot.set_webhook(url=WEBHOOK_URL + \'/telegram\')

    logger.info("Bot iniciado em modo webhook.")

    # Iniciar o servidor Flask em uma thread separada
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Manter a thread principal do bot ativa (para processar updates)
    application.run_webhook(listen=\'0.0.0.0\', port=PORT, url_path=\'/telegram\')

if __name__ == \'__main__\':
    main()
