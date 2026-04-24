import os
import asyncio
import aiohttp
import re
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetForumTopicsRequest

# =====================================================
# CONFIGURAÇÕES
# =====================================================
API_ID         = int(os.environ.get("TELEGRAM_API_ID", "35413457"))
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "10b8fcf078013163bdda6e6cc5edb5a9")
SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")
CANAL_ID       = int(os.environ.get("CANAL_USERNAME", "-1002362134244"))
N8N_WEBHOOK    = os.environ.get("N8N_WEBHOOK_URL", "")

LIMITE_POR_TOPICO = 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SHOPEE_REGEX   = re.compile(r'https?://s\.shopee\.com\.br/\S+')
CATEGORY_REGEX = re.compile(r'#(\w+)', re.IGNORECASE)

CATEGORIAS_MAPA = {
    'moda': 'Moda', 'acessorios': 'Acessorios', 'acessório': 'Acessorios',
    'acessórios': 'Acessorios', 'beleza': 'Beleza', 'banheiro': 'Banheiro',
    'cozinha': 'Cozinha', 'utilidades': 'Utilidades', 'dublados': 'Dublados',
    'decoracao': 'Decoracao', 'decoração': 'Decoracao', 'eletronicos': 'Eletronicos',
    'eletrônicos': 'Eletronicos', 'pet': 'Pet', 'automoveis': 'Automoveis',
    'automóveis': 'Automoveis', 'infantil': 'Infantil', 'maternidade': 'Maternidade',
    'papelaria': 'Papelaria', 'artesanato': 'Artesanato', 'esporte': 'Esporte',
    'seguranca': 'Seguranca', 'segurança': 'Seguranca',
}

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
                log.info(f"✅ n8n OK | Categoria: {categoria} | msg_id: {msg_id}")
                return True
            else:
                log.error(f"❌ n8n erro {resp.status}: {await resp.text()}")
                return False
    except Exception as e:
        log.error(f"❌ Erro envio n8n: {e}")
        return False

async def importar_historico():
    if not SESSION_STRING or not N8N_WEBHOOK:
        log.error("Variáveis de ambiente não configuradas!")
        return

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    log.info(f"Conectado como: {me.first_name}")

    entity = await client.get_entity(CANAL_ID)
    log.info(f"Canal: {entity.title}")

    # Busca os tópicos do canal
    log.info("Buscando tópicos do canal...")
    try:
        result = await client(GetForumTopicsRequest(
            channel=entity,
            offset_date=0,
            offset_id=0,
            offset_topic=0,
            limit=100,
            q=""
        ))
        topics = result.topics
        log.info(f"Encontrados {len(topics)} tópicos")
    except Exception as e:
        log.error(f"Erro ao buscar tópicos: {e}")
        log.info("Canal pode não ter tópicos. Tentando leitura direta...")
        topics = []

    total_enviados = 0
    coletados = {}

    async with aiohttp.ClientSession() as http_session:

        if topics:
            # Lê mensagens de cada tópico
            for topic in topics:
                topic_id   = topic.id
                topic_nome = topic.title
                log.info(f"\n📂 Tópico: {topic_nome} (ID: {topic_id})")

                encontrado = False
                async for msg in client.iter_messages(entity, limit=200, reply_to=topic_id):
                    if encontrado:
                        break
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

                    # Tenta extrair categoria do texto ou usa o nome do tópico
                    cat_match = CATEGORY_REGEX.search(text)
                    if cat_match:
                        categoria = CATEGORIAS_MAPA.get(cat_match.group(1).lower(), topic_nome)
                    else:
                        categoria = CATEGORIAS_MAPA.get(topic_nome.lower(), topic_nome)

                    log.info(f"📥 Baixando | Categoria: {categoria} | msg_id: {msg.id}")
                    try:
                        video_bytes = await client.download_media(msg, bytes)
                        log.info(f"✅ {len(video_bytes)/1024/1024:.1f} MB baixado")
                    except Exception as e:
                        log.error(f"Erro download: {e}")
                        continue

                    sucesso = await enviar_para_n8n(http_session, video_bytes, shopee_link, categoria, msg.id)
                    if sucesso:
                        coletados[categoria] = coletados.get(categoria, 0) + 1
                        total_enviados += 1
                        encontrado = True
                        log.info(f"📊 Total enviados: {total_enviados} | {coletados}")

                    await asyncio.sleep(3)
        else:
            # Fallback: leitura direta
            log.info("Lendo mensagens diretamente...")
            async for msg in client.iter_messages(entity, limit=3000):
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
                cat_match = CATEGORY_REGEX.search(text)
                if not cat_match:
                    continue
                cat_raw   = cat_match.group(1).lower()
                categoria = CATEGORIAS_MAPA.get(cat_raw, cat_raw.capitalize())
                if coletados.get(categoria, 0) >= LIMITE_POR_TOPICO:
                    continue
                log.info(f"📥 Baixando | Categoria: {categoria} | msg_id: {msg.id}")
                try:
                    video_bytes = await client.download_media(msg, bytes)
                    log.info(f"✅ {len(video_bytes)/1024/1024:.1f} MB")
                except Exception as e:
                    log.error(f"Erro: {e}")
                    continue
                sucesso = await enviar_para_n8n(http_session, video_bytes, shopee_link, categoria, msg.id)
                if sucesso:
                    coletados[categoria] = coletados.get(categoria, 0) + 1
                    total_enviados += 1
                    log.info(f"📊 {total_enviados} enviados | {coletados}")
                await asyncio.sleep(3)

    await client.disconnect()
    log.info("=" * 50)
    log.info(f"IMPORTAÇÃO CONCLUÍDA! Total: {total_enviados}")
    log.info(f"Por categoria: {coletados}")
    log.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(importar_historico())
