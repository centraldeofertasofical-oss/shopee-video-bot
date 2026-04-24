import os
import asyncio
import aiohttp
import re
import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# =====================================================
# CONFIGURAÇÕES
# =====================================================
API_ID         = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")
CANAL_INPUT    = os.environ.get("CANAL_USERNAME", "")  # pode ser username OU ID
N8N_WEBHOOK    = os.environ.get("N8N_WEBHOOK_URL", "")

# =====================================================
# LOGGER
# =====================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# =====================================================
# REGEX
# =====================================================
SHOPEE_REGEX = re.compile(r'https?://s\.shopee\.com\.br/\S+')
CATEGORY_REGEX = re.compile(r'#(\w+)')

# =====================================================
# CLIENT
# =====================================================
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


# =====================================================
# RESOLVE CANAL (CORREÇÃO PRINCIPAL)
# =====================================================
async def get_canal_entity():
    try:
        # Se for número → tratar como ID
        if CANAL_INPUT.startswith("-100"):
            canal = await client.get_entity(int(CANAL_INPUT))
        else:
            canal = await client.get_entity(CANAL_INPUT)

        log.info(f"Canal resolvido: {canal.title}")
        return canal

    except Exception as e:
        log.error(f"Erro ao resolver canal: {e}")
        raise


# =====================================================
# HANDLER
# =====================================================
async def setup_handler(canal):

    @client.on(events.NewMessage(chats=canal))
    async def handler(event):
        msg = event.message

        if not msg.media:
            return

        media_type = type(msg.media).__name__
        if 'Document' not in media_type and 'Video' not in media_type:
            return

        text = msg.text or msg.message or ""

        shopee_match = SHOPEE_REGEX.search(text)
        if not shopee_match:
            log.info(f"Ignorado (sem link Shopee) | ID: {msg.id}")
            return

        shopee_link = shopee_match.group(0).strip()

        category_match = CATEGORY_REGEX.search(text)
        categoria = category_match.group(1) if category_match else "Geral"

        log.info(f"Vídeo OK | {categoria} | {msg.id}")

        try:
            video_bytes = await client.download_media(msg, bytes)
        except Exception as e:
            log.error(f"Erro download: {e}")
            return

        await enviar_para_n8n(video_bytes, shopee_link, categoria, msg.id, text)


# =====================================================
# ENVIO N8N
# =====================================================
async def enviar_para_n8n(video_bytes, shopee_link, categoria, msg_id, texto_original):
    if not N8N_WEBHOOK:
        log.error("Webhook não configurado")
        return

    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("video", video_bytes, filename=f"video_{msg_id}.mp4", content_type="video/mp4")
            form.add_field("shopee_link", shopee_link)
            form.add_field("categoria", categoria)
            form.add_field("msg_id", str(msg_id))
            form.add_field("texto_original", texto_original)
            form.add_field("data_coleta", datetime.utcnow().isoformat())

            async with session.post(N8N_WEBHOOK, data=form) as resp:
                if resp.status == 200:
                    log.info(f"n8n OK | {msg_id}")
                else:
                    log.error(f"Erro n8n {resp.status}")

    except Exception as e:
        log.error(f"Erro envio n8n: {e}")


# =====================================================
# HEALTH CHECK
# =====================================================
async def health_server():
    from aiohttp import web

    async def health(request):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    log.info(f"Health OK porta {port}")


# =====================================================
# MAIN
# =====================================================
async def main():
    log.info("Iniciando bot...")

    await health_server()
    await client.start()

    log.info("Telegram conectado")

    canal = await get_canal_entity()
    await setup_handler(canal)

    log.info("Aguardando mensagens...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
