#Desenvolvido por Gustavo Okamoto de Carvalho

import argparse
import platform
import subprocess
import sys
import os
import time
import re # Necessário para o parsing da saída do ping
from datetime import datetime
from pathlib import Path

# --- Bibliotecas para Tickets/E-mail ---
import smtplib
from email.message import EmailMessage
import json
import random
import string
from dotenv import load_dotenv

# Carrega variáveis de ambiente (necessário para SMTP)
load_dotenv()

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns # Novo para o monitor
    console = Console()
except Exception:
    # Fallback if rich isn't installed
    class SimpleConsole:
        def print(self, *a, **k):
            print(*a)
    console = SimpleConsole()

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)
TEMPLATES = ROOT / "templates"
TICKETS_DB = ROOT / "tickets" / "tickets_db.json"
TICKETS_DB.parent.mkdir(exist_ok=True)

# ==============================================================================
# 1. Funções Auxiliares
# ==============================================================================

def run(cmd, shell=True):
    """Executa um comando de sistema e retorna o código, stdout e stderr."""
    try:
        # Usa shell=False para maior segurança, a menos que o comando exija shell (como `ifconfig || ip a`)
        res = subprocess.run(cmd, shell=shell, capture_output=True, text=True, check=False, encoding='utf-8')
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

# ==============================================================================
# 2. Funções de Rede (status, ping, speedtest, diagnose, fix)
# ==============================================================================

def cmd_status(args):
    os_name = platform.system()
    if os_name == "Windows":
        code, out, err = run("ipconfig /all")
    else:
        # Usa shell=True para o operador OR (||)
        code, out, err = run("ifconfig || ip a", shell=True) 
    if code != 0:
        console.print(f"[red]Erro:[/red] {err}")
        return code
    console.print(Panel(out, title=f"Status de Rede ({os_name})"))
    return 0

def cmd_ping(args):
    targets = args.targets or ["1.1.1.1", "8.8.8.8", "google.com"]
    count_flag = "-n" if platform.system() == "Windows" else "-c"
    for t in targets:
        console.print(f"[bold]Ping:[/bold] {t}")
        # Usamos shell=False aqui, pois é um comando simples
        code, out, err = run([f"ping", count_flag, "4", t], shell=False)
        if code == 0:
            console.print(out)
        else:
            console.print(f"[red]Falhou:[/red] {err or out}")
    return 0

def cmd_speedtest(args):
    # Usa sys.executable para garantir que o speedtest-cli seja executado no ambiente correto
    code, out, err = run(f"{sys.executable} -m speedtest --simple")
    if code != 0:
        console.print("[yellow]Instale o speedtest-cli: pip install speedtest-cli[/yellow]")
        console.print(f"[red]Erro:[/red] {err or out}")
        return code
    console.print(Panel(out, title="Speedtest"))
    return 0

def cmd_diagnose(args):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = REPORTS / f"diagnostico-{ts}.txt"
    blocks = []

    # OS info
    blocks.append(f"Sistema: {platform.platform()} | Python: {platform.python_version()}")

    # Status
    os_name = platform.system()
    if os_name == "Windows":
        code, out, err = run("ipconfig /all")
    else:
        code, out, err = run("ifconfig || ip a", shell=True)
    blocks.append("\n=== STATUS DE REDE ===\n" + (out or err))

    # Ping
    for t in ["1.1.1.1", "8.8.8.8", "google.com"]:
        count_flag = "-n" if os_name == "Windows" else "-c"
        code, out, err = run([f"ping", count_flag, "4", t], shell=False)
        blocks.append(f"\n=== PING {t} ===\n" + (out or err))

    # DNS resolve test
    code, out, err = run(["nslookup", "google.com"], shell=False)
    blocks.append("\n=== NSLOOKUP google.com ===\n" + (out or err))

    report.write_text("\n\n".join(blocks), encoding="utf-8")
    console.print(f"[green]Relatório salvo em:[/green] {report}")
    return 0

