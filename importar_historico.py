async def enviar_para_n8n(session, video_bytes, shopee_link, categoria, msg_id):
    try:
        from urllib.parse import urlencode

        form = aiohttp.FormData()
        form.add_field(
            "video",
            video_bytes,
            filename=f"video_{msg_id}.mp4",
            content_type="video/mp4"
        )

        query = urlencode({
            "shopee_link": shopee_link,
            "categoria": categoria,
            "msg_id": str(msg_id),
            "origem": "HISTORICO"
        })

        url = f"{N8N_WEBHOOK}?{query}"

        log.info(f"  🔗 Enviando para n8n: {url}")

        async with session.post(
            url,
            data=form,
            timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            text = await resp.text()

            if resp.status == 200:
                log.info(f"  ✅ n8n OK | {categoria} | msg_id: {msg_id}")
                return True

            log.error(f"  ❌ n8n erro {resp.status}: {text}")
            return False

    except Exception as e:
        log.error(f"  ❌ Erro envio: {e}")
        return False
