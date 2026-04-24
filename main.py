import os
import asyncio
import aiohttp
import aiofiles
import re
import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# =====================================================
# CONFIGURAÇÕES — via variáveis de ambiente
# =====================================================
API_ID         = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")
CANAL_USERNAME = os.environ.get("CANAL_USERNAME", "")        # ex: achadinhos360
N8N_WEBHOOK    = os.environ.get("N8N_WEBHOOK_URL", "")       # URL do webhook no n8n

# =====================================================
# LOGGER
# =====================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# =====================================================
# REGEX — extrai link Shopee
# =====================================================
SHOPEE_REGEX = re.compile(r'https?://s\.shopee\.com\.br/\S+')
CATEGORY_REGEX = re.compile(r'#(\w+)')

# =====================================================
# CLIENTE TELEGRAM
# =====================================================
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# =====================================================
# HANDLER — nova mensagem no canal
# =====================================================
@client.on(events.NewMessage(chats=CANAL_USERNAME))
async def handler(event):
    msg = event.message

    # Só processa se tiver mídia de vídeo
    if not msg.media:
        return

    media = msg.media
    media_type = type(media).__name__

    # Aceita Document (vídeo enviado como arquivo) ou MessageMediaDocument
    if 'Document' not in media_type and 'Video' not in media_type:
        return

    text = msg.text or msg.message or ""

    # Extrai link Shopee
    shopee_match = SHOPEE_REGEX.search(text)
    if not shopee_match:
        log.info(f"Mensagem sem link Shopee — ignorada. ID: {msg.id}")
        return

    shopee_link = shopee_match.group(0).strip()

    # Extrai categoria do texto (#Beleza, #Moda, etc)
    category_match = CATEGORY_REGEX.search(text)
    categoria = category_match.group(1) if category_match else "Geral"

    log.info(f"Vídeo detectado | Categoria: {categoria} | Link: {shopee_link}")

    # Baixa o vídeo como bytes
    try:
        log.info("Baixando vídeo do Telegram...")
        video_bytes = await client.download_media(msg, bytes)
        log.info(f"Vídeo baixado: {len(video_bytes)} bytes")
    except Exception as e:
        log.error(f"Erro ao baixar vídeo: {e}")
        return

    # Envia para o n8n via webhook
    await enviar_para_n8n(
        video_bytes=video_bytes,
        shopee_link=shopee_link,
        categoria=categoria,
        msg_id=msg.id,
        texto_original=text
    )


# =====================================================
# ENVIO PARA N8N
# =====================================================
async def enviar_para_n8n(video_bytes, shopee_link, categoria, msg_id, texto_original):
    if not N8N_WEBHOOK:
        log.error("N8N_WEBHOOK_URL não configurado!")
        return

    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field(
                name="video",
                value=video_bytes,
                filename=f"video_{msg_id}.mp4",
                content_type="video/mp4"
            )
            form.add_field("shopee_link", shopee_link)
            form.add_field("categoria", categoria)
            form.add_field("msg_id", str(msg_id))
            form.add_field("texto_original", texto_original)
            form.add_field("data_coleta", datetime.utcnow().isoformat())

            log.info(f"Enviando para n8n webhook...")
            async with session.post(N8N_WEBHOOK, data=form, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                status = resp.status
                body = await resp.text()
                if status == 200:
                    log.info(f"n8n recebeu com sucesso | msg_id: {msg_id}")
                else:
                    log.error(f"n8n retornou status {status}: {body}")

    except Exception as e:
        log.error(f"Erro ao enviar para n8n: {e}")


# =====================================================
# HEALTH CHECK — porta para Railway detectar serviço ativo
# =====================================================
async def health_server():
    from aiohttp import web

    async def health(request):
        return web.Response(text="OK — Shopee Video Bot rodando")

    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Health check rodando na porta {port}")


# =====================================================
# MAIN
# =====================================================
async def main():
    log.info("Iniciando Shopee Video Bot...")
    log.info(f"Canal monitorado: {CANAL_USERNAME}")

    await health_server()
    await client.start()
    log.info("Conectado ao Telegram!")

    me = await client.get_me()
    log.info(f"Logado como: {me.first_name} (@{me.username})")

    log.info("Aguardando vídeos no canal...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
