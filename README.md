# Reparador de Wi‑Fi — Automático (PoC)

![Okamoto Security Labs](https://img.shields.io/badge/Okamoto%20Security%20Labs-WiFi%20Pro-0b0b0b?style=flat&labelColor=0b0b0b&color=D4AF37)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

Ferramenta **cross‑platform** para diagnóstico rápido de rede e utilitários de reparo básicos (ping, speedtest, coleta de infos, flush DNS no Windows). Ideal para helpdesks e usuários finais.

**Guia rápido (PDF):** `docs/guia-rapido-wifi-pro.pdf`

## Recursos
- `status` — informações de rede (interfaces, IPs, gateway)
- `ping` — teste de conectividade (1.1.1.1, 8.8.8.8, google.com)
- `speedtest` — download/upload/latência via `speedtest-cli`
- `diagnose` — relatório em `reports/diagnostico.txt`
- `fix` — (Windows) `ipconfig /flushdns`, reset Winsock (eleva privilégios)

## Instalação rápida
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

## Uso (CLI)
```bash
python main.py status
python main.py ping
python main.py speedtest
python main.py diagnose
python main.py fix --flushdns --winsock  # Windows
```

## Tickets por e‑mail (opcional)
Preencha `.env` (SMTP) e use:
```bash
python main.py ticket open --client-name "Fulano" --client-email "fulano@exemplo.com" --summary "Wi‑Fi lento" --logical
```
Templates em `templates/`.

## Licença
MIT
