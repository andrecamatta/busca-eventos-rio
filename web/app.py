"""Aplicação web FastAPI para visualização de eventos em calendário."""

import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
LATEST_OUTPUT = OUTPUT_DIR / "latest"
LOG_FILE = BASE_DIR / "busca_eventos.log"

# FastAPI app
app = FastAPI(
    title="Eventos Culturais Rio",
    description="Calendário de eventos culturais no Rio de Janeiro",
    version="1.0.0"
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Scheduler para atualização automática
scheduler = BackgroundScheduler()


def ensure_output_directory():
    """Garante que o diretório base de output existe."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # LATEST_OUTPUT será criado como symlink por EventFileManager
        logger.info(f"✓ Diretório de output verificado: {OUTPUT_DIR}")
    except Exception as e:
        logger.warning(f"Não foi possível criar diretório de output: {e}")


def load_latest_events() -> list[dict]:
    """Carrega os eventos mais recentes do output/latest."""
    try:
        # Garantir que diretório existe
        if not LATEST_OUTPUT.exists():
            logger.info(f"📂 Diretório {LATEST_OUTPUT} não existe. Criando...")
            ensure_output_directory()
            logger.info("ℹ️  Nenhum evento carregado ainda. Execute a busca ou use /api/refresh")
            return []

        # Tentar vários arquivos possíveis
        possible_files = [
            LATEST_OUTPUT / "formatted_output.json",
            LATEST_OUTPUT / "verified_events.json",
            LATEST_OUTPUT / "enriched_events_initial.json",
        ]

        eventos = []
        for file_path in possible_files:
            if file_path.exists():
                logger.info(f"📁 Carregando eventos de: {file_path.name}")
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Extrair eventos (pode ser dict ou list)
                if isinstance(data, list):
                    eventos = data
                elif isinstance(data, dict):
                    # Tentar várias chaves possíveis
                    eventos = (
                        data.get("eventos") or
                        data.get("verified_events") or
                        data.get("enriched_events") or
                        []
                    )

                logger.info(f"✓ Carregados {len(eventos)} eventos de {file_path.name}")
                return eventos

        logger.info(f"ℹ️  Nenhum arquivo de eventos encontrado em {LATEST_OUTPUT}")
        logger.info(f"💡 Execute 'python main.py' ou use /api/refresh para buscar eventos")
        return []

    except Exception as e:
        logger.error(f"❌ Erro ao carregar eventos: {e}")
        return []


def extract_venue_from_local(local: str) -> str:
    """
    Extrai o nome do venue do campo 'local'.

    Formato esperado: "Nome do Venue - Endereço completo"
    Retorna: "Nome do Venue" ou string vazia se não conseguir extrair
    """
    if not local:
        return ""

    # Se contém " - ", extrair a parte antes do primeiro hífen
    if " - " in local:
        venue_name = local.split(" - ")[0].strip()
        return venue_name

    # Se não tem hífen, retornar vazio (local genérico)
    return ""


def parse_event_to_fullcalendar(event: dict) -> dict:
    """Converte evento do formato interno para FullCalendar."""
    try:
        # Parsear data e horário
        data_str = event.get("data", "")
        horario_str = event.get("horario", "00:00")

        # Formato: DD/MM/YYYY
        data_parts = data_str.split("/")
        if len(data_parts) != 3:
            return None

        day, month, year = data_parts
        hora, minuto = horario_str.split(":")

        # ISO format para FullCalendar
        start_datetime = f"{year}-{month}-{day}T{hora}:{minuto}:00"

        # Determinar cor baseado na categoria
        categoria = event.get("categoria", "Geral")

        # Extrair venue do campo 'local' se não existir campo 'venue' direto
        venue = event.get("venue", "")
        if not venue:
            local = event.get("local", "")
            venue = extract_venue_from_local(local)

        # Cores por categoria (granular)
        color_map = {
            "Jazz": "#3498db",  # Azul
            "Música Clássica": "#9b59b6",  # Roxo
            "Teatro": "#e67e22",  # Laranja
            "Comédia": "#e74c3c",  # Vermelho
            "Cinema": "#34495e",  # Cinza escuro
            "Feira Gastronômica": "#f39c12",  # Amarelo/ouro
            "Feira de Artesanato": "#16a085",  # Verde-azulado
            "Outdoor/Parques": "#2ecc71",  # Verde
            "Cursos de Café": "#795548",  # Marrom
            "Geral": "#95a5a6",  # Cinza claro
        }

        # Prioridade: CATEGORIA primeiro, venue como fallback
        if categoria and categoria in color_map:
            color = color_map[categoria]  # Usar cor da categoria
        elif venue:
            color = "#7f8c8d"  # Cinza médio para venues sem categoria
        else:
            color = "#95a5a6"  # Cinza claro default

        return {
            "id": hash(event.get("titulo", "") + data_str + horario_str),
            "title": event.get("titulo", "Sem título"),
            "start": start_datetime,
            "end": start_datetime,  # Eventos pontuais
            "extendedProps": {
                "local": event.get("local", ""),
                "preco": event.get("preco", "Consultar"),
                "link_ingresso": event.get("link_ingresso"),
                "link_type": event.get("link_type", "info"),  # purchase, info, ou venue
                "descricao": event.get("descricao", ""),
                "categoria": categoria,
                "venue": venue,
            },
            "color": color,
            "textColor": "#ffffff",
        }

    except Exception as e:
        logger.error(f"Erro ao parsear evento: {e} - {event}")
        return None


def parse_log_line(line: str) -> Optional[dict]:
    """
    Parseia uma linha de log no formato:
    2025-11-08 15:36:54,176 - module.name - LEVEL - message

    Returns:
        Dict com timestamp, module, level, message ou None se não conseguir parsear
    """
    # Regex para parsear formato de log
    # Formato: YYYY-MM-DD HH:MM:SS,mmm - module - LEVEL - message
    pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^ ]+) - (\w+) - (.+)$'
    match = re.match(pattern, line.strip())

    if match:
        return {
            "timestamp": match.group(1),
            "module": match.group(2),
            "level": match.group(3),
            "message": match.group(4)
        }

    # Se não conseguir parsear, retornar linha raw
    return {
        "timestamp": "",
        "module": "",
        "level": "RAW",
        "message": line.strip()
    }


def run_event_search():
    """Executa a busca de eventos (main.py)."""
    import subprocess
    import shutil

    try:
        # Verificar se API key está configurada
        if not os.getenv("OPENROUTER_API_KEY"):
            logger.error("❌ OPENROUTER_API_KEY não configurada. Busca cancelada.")
            return

        # Determinar comando para executar main.py
        venv_python = BASE_DIR / ".venv" / "bin" / "python"

        if shutil.which("uv"):
            # Se uv está disponível, usar uv run
            cmd = ["uv", "run", "python", "main.py"]
            logger.info(f"🔄 Iniciando busca com uv: {' '.join(cmd)}")
        elif venv_python.exists():
            # Se não tem uv mas tem virtualenv, usar python do venv
            cmd = [str(venv_python), "main.py"]
            logger.info(f"🔄 Iniciando busca com venv python: {' '.join(cmd)}")
        else:
            # Fallback para python do sistema (pode não ter dependências)
            logger.warning("⚠️  Nem uv nem virtualenv encontrados. Tentando python do sistema...")
            cmd = ["python3", "main.py"]
            logger.info(f"🔄 Iniciando busca com python do sistema: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutos
        )

        if result.returncode == 0:
            logger.info("✓ Busca de eventos concluída com sucesso!")
            if result.stdout:
                logger.info(f"stdout: {result.stdout[:500]}")
        else:
            logger.error(f"❌ Erro na busca de eventos (code {result.returncode})")
            if result.stderr:
                logger.error(f"stderr: {result.stderr[:1000]}")
            if result.stdout:
                logger.error(f"stdout: {result.stdout[:1000]}")

    except subprocess.TimeoutExpired:
        logger.error("❌ Busca de eventos excedeu o timeout de 10 minutos")
    except Exception as e:
        logger.error(f"❌ Erro ao executar busca: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()[:1000]}")


@app.on_event("startup")
async def startup_event():
    """Inicializa o scheduler na startup."""
    logger.info("=" * 60)
    logger.info("🚀 INICIANDO APLICAÇÃO EVENTOS CULTURAIS RIO")
    logger.info("=" * 60)

    # Log environment info
    port = os.getenv("PORT", "NOT SET")
    logger.info(f"📌 PORT configurado: {port}")
    logger.info(f"📁 BASE_DIR: {BASE_DIR}")
    logger.info(f"📂 OUTPUT_DIR: {OUTPUT_DIR}")

    # Garantir que diretórios existem
    logger.info("📂 Criando diretórios de output...")
    ensure_output_directory()
    logger.info("✓ Diretórios verificados")

    # Verificar se API key está configurada
    api_key = os.getenv("OPENROUTER_API_KEY")
    logger.info(f"🔑 API Key configurada: {bool(api_key)}")

    if api_key:
        # Agendar busca diária às 6h da manhã
        logger.info("⏰ Configurando scheduler...")
        scheduler.add_job(
            run_event_search,
            trigger="cron",
            hour=6,
            minute=0,
            id="daily_event_search",
            replace_existing=True
        )
        scheduler.start()
        logger.info("✓ Scheduler iniciado - busca automática às 6h")
    else:
        logger.warning("⚠️  OPENROUTER_API_KEY não configurada - scheduler desabilitado")
        logger.info("💡 Configure a variável para habilitar atualização automática")

    logger.info("=" * 60)
    logger.info("✅ APLICAÇÃO PRONTA PARA RECEBER REQUISIÇÕES")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Para o scheduler no shutdown."""
    scheduler.shutdown()
    logger.info("✓ Scheduler parado")


@app.get("/health")
async def health_check():
    """
    Health check endpoint RÁPIDO para Railway e monitoramento.

    Retorna apenas status básico sem operações pesadas de I/O.
    """
    return JSONResponse(content={
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "app": "eventos-culturais-rio"
    })


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Página principal com calendário."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/events")
async def get_events(
    categoria: Optional[str] = None,
    venue: Optional[str] = None
):
    """
    Retorna eventos em formato FullCalendar.

    Query params:
    - categoria: filtrar por categoria (Jazz, Teatro-Comédia, Outdoor-FimDeSemana)
    - venue: filtrar por venue específico
    """
    eventos = load_latest_events()

    # Aplicar filtros
    if categoria:
        eventos = [e for e in eventos if e.get("categoria") == categoria]

    if venue:
        eventos = [e for e in eventos if e.get("venue") == venue]

    # Converter para formato FullCalendar
    calendar_events = []
    for evento in eventos:
        parsed = parse_event_to_fullcalendar(evento)
        if parsed:
            calendar_events.append(parsed)

    return JSONResponse(content=calendar_events)