def cmd_fix(args):
    if platform.system() != "Windows":
        console.print("[yellow]No momento, 'fix' implementado apenas no Windows.[/yellow]")
        return 0

    if args.flushdns:
        console.print("[bold]Executando:[/bold] ipconfig /flushdns")
        run("ipconfig /flushdns")

    if args.winsock:
        console.print("[bold]Executando:[/bold] netsh winsock reset (requer reiniciar)")
        # Isso precisa ser executado com privilégios de administrador
        run("netsh winsock reset") 

    if not args.flushdns and not args.winsock:
        console.print("[cyan]Nada a fazer. Use --flushdns e/ou --winsock[/cyan]")
    else:
        console.print("[green]Concluído. Reinicie o PC se solicitado.[/green]")
    return 0

# ==============================================================================
# 3. Funções de Monitoramento de Qualidade de Conexão (Novo)
# ==============================================================================

def _measure_latency(target, count=4):
    """
    Mede a latência, perda de pacotes e jitter para um alvo.
    Retorna (min_lat, avg_lat, max_lat, loss_rate, jitter, code).
    """
    ping_command = ["ping"]
    if platform.system() == "Windows":
        # -n para count, -w para timeout em milissegundos
        ping_command += ["-n", str(count), "-w", "1000"] 
        # O ping do Windows não suporta intervalo rápido, usa o padrão (1 segundo)
    else:
        # -c para count, -i para intervalo de 0.2 segundos para ser mais rápido
        ping_command += ["-c", str(count), "-i", "0.2"] 
    ping_command.append(target)

    # Usa shell=False para o subprocess.run do ping
    code, out, err = run(ping_command, shell=False)
    
    if code != 0:
        # Tenta extrair perda de pacotes mesmo em erro
        loss_match = re.search(r"(\d+)%\s+packet loss", out + err)
        loss_rate = int(loss_match.group(1)) if loss_match else 100
        return None, None, None, loss_rate, None, 1

    latencies = []
    
    # Simples parsing do output do ping para extrair tempos
    if platform.system() == "Windows":
        # Expressão para 'tempo=XXms' (Win)
        matches = re.findall(r"tempo=(\d+)ms", out)
        latencies = [int(m) for m in matches]
    else:
        # Expressão para 'time=XX.X ms' (Unix)
        matches = re.findall(r"time=(\d+\.?\d*)\s+ms", out)
        latencies = [float(m) for m in matches]

    # Tentativa de extrair perda de pacotes da linha de resumo
    loss_match = re.search(r"(\d+)%\s+packet loss", out)
    loss_rate = int(loss_match.group(1)) if loss_match else 100

    if not latencies:
        return None, None, None, loss_rate, None, 1

    min_lat = min(latencies)
    max_lat = max(latencies)
    avg_lat = sum(latencies) / len(latencies)
    
    # Cálculo do Jitter (variação média entre latências consecutivas)
    jitter = 0
    if len(latencies) > 1:
        # Calcula a diferença absoluta entre latências consecutivas
        diffs = [abs(latencies[i] - latencies[i-1]) for i in range(1, len(latencies))]
        # O jitter é a média dessas diferenças
        jitter = sum(diffs) / len(diffs) if diffs else 0
        
    return min_lat, avg_lat, max_lat, loss_rate, jitter, 0


