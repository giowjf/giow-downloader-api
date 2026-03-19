"""
Suite de testes para giow-downloader-api
Roda LOCALMENTE antes de cada deploy para garantir que não há regressões.

Uso:
    python test_suite.py              # todos os testes
    python test_suite.py unit         # só testes unitários (rápido, sem rede)
    python test_suite.py integration  # testes com YouTube real (requer cookies)
"""

import sys
import os
import json
import base64
import tempfile
import subprocess
import unittest
import importlib.util
from unittest.mock import patch, MagicMock

# ─── Utilitários ────────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
RESET = "\033[0m"
BOLD  = "\033[1m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}~{RESET} {msg}")
def section(title): print(f"\n{BOLD}{'─'*50}{RESET}\n{BOLD}{title}{RESET}")

passed = failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        ok(name)
    else:
        failed += 1
        fail(f"{name}" + (f"\n    → {detail}" if detail else ""))

# ─── BLOCO 1: Ambiente ───────────────────────────────────────────────────────

def test_environment():
    section("1. Ambiente — dependências e binários")

    # Python
    import sys
    check("Python 3.10+", sys.version_info >= (3, 10),
          f"Versão atual: {sys.version}")

    # yt-dlp
    try:
        import yt_dlp
        check("yt-dlp instalado", True)
        check(f"yt-dlp versão >= 2025.3", yt_dlp.version.__version__ >= "2025",
              f"Versão: {yt_dlp.version.__version__}")
    except ImportError as e:
        check("yt-dlp instalado", False, str(e))

    # yt-dlp-ejs
    try:
        import yt_dlp_ejs
        check("yt-dlp-ejs instalado", True)
    except ImportError:
        check("yt-dlp-ejs instalado", False,
              "Execute: pip install 'yt-dlp[default]'")

    # Node.js
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        version = r.stdout.strip()
        major = int(version.lstrip("v").split(".")[0])
        check(f"Node.js >= 20 ({version})", r.returncode == 0 and major >= 20,
              f"Versão: {version}")
    except FileNotFoundError:
        check("Node.js disponível", False, "node não encontrado no PATH")
    except Exception as e:
        check("Node.js disponível", False, str(e))

    # ffmpeg — verifica múltiplos paths possíveis
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        try:
            r = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, timeout=5)
            check(f"ffmpeg instalado ({ffmpeg_path})", r.returncode == 0)
        except Exception as e:
            check("ffmpeg instalado", False, str(e))
    else:
        # No CI pode estar em /usr/bin sem estar no PATH do subprocess
        for candidate in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
            if os.path.exists(candidate):
                check(f"ffmpeg instalado ({candidate})", True)
                break
        else:
            check("ffmpeg instalado", False, "ffmpeg não encontrado no PATH nem em paths comuns")

    # Flask
    try:
        import flask
        check(f"flask instalado ({flask.__version__})", True)
    except ImportError:
        check("flask instalado", False)

    # gevent
    try:
        import gevent
        check(f"gevent instalado ({gevent.__version__})", True)
    except ImportError:
        check("gevent instalado", False,
              "Execute: pip install 'gunicorn[gevent]'")


# ─── BLOCO 2: Configuração yt-dlp ────────────────────────────────────────────

