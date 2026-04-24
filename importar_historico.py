import os
import asyncio
import aiohttp
import re
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

# =====================================================
# CONFIGURAÇÕES
# =====================================================
API_ID          = int(os.environ.get("TELEGRAM_API_ID", "35413457"))
API_HASH        = os.environ.get("TELEGRAM_API_HASH", "10b8fcf078013163bdda6e6cc5edb5a9")
SESSION_STRING  = os.environ.get("TELEGRAM_SESSION_STRING", "")
CANAL_ID        = int(os.environ.get("CANAL_USERNAME", "-1002362134244"))
N8N_WEBHOOK     = os.environ.get("N8N_WEBHOOK_URL", "")

# 1 vídeo por categoria
LIMITE_POR_CATEGORIA = 1

# Categorias mapeadas pelos tópicos do canal
CATEGORIAS_ALVO = [
    'Moda', 'Acessorios', 'Beleza', 'Banheiro', 'Cozinha',
    'Utilidades', 'Dublados', 'Decoracao', 'Eletronicos', 'Pet',
    'Automoveis', 'Infantil', 'Maternidade', 'Papelaria',
    'Artesanato', 'Esporte', 'Seguranca'
]

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
SHOPEE_REGEX   = re.compile(r'https?://s\.shopee\.com\.br/\S+')
CATEGORY_REGEX = re.compile(r'#(\w+)', re.IGNORECASE)

# =====================================================
# NORMALIZA CATEGORIA
# =====================================================
def normalizar_categoria(texto):
    mapa = {
        'moda': 'Moda',
        'acessorios': 'Acessorios',
        'acessório': 'Acessorios',
        'acessórios': 'Acessorios',
        'beleza': 'Beleza',
        'banheiro': 'Banheiro',
        'cozinha': 'Cozinha',
        'utilidades': 'Utilidades',
        'dublados': 'Dublados',
        'decoracao': 'Decoracao',
        'decoração': 'Decoracao',
        'eletronicos': 'Eletronicos',
        'eletrônicos': 'Eletronicos',
        'pet': 'Pet',
        'automoveis': 'Automoveis',
        'automóveis': 'Automoveis',
        'infantil': 'Infantil',
        'maternidade': 'Maternidade',
        'papelaria': 'Papelaria',
        'artesanato': 'Artesanato',
        'esporte': 'Esporte',
        'seguranca': 'Seguranca',
        'segurança': 'Seguranca',
    }
    return mapa.get(texto.lower().strip(), None)

# =====================================================
# ENVIA PARA N8N
# =====================================================
async def enviar_para_n8n(session, video_bytes, shopee_link, categoria, msg_id):
    try:
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
        form.add_field("origem", "HISTORICO")

        async with session.post(
            N8N_WEBHOOK,
            data=form,
            timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            status = resp.status
            body = await resp.text()
            if status == 200:
                log.info(f"✅ n8n OK | Categoria: {categoria} | msg_id: {msg_id}")
                return True
            else:
                log.error(f"❌ n8n erro {status}: {body}")
                return False
    except Exception as e:
        log.error(f"❌ Erro ao enviar para n8n: {e}")
        return False

# =====================================================
# IMPORTADOR PRINCIPAL
# =====================================================
async def importar_historico():
    if not SESSION_STRING:
        log.error("TELEGRAM_SESSION_STRING não configurado!")
        return

    if not N8N_WEBHOOK:
        log.error("N8N_WEBHOOK_URL não configurado!")
        return

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    log.info(f"Conectado como: {me.first_name} (@{me.username})")
    log.info(f"Importando histórico do canal: {CANAL_ID}")
    log.info(f"Meta: {LIMITE_POR_CATEGORIA} vídeo por categoria")
    log.info(f"Categorias: {CATEGORIAS_ALVO}")

    # Controle de quantos vídeos já coletamos por categoria
    coletados = {cat: 0 for cat in CATEGORIAS_ALVO}
    total_enviados = 0

    async with aiohttp.ClientSession() as http_session:
        async for msg in client.iter_messages(CANAL_ID, limit=5000):
            # Verifica se todas as categorias já foram coletadas
            pendentes = [c for c in CATEGORIAS_ALVO if coletados[c] < LIMITE_POR_CATEGORIA]
            if not pendentes:
                log.info("✅ Todas as categorias coletadas! Encerrando.")
                break

            # Só processa mensagens com mídia
            if not msg.media:
                continue

            media_type = type(msg.media).__name__
            if 'Document' not in media_type and 'Video' not in media_type:
                continue

            text = msg.text or msg.message or ""

            # Extrai link Shopee
            shopee_match = SHOPEE_REGEX.search(text)
            if not shopee_match:
                continue

            shopee_link = shopee_match.group(0).strip()

            # Extrai categoria
            category_match = CATEGORY_REGEX.search(text)
            if not category_match:
                continue

            categoria_raw = category_match.group(1)
            categoria = normalizar_categoria(categoria_raw)

            if not categoria:
                continue

            if categoria not in CATEGORIAS_ALVO:
                continue

            if coletados[categoria] >= LIMITE_POR_CATEGORIA:
                continue

            # Baixa o vídeo
            log.info(f"📥 Baixando vídeo | Categoria: {categoria} | msg_id: {msg.id}")
            try:
                video_bytes = await client.download_media(msg, bytes)
                tamanho_mb = len(video_bytes) / (1024 * 1024)
                log.info(f"✅ Vídeo baixado: {tamanho_mb:.1f} MB")
            except Exception as e:
                log.error(f"❌ Erro ao baixar vídeo msg {msg.id}: {e}")
                continue

            # Envia para o n8n
            sucesso = await enviar_para_n8n(
                http_session,
                video_bytes,
                shopee_link,
                categoria,
                msg.id
            )

            if sucesso:
                coletados[categoria] += 1
                total_enviados += 1
                log.info(f"📊 Progresso: {coletados}")

            # Pequena pausa entre envios para não sobrecarregar
            await asyncio.sleep(3)

    await client.disconnect()

    log.info("=" * 50)
    log.info(f"IMPORTAÇÃO CONCLUÍDA!")
    log.info(f"Total enviados: {total_enviados}")
    log.info(f"Por categoria: {coletados}")
    log.info("=" * 50)

# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    asyncio.run(importar_historico())