def _get_quality_alert(avg_lat, loss_rate, jitter):
    """Retorna uma string de alerta de qualidade de conexão baseado em limites típicos."""
    alerts = []
    
    # Limites típicos para VoIP/Jogos (valores em milissegundos)
    LATENCY_LIMIT = 150 # Ruim > 150ms
    LOSS_LIMIT = 5      # Ruim > 5%
    JITTER_LIMIT = 30   # Ruim > 30ms

    if loss_rate >= LOSS_LIMIT:
        alerts.append(f"[bold red]ALERTA: Perda de Pacotes Alta ({loss_rate:.1f}%)![/bold red]")
    elif loss_rate > 1:
        alerts.append(f"[yellow]Atenção: Perda de Pacotes Moderada ({loss_rate:.1f}%).[/yellow]")

    if avg_lat >= LATENCY_LIMIT:
        alerts.append(f"[bold red]ALERTA: Latência Muito Alta ({avg_lat:.1f}ms)![/bold red]")
    elif avg_lat > 50:
        alerts.append(f"[yellow]Atenção: Latência Elevada ({avg_lat:.1f}ms).[/yellow]")

    if jitter >= JITTER_LIMIT:
        alerts.append(f"[bold red]ALERTA: Jitter Extremo ({jitter:.1f}ms)![/bold red]")
    elif jitter > 10:
        alerts.append(f"[yellow]Atenção: Jitter Moderado ({jitter:.1f}ms).[/yellow]")
        
    if not alerts:
        alerts.append("[green]Qualidade de Conexão Ótima.[/green]")
        
    return " | ".join(alerts)

def cmd_monitor(args):
    target = args.target or "1.1.1.1"
    duration = args.duration
    interval = args.interval
    
    console.print(f"[bold blue]Monitorando:[/bold blue] {target} (Intervalo: {interval}s, Duração: {duration}s)")
    
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration:
            # Medição contínua. 4 pings por medição
            min_lat, avg_lat, max_lat, loss_rate, jitter, code = _measure_latency(target, count=4)
            
            current_ts = datetime.now().strftime('%H:%M:%S')

            if code != 0 or avg_lat is None:
                # Falhou completamente (target não existe, firewall, etc)
                console.print(f"[{current_ts}] [red]Falha na Medição para {target}.[/red] Perda: {loss_rate:.1f}%")
            else:
                alert_status = _get_quality_alert(avg_lat, loss_rate, jitter)
                
                # Exibe a tabela de métricas (usa Columns da rich para um layout limpo)
                try:
                    data_panel = Panel(
                        Columns([
                            f"[cyan]Latência Média:[/cyan] [bold white]{avg_lat:.1f}ms[/bold white]",
                            f"[cyan]Jitter:[/cyan] [bold white]{jitter:.1f}ms[/bold white]",
                            f"[cyan]Perda:[/cyan] [bold white]{loss_rate:.1f}%[/bold white]",
                        ], equal=True),
                        title=f"Métricas ({current_ts})",
                        border_style="blue"
                    )
                    console.print(data_panel)
                except NameError:
                    # Fallback simples
                    console.print(f"[{current_ts}] Avg Lat: {avg_lat:.1f}ms | Jitter: {jitter:.1f}ms | Loss: {loss_rate:.1f}%")
                    
                # Exibe o alerta de qualidade
                console.print(alert_status)
                
            time.sleep(interval)
            
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Monitoramento encerrado pelo usuário.[/bold yellow]")
        
    return 0


# ==============================================================================
# 4. Funções de Tickets (open, list, view)
# ==============================================================================

def _load_db():
    if TICKETS_DB.exists():
        try:
            return json.loads(TICKETS_DB.read_text(encoding="utf-8"))
        except Exception:
            return {"tickets": []}
    return {"tickets": []}

def _save_db(db):
    TICKETS_DB.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def _gen_protocol(prefix=None):
    prefix = prefix or os.getenv("PROTOCOL_PREFIX", "OKA")
    day = datetime.now().strftime("%Y%m%d") # Formato sem hífens para simplificar
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{day}-{suffix}"

def _render_template(path, mapping):
    txt = Path(path).read_text(encoding="utf-8")
    for k, v in mapping.items():
        txt = txt.replace("${" + k + "}", str(v))
    return txt