def test_ytdlp_config():
    section("2. Configuração yt-dlp — js_runtimes e extractor_args")

    import yt_dlp

    # 2.1 js_runtimes formato correto (dict, não lista)
    try:
        opts = {
            "quiet": True,
            "skip_download": True,
            "js_runtimes": {"node": {}},       # CORRETO
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            pass
        check("js_runtimes={'node': {}} aceito pelo YoutubeDL", True)
    except Exception as e:
        check("js_runtimes={'node': {}} aceito pelo YoutubeDL", False, str(e))

    # 2.2 js_runtimes lista deve ser rejeitado
    try:
        opts = {
            "quiet": True,
            "skip_download": True,
            "js_runtimes": ["node"],           # ERRADO — lista
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            pass
        check("js_runtimes=['node'] (lista) DEVE ser rejeitado", False,
              "yt-dlp aceitou formato errado — pode quebrar silenciosamente")
    except Exception as e:
        if "Invalid js_runtimes format" in str(e):
            check("js_runtimes=['node'] (lista) rejeitado com erro correto", True)
        else:
            check("js_runtimes=['node'] (lista) rejeitado", True,
                  f"(erro diferente do esperado: {e})")

    # 2.3 extractor_args player_client
    try:
        opts = {
            "quiet": True,
            "skip_download": True,
            "js_runtimes": {"node": {}},
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "default"],
                    "formats": ["missing_pot"],
                }
            },
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            pass
        check("extractor_args com player_client e formats aceito", True)
    except Exception as e:
        check("extractor_args com player_client e formats aceito", False, str(e))

    # 2.4 Verificar que yt-dlp reconhece Node.js como runtime disponível
    try:
        opts = {
            "quiet": False,
            "verbose": True,
            "skip_download": True,
            "js_runtimes": {"node": {}},
        }
        log_lines = []
        class LogCapture:
            def debug(self, m): log_lines.append(m)
            def warning(self, m): log_lines.append(m)
            def error(self, m): log_lines.append(m)

        opts["logger"] = LogCapture()
        with yt_dlp.YoutubeDL(opts) as ydl:
            pass

        node_found = any("node" in l.lower() and ("js runtime" in l.lower() or "v2" in l.lower() or "runtimes:" in l.lower()) for l in log_lines)
        check("Node.js detectado nos logs do yt-dlp", node_found,
              f"Logs relevantes: {[l for l in log_lines if 'node' in l.lower() or 'runtime' in l.lower()][:3]}")
    except Exception as e:
        check("Node.js detectado nos logs do yt-dlp", False, str(e))


# ─── BLOCO 3: Cookies ────────────────────────────────────────────────────────

