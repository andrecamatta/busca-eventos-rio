"""Aplicação web FastAPI para visualização de eventos em calendário."""

import asyncio
import json
import logging
import os
import re
import shutil
import threading
import time
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

# Status do job de atualização (rastreamento global)
job_status = {
    "is_running": False,
    "last_started": None,
    "last_completed": None,
    "last_result": None,  # "success", "error", ou None
    "last_error": None,
    "last_duration_seconds": None,
    "last_stdout": None,
    "last_stderr": None,
}

# Status do job de julgamento (rastreamento global)
judge_status = {
    "is_running": False,
    "last_started": None,
    "last_completed": None,
    "last_result": None,  # "success", "error", ou None
    "last_error": None,
    "total_events": 0,
    "judged_count": 0,
    "current_batch": 0,
    "total_batches": 0,
    "average_score": 0.0,
}


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

        # Tentar vários arquivos possíveis (em ordem de prioridade)
        possible_files = [
            LATEST_OUTPUT / "judged_events.json",              # PRIORIDADE 1: Eventos com notas de qualidade (GPT-5)
            LATEST_OUTPUT / "formatted_output.json",           # PRIORIDADE 2: Eventos formatados para WhatsApp
            LATEST_OUTPUT / "verified_events.json",            # PRIORIDADE 3: Eventos verificados
            LATEST_OUTPUT / "enriched_events_initial.json",    # PRIORIDADE 4: Fallback (eventos enriquecidos)
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

        # Validar link antes de incluir (não mostrar links 404 ou inválidos)
        link_ingresso = event.get("link_ingresso")
        link_valid = event.get("link_valid")
        link_status_code = event.get("link_status_code")

        # Só incluir link se for válido (não é False e não é 404)
        if link_valid is False or link_status_code == 404:
            link_ingresso = None

        # Badge visual para eventos contínuos (exposições/temporadas)
        title = event.get("titulo", "Sem título")
        is_temporada = event.get("is_temporada", False)
        tipo_temporada = event.get("tipo_temporada")

        if is_temporada and tipo_temporada:
            # Adicionar ícone de calendário ao título
            title = f"📅 {title}"

        return {
            "id": hash(event.get("titulo", "") + data_str + horario_str),
            "title": title,
            "start": start_datetime,
            "end": start_datetime,  # Eventos pontuais
            "extendedProps": {
                "local": event.get("local", ""),
                "preco": event.get("preco", "Consultar"),
                "link_ingresso": link_ingresso,  # None se inválido
                "link_type": event.get("link_type", "info") if link_ingresso else None,  # purchase, info, ou venue
                "descricao": event.get("descricao", ""),
                "categoria": categoria,
                "venue": venue,
                "is_temporada": is_temporada,
                "tipo_temporada": tipo_temporada,
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
    """Executa a busca de eventos (main.py) com logging detalhado e rastreamento de status."""
    import subprocess
    import shutil
    import time
    import traceback

    # Marcar início da execução
    start_time = time.time()
    job_status["is_running"] = True
    job_status["last_started"] = datetime.now().isoformat()
    job_status["last_result"] = None
    job_status["last_error"] = None

    logger.info("=" * 80)
    logger.info("🚀 INICIANDO BUSCA DE EVENTOS (MANUAL/SCHEDULED)")
    logger.info(f"📅 Horário de início: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)

    try:
        # Verificar se API key está configurada
        if not os.getenv("OPENROUTER_API_KEY"):
            error_msg = "OPENROUTER_API_KEY não configurada. Busca cancelada."
            logger.error(f"❌ {error_msg}")
            job_status["last_result"] = "error"
            job_status["last_error"] = error_msg
            return

        # Determinar comando para executar main.py
        # No container Docker, venv está no PATH via ENV VIRTUAL_ENV=/app/.venv
        # Usar 'python' diretamente aproveita o venv ativo
        venv_python = BASE_DIR / ".venv" / "bin" / "python"

        if venv_python.exists():
            # Venv existe (container Docker ou dev local) - usar diretamente
            cmd = ["python", "main.py"]
            logger.info(f"✓ Comando selecionado: python main.py (venv em {venv_python})")
        elif shutil.which("uv"):
            # Ambiente dev com uv mas sem venv
            cmd = ["uv", "run", "python", "main.py"]
            logger.info(f"✓ Comando selecionado: uv run python main.py")
        else:
            # Fallback: python do sistema
            logger.warning("⚠️  Nem venv nem uv encontrados. Usando python do sistema...")
            cmd = ["python3", "main.py"]
            logger.info(f"✓ Comando selecionado: python3 main.py")

        logger.info(f"📂 Diretório de execução: {BASE_DIR}")
        logger.info(f"⏱️  Timeout configurado: 600s (10 minutos)")
        logger.info("🔄 Executando subprocess...")

        # Executar comando
        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutos
        )

        duration = time.time() - start_time
        job_status["last_duration_seconds"] = round(duration, 2)

        logger.info("-" * 80)
        logger.info(f"⏱️  Duração total: {duration:.2f}s")
        logger.info(f"📊 Return code: {result.returncode}")

        if result.returncode == 0:
            logger.info("=" * 80)
            logger.info("✅ BUSCA DE EVENTOS CONCLUÍDA COM SUCESSO!")
            logger.info("=" * 80)

            # Logar stdout completo (primeiros 5000 chars)
            if result.stdout:
                logger.info("📝 STDOUT (primeiros 5000 chars):")
                logger.info(result.stdout[:5000])

            job_status["last_result"] = "success"
            job_status["last_error"] = None
            job_status["last_stdout"] = result.stdout[:5000] if result.stdout else None
            job_status["last_stderr"] = result.stderr[:5000] if result.stderr else None
        else:
            error_msg = f"Subprocess retornou código {result.returncode}"
            logger.error("=" * 80)
            logger.error(f"❌ ERRO NA BUSCA DE EVENTOS")
            logger.error("=" * 80)
            logger.error(f"Return code: {result.returncode}")

            # Logar stderr completo (primeiros 5000 chars)
            if result.stderr:
                logger.error("📝 STDERR (primeiros 5000 chars):")
                logger.error(result.stderr[:5000])

            # Logar stdout também (pode conter mensagens úteis)
            if result.stdout:
                logger.error("📝 STDOUT (primeiros 5000 chars):")
                logger.error(result.stdout[:5000])

            job_status["last_result"] = "error"
            job_status["last_error"] = error_msg
            job_status["last_stdout"] = result.stdout[:5000] if result.stdout else None
            job_status["last_stderr"] = result.stderr[:5000] if result.stderr else None

    except subprocess.TimeoutExpired as e:
        duration = time.time() - start_time
        job_status["last_duration_seconds"] = round(duration, 2)

        error_msg = f"Timeout de 10 minutos excedido (executou por {duration:.2f}s)"
        logger.error("=" * 80)
        logger.error("❌ TIMEOUT NA BUSCA DE EVENTOS")
        logger.error("=" * 80)
        logger.error(error_msg)

        # Tentar capturar output parcial
        if hasattr(e, 'stdout') and e.stdout:
            logger.error("📝 STDOUT parcial (primeiros 5000 chars):")
            logger.error(e.stdout[:5000])
        if hasattr(e, 'stderr') and e.stderr:
            logger.error("📝 STDERR parcial (primeiros 5000 chars):")
            logger.error(e.stderr[:5000])

        job_status["last_result"] = "error"
        job_status["last_error"] = error_msg

    except Exception as e:
        duration = time.time() - start_time
        job_status["last_duration_seconds"] = round(duration, 2)

        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error("=" * 80)
        logger.error("❌ EXCEÇÃO NÃO TRATADA NA BUSCA DE EVENTOS")
        logger.error("=" * 80)
        logger.error(f"Tipo: {type(e).__name__}")
        logger.error(f"Mensagem: {str(e)}")
        logger.error("📝 Traceback completo:")
        logger.error(traceback.format_exc())

        job_status["last_result"] = "error"
        job_status["last_error"] = error_msg

    finally:
        # Marcar fim da execução
        job_status["is_running"] = False
        job_status["last_completed"] = datetime.now().isoformat()

        logger.info("=" * 80)
        logger.info(f"🏁 EXECUÇÃO FINALIZADA - Status: {job_status['last_result']}")
        logger.info(f"📅 Horário de término: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)


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

    # FILTRO TEMPORAL: Eventos de hoje só aparecem se faltam pelo menos 3 horas
    from datetime import datetime, timedelta
    now = datetime.now()
    hora_minima = now + timedelta(hours=3)

    eventos_filtrados = []
    for evento in eventos:
        data_str = evento.get("data", "")
        horario_str = evento.get("horario", "00:00")

        try:
            # Parse data (formato DD/MM/YYYY)
            event_date = datetime.strptime(data_str, "%d/%m/%Y").date()

            # Se não é hoje, verificar se não é data passada
            if event_date != now.date():
                # Rejeitar eventos passados
                if event_date < now.date():
                    continue  # Filtrar silenciosamente
                # Aceitar eventos futuros
                eventos_filtrados.append(evento)
                continue

            # Se é hoje, verificar horário
            hora_partes = horario_str.split(":")
            if len(hora_partes) >= 2:
                hora = int(hora_partes[0])
                minuto = int(hora_partes[1])
                event_datetime = datetime.combine(event_date, datetime.min.time()).replace(hour=hora, minute=minuto)

                # Só adicionar se faltam pelo menos 3 horas
                if event_datetime >= hora_minima:
                    eventos_filtrados.append(evento)
                # Senão, evento muito próximo/passado - filtrar silenciosamente
            else:
                # Horário inválido - manter por segurança (modo permissivo)
                eventos_filtrados.append(evento)

        except (ValueError, IndexError):
            # Erro de parsing - manter evento por segurança (modo permissivo)
            eventos_filtrados.append(evento)

    eventos = eventos_filtrados

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


@app.get("/api/refresh/status")
async def get_refresh_status():
    """
    Retorna o status atual do job de atualização de eventos.

    Response:
        {
            "is_running": bool,
            "last_started": str | null,
            "last_completed": str | null,
            "last_result": "success" | "error" | null,
            "last_error": str | null,
            "last_duration_seconds": float | null
        }
    """
    return JSONResponse(content=job_status)


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


# ═══════════════════════════════════════════════════════════════════════════════
# JULGAMENTO DE QUALIDADE DE EVENTOS (GPT-5)
# ═══════════════════════════════════════════════════════════════════════════════

def run_judge_quality():
    """Executa julgamento de qualidade dos eventos em background thread."""
    import sys
    sys.path.insert(0, str(BASE_DIR))

    from agents.judge_agent import QualityJudgeAgent

    start_time = time.time()
    judge_status["is_running"] = True
    judge_status["last_started"] = datetime.now().isoformat()
    judge_status["last_result"] = None
    judge_status["last_error"] = None

    logger.info("=" * 80)
    logger.info("⚖️  INICIANDO JULGAMENTO DE QUALIDADE DE EVENTOS")
    logger.info(f"📅 Horário de início: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)

    try:
        # Verificar API key
        if not os.getenv("OPENROUTER_API_KEY"):
            error_msg = "OPENROUTER_API_KEY não configurada. Julgamento cancelado."
            logger.error(f"❌ {error_msg}")
            judge_status["last_result"] = "error"
            judge_status["last_error"] = error_msg
            judge_status["is_running"] = False
            return

        # Carregar eventos
        logger.info("📂 Carregando eventos para julgar...")
        eventos = load_latest_events()

        if not eventos:
            error_msg = "Nenhum evento encontrado para julgar"
            logger.warning(f"⚠️  {error_msg}")
            judge_status["last_result"] = "error"
            judge_status["last_error"] = error_msg
            judge_status["is_running"] = False
            return

        judge_status["total_events"] = len(eventos)
        logger.info(f"✓ {len(eventos)} eventos carregados")

        # Criar agent
        logger.info("🤖 Inicializando QualityJudgeAgent...")
        judge = QualityJudgeAgent()

        # Callback de progresso
        def progress_callback(batch_num, total_batches):
            judge_status["current_batch"] = batch_num
            judge_status["total_batches"] = total_batches
            judge_status["judged_count"] = min(batch_num * 5, len(eventos))
            logger.info(
                f"⚖️  Progresso: batch {batch_num}/{total_batches} "
                f"({judge_status['judged_count']}/{len(eventos)} eventos)"
            )

        # Executar julgamento (assíncrono)
        logger.info("⚖️  Iniciando julgamento...")

        # Criar event loop para executar código assíncrono
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            judged_events = loop.run_until_complete(
                judge.judge_all_events(eventos, progress_callback)
            )
        finally:
            loop.close()

        # Calcular estatísticas
        scores = [e.get("quality_score", 0) for e in judged_events]
        avg_score = sum(scores) / len(scores) if scores else 0
        judge_status["average_score"] = round(avg_score, 2)

        # Salvar eventos julgados
        judged_file = LATEST_OUTPUT / "judged_events.json"
        logger.info(f"💾 Salvando eventos julgados em: {judged_file}")

        with open(judged_file, "w", encoding="utf-8") as f:
            json.dump(judged_events, f, ensure_ascii=False, indent=2)

        duration = time.time() - start_time

        logger.info("=" * 80)
        logger.info("✅ JULGAMENTO CONCLUÍDO COM SUCESSO!")
        logger.info(f"⏱️  Duração: {duration:.2f}s")
        logger.info(f"📊 Eventos julgados: {len(judged_events)}")
        logger.info(f"⭐ Nota média: {avg_score:.2f}/10")
        logger.info("=" * 80)

        judge_status["last_result"] = "success"
        judge_status["last_completed"] = datetime.now().isoformat()
        judge_status["is_running"] = False

    except Exception as e:
        duration = time.time() - start_time
        error_msg = f"Erro no julgamento: {str(e)}"

        logger.error("=" * 80)
        logger.error("❌ ERRO NO JULGAMENTO DE QUALIDADE")
        logger.error("=" * 80)
        logger.error(f"⏱️  Duração até erro: {duration:.2f}s")
        logger.error(f"Erro: {e}")
        logger.exception(e)

        judge_status["last_result"] = "error"
        judge_status["last_error"] = error_msg
        judge_status["last_completed"] = datetime.now().isoformat()
        judge_status["is_running"] = False


@app.post("/api/judge")
async def start_judge():
    """
    Inicia julgamento de qualidade dos eventos em background.

    Returns:
        JSON com status de início do job
    """
    # Verificar se já está rodando
    if judge_status["is_running"]:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Julgamento já em andamento",
                "status": judge_status
            }
        )

    # Verificar API key
    if not os.getenv("OPENROUTER_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY não configurada"
        )

    # Iniciar job em background thread
    thread = threading.Thread(target=run_judge_quality, daemon=True)
    thread.start()

    return JSONResponse(
        status_code=202,
        content={
            "message": "Julgamento iniciado com sucesso",
            "status": "started",
            "started_at": judge_status["last_started"]
        }
    )


@app.get("/api/judge/status")
async def judge_status_endpoint():
    """
    Retorna status atual do julgamento.

    Returns:
        JSON com informações de progresso
    """
    return JSONResponse(content=judge_status)


@app.get("/api/judge/results")
async def judge_results():
    """
    Retorna eventos julgados (com notas de qualidade).

    Returns:
        JSON com lista de eventos e suas avaliações
    """
    try:
        judged_file = LATEST_OUTPUT / "judged_events.json"

        if not judged_file.exists():
            return JSONResponse(
                status_code=404,
                content={
                    "detail": "Nenhum julgamento disponível ainda. Execute /api/judge primeiro.",
                    "events": []
                }
            )

        with open(judged_file, "r", encoding="utf-8") as f:
            events = json.load(f)

        # Estatísticas
        scores = [e.get("quality_score", 0) for e in events if e.get("quality_score")]
        stats = {
            "total": len(events),
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "min_score": round(min(scores), 2) if scores else 0,
            "max_score": round(max(scores), 2) if scores else 0,
        }

        return JSONResponse(content={
            "events": events,
            "stats": stats
        })

    except Exception as e:
        logger.error(f"❌ Erro ao carregar resultados do julgamento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