def _send_email(subject, body, to_addr, from_addr=None, html_body=None):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASS")
    from_addr = from_addr or os.getenv("SUPPORT_FROM", user or "no-reply@example.com")

    if not (host and port and user and pwd and to_addr):
        console.print("[yellow]SMTP não configurado corretamente (.env). Pulando envio.[/yellow]")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        return True
    except Exception as e:
        console.print(f"[red]Erro ao enviar e-mail:[/red] {e}")
        return False


def cmd_ticket_open(args):
    company = os.getenv("COMPANY_NAME", "Okamoto Security Labs")
    protocol = _gen_protocol()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not args.client_name or not args.client_email or not args.summary:
        console.print("[red]--client-name, --client-email e --summary são obrigatórios[/red]")
        return 2

    # Verifica o mutually exclusive group
    if args.physical and args.logical:
        console.print("[red]Use apenas --physical OU --logical, não ambos.[/red]")
        return 2
        
    category = "Físico" if args.physical else "Lógico" # Já garantido que um foi passado

    ticket = {
        "id": protocol,
        "client_name": args.client_name,
        "client_email": args.client_email,
        "summary": args.summary,
        "category": category,
        "created_at": created_at,
        "status": "Recebido"
    }

    db = _load_db()
    db["tickets"].append(ticket)
    _save_db(db)

    console.print(f"[green]Ticket criado:[/green] {protocol} — {category}")

    if args.no_email:
        console.print("[cyan]Envio de e-mails desativado (--no-email).[/cyan]")
        return 0

    # Mapeamento de variáveis para templates
    mapping = {
        "PROTOCOL": protocol,
        "COMPANY_NAME": company,
        "CLIENT_NAME": args.client_name,
        "CLIENT_EMAIL": args.client_email,
        "SUMMARY": args.summary,
        "CATEGORY": category,
        "CREATED_AT": created_at,
    }
    
    # 1. E-mail para cliente
    client_txt = _render_template(TEMPLATES / "email_client.txt", mapping)
    client_html = None
    if (TEMPLATES / "email_client.html").exists():
        client_html = _render_template(TEMPLATES / "email_client.html", mapping)
        
    # Extrai o assunto (primeira linha que contenha "Assunto:")
    first_line_c, _, body_rest_c = client_txt.partition("\n")
    subject_client = first_line_c.replace("Assunto:", "").strip() if "Assunto:" in first_line_c else f"Protocolo {protocol} Recebido"
    sent_client = _send_email(subject_client, body_rest_c.strip(), args.client_email, html_body=client_html)

    # 2. E-mail para equipe de suporte
    support_txt = _render_template(TEMPLATES / "email_support.txt", mapping)
    support_html = None
    if (TEMPLATES / "email_support.html").exists():
        support_html = _render_template(TEMPLATES / "email_support.html", mapping)
        
    first_line_s, _, body_rest_s = support_txt.partition("\n")
    subject_support = first_line_s.replace("Assunto:", "").strip() if "Assunto:" in first_line_s else f"[{protocol}] Novo Chamado ({category})"
    
    team = os.getenv("SUPPORT_TEAM_EMAIL")
    sent_support = False
    if team:
        sent_support = _send_email(subject_support, body_rest_s.strip(), team, html_body=support_html)

    console.print(f"[blue]E-mails[/blue] → Cliente: {'OK' if sent_client else 'SKIP/FAIL'} | Equipe: {'OK' if sent_support else 'SKIP/FAIL'}")
    return 0

def cmd_ticket_list(args):
    db = _load_db()
    if not db["tickets"]:
        console.print("[yellow]Nenhum ticket.[/yellow]")
        return 0
    try:
        table = Table(title="Tickets")
        for col in ["ID","Cliente","Categoria","Status","Criado em"]:
            table.add_column(col)
        for t in db["tickets"]:
            table.add_row(t["id"], t["client_name"], t["category"], t["status"], t["created_at"])
        console.print(table)
    except Exception:
        # Fallback se rich falhar ou for SimpleConsole
        for t in db["tickets"]:
            console.print(f"- {t['id']} | {t['client_name']} | {t['category']} | {t['status']} | {t['created_at']}")
    return 0

