import argparse
import platform
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
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

def run(cmd, shell=True):
    try:
        res = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def cmd_status(args):
    os_name = platform.system()
    if os_name == "Windows":
        code, out, err = run("ipconfig /all")
    else:
        code, out, err = run("ifconfig || ip a")
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
        code, out, err = run(f"ping {count_flag} 4 {t}")
        if code == 0:
            console.print(out)
        else:
            console.print(f"[red]Falhou:[/red] {err or out}")
    return 0

def cmd_speedtest(args):
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
        code, out, err = run("ifconfig || ip a")
    blocks.append("\n=== STATUS DE REDE ===\n" + (out or err))

    # Ping
    for t in ["1.1.1.1", "8.8.8.8", "google.com"]:
        count_flag = "-n" if os_name == "Windows" else "-c"
        code, out, err = run(f"ping {count_flag} 4 {t}")
        blocks.append(f"\n=== PING {t} ===\n" + (out or err))

    # DNS resolve test
    code, out, err = run("nslookup google.com")
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
        run("netsh winsock reset")

    if not args.flushdns and not args.winsock:
        console.print("[cyan]Nada a fazer. Use --flushdns e/ou --winsock[/cyan]")
    else:
        console.print("[green]Concluído. Reinicie o PC se solicitado.[/green]")
    return 0


import smtplib
from email.message import EmailMessage
import json
import random
import string
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TEMPLATES = ROOT / "templates"
TICKETS_DB = ROOT / "tickets" / "tickets_db.json"
TICKETS_DB.parent.mkdir(exist_ok=True)

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
    day = datetime.now().strftime("%Y-%m-%d")
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

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    return True

def cmd_ticket_open(args):
    company = os.getenv("COMPANY_NAME", "Okamoto Security Labs")
    protocol = _gen_protocol()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not args.client_name or not args.client_email or not args.summary:
        console.print("[red]--client-name, --client-email e --summary são obrigatórios[/red]")
        return 2

    category = "Físico" if args.physical else "Lógico"

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

    # E-mail para cliente
    mapping = {
        "PROTOCOL": protocol,
        "COMPANY_NAME": company,
        "CLIENT_NAME": args.client_name,
        "CLIENT_EMAIL": args.client_email,
        "SUMMARY": args.summary,
        "CATEGORY": category,
        "CREATED_AT": created_at,
    }
    client_txt = _render_template(TEMPLATES / "email_client.txt", mapping)
    client_html = None
    if (TEMPLATES / "email_client.html").exists():
        client_html = _render_template(TEMPLATES / "email_client.html", mapping)
    # Primeira linha "Assunto: ..." como subject
    first_line, _, body_rest = client_txt.partition("\n")
    subject_client = first_line.replace("Assunto:", "").strip() if "Assunto:" in first_line else f"Protocolo {protocol}"
    sent_client = _send_email(subject_client, body_rest.strip(), args.client_email, html_body=client_html)

    # E-mail para equipe
    support_txt = _render_template(TEMPLATES / "email_support.txt", mapping)
    support_html = None
    if (TEMPLATES / "email_support.html").exists():
        support_html = _render_template(TEMPLATES / "email_support.html", mapping)
    first_line_s, _, body_rest_s = support_txt.partition("\n")
    subject_support = first_line_s.replace("Assunto:", "").strip() if "Assunto:" in first_line_s else f"[{protocol}] Novo chamado"
    team = os.getenv("SUPPORT_TEAM_EMAIL")
    sent_support = False
    if team:
        sent_support = _send_email(subject_support, body_rest_s.strip(), team, html_body=support_html)

    console.print(f"[blue]E-mails[/blue] → Cliente: {'OK' if sent_client else 'skip'} | Equipe: {'OK' if sent_support else 'skip'}")
    return 0

def cmd_ticket_list(args):
    db = _load_db()
    if not db["tickets"]:
        console.print("[yellow]Nenhum ticket.[/yellow]")
        return 0
    try:
        from rich.table import Table
        table = Table(title="Tickets")
        for col in ["ID","Cliente","Categoria","Status","Criado em"]:
            table.add_column(col)
        for t in db["tickets"]:
            table.add_row(t["id"], t["client_name"], t["category"], t["status"], t["created_at"])
        console.print(table)
    except Exception:
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

def build_parser():
    p = argparse.ArgumentParser(description="Reparador de Wi‑Fi — utilitários de rede")
    sub = p.add_subparsers(dest="cmd")

    s1 = sub.add_parser("status", help="Exibe informações de rede")
    s1.set_defaults(func=cmd_status)

    s2 = sub.add_parser("ping", help="Ping para destinos comuns")
    s2.add_argument("targets", nargs="*", help="Alvos (ex: 1.1.1.1 8.8.8.8)")
    s2.set_defaults(func=cmd_ping)

    s3 = sub.add_parser("speedtest", help="Executa speedtest-cli")
    s3.set_defaults(func=cmd_speedtest)

    s4 = sub.add_parser("diagnose", help="Gera relatório de diagnóstico")
    s4.set_defaults(func=cmd_diagnose)

    s5 = sub.add_parser("fix", help="Ações de reparo (Windows)")
    s5.add_argument("--flushdns", action="store_true", help="Executa ipconfig /flushdns")
    s5.add_argument("--winsock", action="store_true", help="Executa netsh winsock reset")
    s5.set_defaults(func=cmd_fix)

    # === Tickets ===
    t = sub.add_parser("ticket", help="Gerenciar tickets (abertura, listagem, visualização)")
    tsub = t.add_subparsers(dest="ticket_cmd")

    t_open = tsub.add_parser("open", help="Abre um ticket e (opcionalmente) envia e-mails")
    t_open.add_argument("--client-name", required=True, help="Nome do cliente")
    t_open.add_argument("--client-email", required=True, help="E-mail do cliente")
    t_open.add_argument("--summary", required=True, help="Resumo do problema")
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

def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    sys.exit(args.func(args))

if __name__ == "__main__":
    main()
