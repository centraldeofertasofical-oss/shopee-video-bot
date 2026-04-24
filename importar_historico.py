import os
import asyncio
import aiohttp
import re
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID         = int(os.environ.get("TELEGRAM_API_ID", "35413457"))
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "10b8fcf078013163bdda6e6cc5edb5a9")
SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")
CANAL_ID       = int(os.environ.get("CANAL_USERNAME", "-1002362134244"))
N8N_WEBHOOK    = os.environ.get("N8N_WEBHOOK_URL", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SHOPEE_REGEX = re.compile(r'https?://s\.shopee\.com\.br/\S+')

# Todos os tópicos mapeados
TOPICOS = [
    (2,    "Automoveis"),
    (3,    "Dublados"),
    (6,    "Banheiro"),
    (7,    "Cozinha"),
    (8,    "Pet"),
    (9,    "Beleza"),
    (10,   "Moda"),
    (11,   "Eletronicos"),
    (12,   "Acessorios"),
    (19,   "Decoracao"),
    (49,   "Maternidade"),
    (78,   "Papelaria"),
    (80,   "Utilidades"),
    (92,   "Seguranca"),
    (159,  "Artesanato"),
    (500,  "Infantil"),
    (1167, "Esporte"),
]
# ID 1 (+ 2MIL VÍDEOS) ignorado — é arquivo geral, não categoria

async def enviar_para_n8n(session, video_bytes, shopee_link, categoria, msg_id):
    try:
        form = aiohttp.FormData()
        form.add_field("video", video_bytes, filename=f"video_{msg_id}.mp4", content_type="video/mp4")
        form.add_field("shopee_link", shopee_link)
        form.add_field("categoria", categoria)
        form.add_field("msg_id", str(msg_id))
        form.add_field("origem", "HISTORICO")
        async with session.post(N8N_WEBHOOK, data=form, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status == 200:
                log.info(f"  ✅ n8n OK | {categoria} | msg_id: {msg_id}")
                return True
            log.error(f"  ❌ n8n erro {resp.status}: {await resp.text()}")
            return False
    except Exception as e:
        log.error(f"  ❌ Erro envio: {e}")
        return False

async def pegar_video_do_topico(client, entity, topic_id, categoria):
    log.info(f"\n📂 [{categoria}] topic_id: {topic_id}")
    try:
        count = 0
        async for msg in client.iter_messages(entity, limit=100, reply_to=topic_id):
            count += 1
            if not msg.media:
                continue
            media_type = type(msg.media).__name__
            if 'Document' not in media_type and 'Video' not in media_type:
                continue
            text = msg.text or msg.message or ""
            shopee_match = SHOPEE_REGEX.search(text)
            if not shopee_match:
                continue
            shopee_link = shopee_match.group(0).strip()
            log.info(f"  📎 Link: {shopee_link[:50]}...")
            return msg, shopee_link
        log.info(f"  ⚠️ Nenhum vídeo válido ({count} msgs verificadas)")
    except Exception as e:
        log.error(f"  ❌ Erro ao ler tópico: {e}")
    return None, None

async def importar_historico():
    if not SESSION_STRING or not N8N_WEBHOOK:
        log.error("❌ SESSION_STRING ou N8N_WEBHOOK não configurados!")
        return

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    log.info(f"✅ Conectado: {me.first_name} (@{me.username})")

    entity = await client.get_entity(CANAL_ID)
    log.info(f"✅ Canal: {entity.title}")
    log.info(f"📋 Total de tópicos: {len(TOPICOS)}")
    log.info("=" * 50)

    total_enviados = 0
    pulados = []

    async with aiohttp.ClientSession() as http_session:
        for topic_id, categoria in TOPICOS:
            msg, shopee_link = await pegar_video_do_topico(client, entity, topic_id, categoria)

            if not msg or not shopee_link:
                pulados.append(categoria)
                continue

            log.info(f"  📥 Baixando vídeo (msg_id: {msg.id})...")
            try:
                video_bytes = await client.download_media(msg, bytes)
                log.info(f"  📦 {len(video_bytes)/1024/1024:.1f} MB")
            except Exception as e:
                log.error(f"  ❌ Erro download: {e}")
                pulados.append(categoria)
                continue

            sucesso = await enviar_para_n8n(http_session, video_bytes, shopee_link, categoria, msg.id)
            if sucesso:
                total_enviados += 1
            else:
                pulados.append(categoria)

            await asyncio.sleep(5)

    await client.disconnect()
    log.info("=" * 50)
    log.info(f"✅ IMPORTAÇÃO CONCLUÍDA!")
    log.info(f"   Enviados: {total_enviados}/{len(TOPICOS)}")
    if pulados:
        log.info(f"   Pulados:  {pulados}")
    log.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(importar_historico())