def cmd_ticket_view(args):
    db = _load_db()
    tid = args.id
    for t in db["tickets"]:
        if t["id"] == tid:
            console.print(json.dumps(t, ensure_ascii=False, indent=2))
            return 0
    console.print("[red]Ticket não encontrado.[/red]")
    return 1

# ==============================================================================
# 5. Configuração do Parser (Argumentos de Linha de Comando)
# ==============================================================================

def build_parser():
    p = argparse.ArgumentParser(description="Reparador de Wi‑Fi — utilitários de rede")
    sub = p.add_subparsers(dest="cmd")

    # --- Comandos de Rede ---
    s1 = sub.add_parser("status", help="Exibe informações de rede")
    s1.set_defaults(func=cmd_status)

    s2 = sub.add_parser("ping", help="Ping para destinos comuns")
    s2.add_argument("targets", nargs="*", help="Alvos (ex: 1.1.1.1 8.8.8.8)")
    s2.set_defaults(func=cmd_ping)

    s3 = sub.add_parser("speedtest", help="Executa speedtest-cli (requer instalação)")
    s3.set_defaults(func=cmd_speedtest)

    s4 = sub.add_parser("diagnose", help="Gera relatório de diagnóstico")
    s4.set_defaults(func=cmd_diagnose)

    s5 = sub.add_parser("fix", help="Ações de reparo (Windows)")
    s5.add_argument("--flushdns", action="store_true", help="Executa ipconfig /flushdns")
    s5.add_argument("--winsock", action="store_true", help="Executa netsh winsock reset")
    s5.set_defaults(func=cmd_fix)

    # --- NOVO: Monitoramento em Tempo Real ---
    s6 = sub.add_parser("monitor", help="Mede latência, jitter e perda de pacotes em tempo real.")
    s6.add_argument("target", nargs="?", default="1.1.1.1", help="Alvo para monitorar (padrão: 1.1.1.1)")
    s6.add_argument("--duration", type=int, default=60, help="Duração total do monitoramento em segundos (padrão: 60)")
    s6.add_argument("--interval", type=int, default=5, help="Intervalo entre as medições em segundos (padrão: 5)")
    s6.set_defaults(func=cmd_monitor)

    # --- Comandos de Tickets ---
    t = sub.add_parser("ticket", help="Gerenciar tickets (abertura, listagem, visualização)")
    tsub = t.add_subparsers(dest="ticket_cmd")

    t_open = tsub.add_parser("open", help="Abre um ticket e (opcionalmente) envia e-mails")
    t_open.add_argument("--client-name", required=True, help="Nome do cliente")
    t_open.add_argument("--client-email", required=True, help="E-mail do cliente")
    t_open.add_argument("--summary", required=True, help="Resumo do problema")
    # Garante que seja físico OU lógico, não ambos ou nenhum.
    grp = t_open.add_mutually_exclusive_group(required=True) 
    grp.add_argument("--physical", action="store_true", help="Problema físico (cabo/porta/fonte)")
    grp.add_argument("--logical", action="store_true", help="Problema lógico (config/DNS/etc.)")
    t_open.add_argument("--no-email", action="store_true", help="Não enviar e-mails (apenas grava no DB)")
    t_open.set_defaults(func=cmd_ticket_open)

    t_list = tsub.add_parser("list", help="Lista tickets")
    t_list.set_defaults(func=cmd_ticket_list)

    t_view = tsub.add_parser("view", help="Mostra um ticket específico")
    t_view.add_argument("--id", required=True, help="ID/Protocolo do ticket")
    t_view.set_defaults(func=cmd_ticket_view)

    return p

# ==============================================================================
# 6. Ponto de Entrada
# ==============================================================================

def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    sys.exit(args.func(args))

if __name__ == "__main__":
    main()