@app.get("/api/categories")
async def get_categories():
    """Retorna lista de categorias disponíveis."""
    eventos = load_latest_events()
    categorias = set()

    for evento in eventos:
        cat = evento.get("categoria")
        if cat:
            categorias.add(cat)

    return JSONResponse(content=sorted(list(categorias)))


@app.get("/api/venues")
async def get_venues():
    """Retorna lista de venues disponíveis."""
    eventos = load_latest_events()
    venues = set()

    for evento in eventos:
        venue = evento.get("venue")
        if venue:
            venues.add(venue)

    return JSONResponse(content=sorted(list(venues)))


@app.post("/api/refresh")
async def trigger_refresh():
    """Força atualização manual dos eventos."""
    try:
        # Verificar se API key está configurada antes de aceitar a requisição
        if not os.getenv("OPENROUTER_API_KEY"):
            logger.warning("⚠️  Tentativa de atualização sem API key configurada")
            raise HTTPException(
                status_code=503,
                detail="Atualização indisponível: OPENROUTER_API_KEY não configurada. Configure a variável de ambiente para habilitar buscas automáticas."
            )

        # Executar busca em background
        logger.info("📨 Requisição de atualização manual recebida")
        scheduler.add_job(
            run_event_search,
            id="manual_refresh",
            replace_existing=True
        )
        return JSONResponse(content={"status": "success", "message": "Atualização iniciada"})

    except HTTPException:
        # Re-raise HTTP exceptions (como o 503 acima)
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao agendar atualização: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Retorna estatísticas dos eventos."""
    eventos = load_latest_events()

    # Contagens por categoria
    categorias = {}
    venues = {}

    for evento in eventos:
        cat = evento.get("categoria", "Geral")
        categorias[cat] = categorias.get(cat, 0) + 1

        venue = evento.get("venue")
        if venue:
            venues[venue] = venues.get(venue, 0) + 1

    return JSONResponse(content={
        "total_eventos": len(eventos),
        "por_categoria": categorias,
        "por_venue": venues,
        "ultima_atualizacao": datetime.now().isoformat()
    })


@app.get("/api/logs")
async def get_logs(
    lines: int = 100,
    level: Optional[str] = None,
    search: Optional[str] = None,
    reverse: bool = True
):
    """
    Retorna últimas linhas do log de execução com filtros.

    Query params:
    - lines: número de linhas a retornar (padrão: 100, máx: 1000)
    - level: filtrar por nível (INFO, ERROR, WARNING, DEBUG) - aceita múltiplos separados por vírgula
    - search: buscar texto específico (case-insensitive)
    - reverse: ordem cronológica reversa (padrão: True = mais recentes primeiro)

    Examples:
        /api/logs?lines=50
        /api/logs?level=ERROR,WARNING
        /api/logs?search=blue%20note
        /api/logs?level=ERROR&search=timeout
    """
    try:
        # Validar parâmetros
        lines = min(max(1, lines), 1000)  # Entre 1 e 1000

        # Verificar se arquivo existe
        if not LOG_FILE.exists():
            return JSONResponse(content={
                "logs": [],
                "total_lines": 0,
                "filtered_lines": 0,
                "file_size_mb": 0,
                "message": "Arquivo de log ainda não existe. Execute uma busca primeiro."
            })

        # Obter tamanho do arquivo
        file_size_bytes = LOG_FILE.stat().st_size
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        # Ler arquivo (otimizado para arquivos grandes)
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # Parsear níveis de filtro se fornecidos
        level_filters = None
        if level:
            level_filters = [l.strip().upper() for l in level.split(',')]

        # Processar linhas
        parsed_logs = []
        for line in all_lines:
            if not line.strip():
                continue

            log_entry = parse_log_line(line)
            if not log_entry:
                continue

            # Filtrar por nível
            if level_filters and log_entry["level"] not in level_filters:
                continue

            # Filtrar por busca de texto
            if search:
                search_lower = search.lower()
                # Buscar em todos os campos
                searchable = f"{log_entry['timestamp']} {log_entry['module']} {log_entry['level']} {log_entry['message']}".lower()
                if search_lower not in searchable:
                    continue

            parsed_logs.append(log_entry)

        # Aplicar ordem reversa se solicitado
        if reverse:
            parsed_logs = parsed_logs[::-1]

        # Limitar número de linhas
        filtered_count = len(parsed_logs)
        parsed_logs = parsed_logs[:lines]

        return JSONResponse(content={
            "logs": parsed_logs,
            "total_lines": total_lines,
            "filtered_lines": filtered_count,
            "returned_lines": len(parsed_logs),
            "file_size_mb": file_size_mb,
            "filters": {
                "level": level_filters,
                "search": search,
                "reverse": reverse
            }
        })

    except Exception as e:
        logger.error(f"❌ Erro ao ler logs: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao ler logs: {str(e)}")


@app.get("/api/logs/download")
async def download_logs():
    """
    Download do arquivo completo de logs.

    Retorna o arquivo busca_eventos.log para download direto.
    Útil para análise offline ou arquivamento.
    """
    try:
        if not LOG_FILE.exists():
            raise HTTPException(
                status_code=404,
                detail="Arquivo de log não encontrado. Execute uma busca primeiro."
            )

        # Retornar arquivo para download
        return FileResponse(
            path=LOG_FILE,
            media_type="text/plain",
            filename="busca_eventos.log",
            headers={
                "Content-Disposition": f"attachment; filename=busca_eventos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao fazer download de logs: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao fazer download: {str(e)}")


@app.post("/api/logs/clear")
async def clear_logs():
    """
    Limpa o arquivo de log (rotação).

    Cria backup do arquivo atual antes de limpar.
    Só permite limpeza se arquivo > 5MB.

    Returns:
        JSON com status da operação e informações do backup
    """
    try:
        if not LOG_FILE.exists():
            return JSONResponse(content={
                "status": "success",
                "message": "Arquivo de log não existe, nada para limpar."
            })

        # Verificar tamanho do arquivo
        file_size_bytes = LOG_FILE.stat().st_size
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        # Só permitir limpeza se arquivo > 5MB
        MIN_SIZE_MB = 5
        if file_size_mb < MIN_SIZE_MB:
            return JSONResponse(content={
                "status": "skipped",
                "message": f"Arquivo muito pequeno ({file_size_mb}MB). Só é possível limpar arquivos > {MIN_SIZE_MB}MB.",
                "file_size_mb": file_size_mb
            })

        # Criar backup
        backup_dir = OUTPUT_DIR / "log_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"busca_eventos_{timestamp}.log"

        shutil.copy2(LOG_FILE, backup_file)
        logger.info(f"✓ Backup criado: {backup_file}")

        # Limpar arquivo original (mantém arquivo vazio)
        with open(LOG_FILE, 'w') as f:
            f.write(f"# Log rotacionado em {datetime.now().isoformat()}\n")
            f.write(f"# Backup salvo em: {backup_file}\n\n")

        logger.info(f"✓ Arquivo de log limpo. Tamanho anterior: {file_size_mb}MB")

        return JSONResponse(content={
            "status": "success",
            "message": f"Log rotacionado com sucesso. Backup criado.",
            "backup_file": str(backup_file),
            "previous_size_mb": file_size_mb,
            "timestamp": timestamp
        })

    except Exception as e:
        logger.error(f"❌ Erro ao limpar logs: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao limpar logs: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
