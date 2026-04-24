# Shopee Video Bot — Central de Ofertas

Serviço que monitora o Canal Achadinhos 360 no Telegram,
captura vídeos com links Shopee e envia para o n8n processar.

## Fluxo

```
Canal Telegram → Detecta vídeo + link Shopee
→ Baixa o vídeo
→ Envia para n8n via webhook
→ n8n gera link afiliado + legenda + publica no Shopee Vídeo
```

## Variáveis de Ambiente (Railway)

| Variável | Descrição |
|---|---|
| TELEGRAM_API_ID | ID da API do Telegram (my.telegram.org) |
| TELEGRAM_API_HASH | Hash da API do Telegram |
| TELEGRAM_SESSION_STRING | Session string gerada pelo script local |
| CANAL_USERNAME | Username do canal sem @ (ex: achadinhos360) |
| N8N_WEBHOOK_URL | URL do webhook no n8n |

## Deploy no Railway

1. Suba este repositório no GitHub
2. No Railway: New Project → Deploy from GitHub
3. Adicione as variáveis de ambiente
4. Railway detecta o Procfile e sobe automaticamente

## Health Check

```
GET /health → retorna "OK — Shopee Video Bot rodando"
```