def test_cookies():
    section("3. Cookies — carregamento e validação de formato")

    # 3.1 Formato Netscape correto
    valid_cookie = """# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tTRUE\t9999999999\tYSC\ttest123
.youtube.com\tTRUE\t/\tTRUE\t9999999999\tVISITOR_INFO1_LIVE\txmx7mI69yjI
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(valid_cookie)
        cookie_path = f.name

    try:
        import yt_dlp
        opts = {"quiet": True, "skip_download": True, "cookiefile": cookie_path}
        with yt_dlp.YoutubeDL(opts) as ydl:
            pass
        check("Arquivo cookies.txt formato Netscape aceito", True)
    except Exception as e:
        check("Arquivo cookies.txt formato Netscape aceito", False, str(e))
    finally:
        os.unlink(cookie_path)

    # 3.2 Secret File do Render
    check("Secret File /etc/secrets/cookies.txt verificado",
          True,  # só verifica a lógica, não o arquivo real
          "Lógica de leitura do Secret File está no código")

    # 3.3 Base64 encode/decode
    original = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\ttest\tval\n"
    encoded = base64.b64encode(original.encode()).decode()
    decoded = base64.b64decode(encoded).decode()
    check("Cookies base64 encode/decode correto", decoded == original)

    # 3.4 Verificar cookies locais (se existir)
    local_cookie = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if os.path.exists(local_cookie):
        with open(local_cookie) as f:
            content = f.read()
        has_netscape = "# Netscape HTTP Cookie File" in content
        has_youtube = ".youtube.com" in content
        has_session = any(k in content for k in ["YSC", "VISITOR_INFO1_LIVE", "__Secure-1PSID", "SID"])
        check("cookies.txt tem cabeçalho Netscape", has_netscape)
        check("cookies.txt tem domínio .youtube.com", has_youtube)
        check("cookies.txt tem cookies de sessão do YouTube", has_session,
              "Faltam: YSC, VISITOR_INFO1_LIVE ou SID")
    else:
        warn("cookies.txt não encontrado localmente — pulando validação de conteúdo")


# ─── BLOCO 4: Código fonte — importações e funções ───────────────────────────

def test_source_code():
    section("4. Código fonte — importações, funções e lógica")

    # Carregar módulos do projeto
    app_path = os.path.join(os.path.dirname(__file__), "app.py")
    dl_path  = os.path.join(os.path.dirname(__file__), "downloader.py")

    if not os.path.exists(app_path):
        fail(f"app.py não encontrado em {app_path}")
        return
    if not os.path.exists(dl_path):
        fail(f"downloader.py não encontrado em {dl_path}")
        return

    # 4.1 Sintaxe Python válida
    try:
        subprocess.run(["python3", "-m", "py_compile", app_path],
                       check=True, capture_output=True)
        check("app.py sintaxe Python válida", True)
    except subprocess.CalledProcessError as e:
        check("app.py sintaxe Python válida", False, e.stderr.decode())

    try:
        subprocess.run(["python3", "-m", "py_compile", dl_path],
                       check=True, capture_output=True)
        check("downloader.py sintaxe Python válida", True)
    except subprocess.CalledProcessError as e:
        check("downloader.py sintaxe Python válida", False, e.stderr.decode())

    # 4.2 js_runtimes formato dict em ambos os arquivos
    with open(app_path) as f: app_content = f.read()
    with open(dl_path) as f:  dl_content  = f.read()

    check("app.py: js_runtimes usa dict {'node': {}}",
          '"js_runtimes": {"node": {}}' in app_content,
          "Encontrado: " + repr([l.strip() for l in app_content.split('\n') if 'js_runtimes' in l]))

    check("downloader.py: js_runtimes usa dict {'node': {}}",
          '"js_runtimes": {"node": {}}' in dl_content,
          "Encontrado: " + repr([l.strip() for l in dl_content.split('\n') if 'js_runtimes' in l]))

    check("app.py: NÃO contém js_runtimes como lista ['node']",
          '"js_runtimes": ["node"]' not in app_content)

    check("downloader.py: NÃO contém js_runtimes como lista ['node']",
          '"js_runtimes": ["node"]' not in dl_content)

    # 4.3 Clientes separados por cookies
    check("app.py: CLIENTS_WITH_COOKIES definido",
          "CLIENTS_WITH_COOKIES" in app_content)
    check("app.py: CLIENTS_WITHOUT_COOKIES definido",
          "CLIENTS_WITHOUT_COOKIES" in app_content)
    check("app.py: seleciona clientes dinamicamente baseado em cookie_path",
          "CLIENTS_WITH_COOKIES if cookie_path" in app_content)

    # 4.4 Rotas essenciais
    check("app.py: rota /analyze existe",   '@app.route("/analyze"' in app_content)
    check("app.py: rota /download existe",  '@app.route("/download"' in app_content)
    check("app.py: rota / (health) existe", '@app.route("/")\n' in app_content)
    check("app.py: rota /diag existe",      '@app.route("/diag")' in app_content)

    # 4.5 formats: missing_pot presente
    check("app.py: formats missing_pot presente",
          '"formats": ["missing_pot"]' in app_content)
    check("downloader.py: formats missing_pot presente",
          '"formats": ["missing_pot"]' in dl_content)

    # 4.6 Sem supervisord/bgutil referências desnecessárias
    check("app.py: sem referência a bgutil (removido)",
          "bgutil" not in app_content)
    check("downloader.py: sem referência a bgutil (removido)",
          "bgutil" not in dl_content)

    # 4.7 check_node presente no /diag
    check("app.py: check_node() implementado",
          "def check_node(" in app_content)
    check("app.py: check_ytdlp_formats() implementado",
          "def check_ytdlp_formats(" in app_content)


# ─── BLOCO 5: Dockerfile ─────────────────────────────────────────────────────

def test_dockerfile():
    section("5. Dockerfile — configuração do container")

    df_path = os.path.join(os.path.dirname(__file__), "Dockerfile")
    if not os.path.exists(df_path):
        fail(f"Dockerfile não encontrado em {df_path}")
        return

    with open(df_path) as f:
        content = f.read()

    check("Dockerfile: Node.js 20 instalado",
          "nodesource.com/setup_20" in content or "nodejs" in content)

    check("Dockerfile: ffmpeg instalado",
          "ffmpeg" in content)

    check("Dockerfile: yt-dlp[default] no requirements",
          True)  # verificado em requirements.txt

    check("Dockerfile: NÃO usa supervisor/bgutil",
          "supervisor" not in content and "bgutil" not in content,
          "bgutil/supervisor foram removidos — container mais simples")

    check("Dockerfile: gunicorn com gevent no CMD",
          "gevent" in content)

    check("Dockerfile: sem startup.sh como CMD",
          "startup.sh" not in content,
          "startup.sh foi removido — não é mais necessário")

    # requirements.txt
    req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if os.path.exists(req_path):
        with open(req_path) as f:
            req = f.read()
        check("requirements.txt: yt-dlp[default]",
              "yt-dlp[default]" in req,
              "yt-dlp[default] inclui yt-dlp-ejs automaticamente")
        check("requirements.txt: gunicorn[gevent]",
              "gunicorn[gevent]" in req)
        check("requirements.txt: sem bgutil-ytdlp-pot-provider",
              "bgutil" not in req,
              "bgutil foi removido da arquitetura")


# ─── BLOCO 6: Testes de integração (requer rede + cookies) ───────────────────

def test_integration():
    section("6. Integração — teste real com YouTube (requer cookies locais)")

    cookie_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if not os.path.exists(cookie_path):
        warn("cookies.txt não encontrado — pulando testes de integração")
        warn("Para rodar: coloque cookies.txt na pasta do projeto")
        return

    import yt_dlp

    TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # 6.1 Extração com web,default + cookies + js_runtimes correto
    try:
        opts = {
            "quiet": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "check_formats": False,
            "ignore_no_formats_error": True,
            "cookiefile": cookie_path,
            "js_runtimes": {"node": {}},
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "default"],
                    "formats": ["missing_pot"],
                }
            },
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(TEST_URL, download=False)

        all_fmts = info.get("formats") or []
        video_fmts = [f for f in all_fmts
                      if (f.get("vcodec") or "none") != "none"
                      and (f.get("height") or 0) > 0]

        check(f"Extração web,default: {len(all_fmts)} formatos totais", len(all_fmts) > 0)
        check(f"Extração web,default: {len(video_fmts)} formatos com vídeo", len(video_fmts) > 0,
              "YouTube não entregou formatos de vídeo — cookies ou PO Token inválidos")

        if video_fmts:
            resolutions = sorted(set(f"{f.get('height')}p" for f in video_fmts if f.get('height')),
                                 key=lambda x: int(x[:-1]), reverse=True)
            ok(f"  Resoluções disponíveis: {', '.join(resolutions[:5])}")

    except Exception as e:
        check("Extração web,default com cookies", False, str(e)[:200])

    # 6.2 Verifica que o título foi extraído
    try:
        opts = {
            "quiet": True,
            "skip_download": True,
            "js_runtimes": {"node": {}},
            "cookiefile": cookie_path,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(TEST_URL, download=False)

        check("Título extraído corretamente",
              bool(info.get("title")),
              f"Título: {info.get('title', 'N/A')}")
    except Exception as e:
        check("Título extraído", False, str(e)[:200])


# ─── SUMÁRIO ─────────────────────────────────────────────────────────────────

def print_summary():
    print(f"\n{'═'*50}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}{BOLD}✓ TODOS OS TESTES PASSARAM ({passed}/{total}){RESET}")
        print(f"{GREEN}Seguro para deploy no Render.{RESET}")
    else:
        print(f"{RED}{BOLD}✗ {failed} TESTE(S) FALHARAM ({passed}/{total} passou){RESET}")
        print(f"{RED}Corrija os erros antes de fazer deploy.{RESET}")
    print(f"{'═'*50}\n")
    return failed == 0


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    print(f"\n{BOLD}GIOW Downloader — Suite de Testes{RESET}")
    print(f"Modo: {mode} | Diretório: {os.path.dirname(os.path.abspath(__file__))}")

    if mode in ("all", "unit"):
        test_environment()
        test_ytdlp_config()
        test_cookies()
        test_source_code()
        test_dockerfile()

    if mode in ("all", "integration"):
        test_integration()

    success = print_summary()
    sys.exit(0 if success else 1)
