"""Aplicação web FastAPI para visualização de eventos em calendário."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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
    """Garante que o diretório de output existe."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        LATEST_OUTPUT.mkdir(parents=True, exist_ok=True)
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
        venue = event.get("venue", "")

        # Cores por categoria
        color_map = {
            "Jazz": "#3498db",  # Azul
            "Teatro-Comédia": "#e74c3c",  # Vermelho
            "Outdoor-FimDeSemana": "#2ecc71",  # Verde
        }

        # Se tem venue, usar cor específica
        if venue:
            color = "#9b59b6"  # Roxo para venues
        else:
            color = color_map.get(categoria, "#95a5a6")  # Cinza default

        return {
            "id": hash(event.get("titulo", "") + data_str + horario_str),
            "title": event.get("titulo", "Sem título"),
            "start": start_datetime,
            "end": start_datetime,  # Eventos pontuais
            "extendedProps": {
                "local": event.get("local", ""),
                "preco": event.get("preco", "Consultar"),
                "link_ingresso": event.get("link_ingresso"),
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


def run_event_search():
    """Executa a busca de eventos (main.py)."""
    import subprocess
    import shutil

    try:
        # Verificar se API key está configurada
        if not os.getenv("OPENROUTER_API_KEY"):
            logger.error("❌ OPENROUTER_API_KEY não configurada. Busca cancelada.")
            return

        # Verificar se comando uv está disponível
        if not shutil.which("uv"):
            logger.warning("⚠️  Comando 'uv' não encontrado. Tentando com python direto...")
            cmd = ["python", "main.py"]
        else:
            cmd = ["uv", "run", "python", "main.py"]

        logger.info(f"🔄 Iniciando busca automática de eventos com: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutos
        )

        if result.returncode == 0:
            logger.info("✓ Busca de eventos concluída com sucesso!")
        else:
            logger.error(f"❌ Erro na busca de eventos (code {result.returncode})")
            logger.error(f"stderr: {result.stderr[:500]}")  # Primeiros 500 chars

    except subprocess.TimeoutExpired:
        logger.error("❌ Busca de eventos excedeu o timeout de 10 minutos")
    except Exception as e:
        logger.error(f"❌ Erro ao executar busca: {type(e).__name__}: {e}")


@app.on_event("startup")
async def startup_event():
    """Inicializa o scheduler na startup."""
    # Garantir que diretórios existem
    ensure_output_directory()

    # Verificar se API key está configurada
    api_key = os.getenv("OPENROUTER_API_KEY")

    if api_key:
        # Agendar busca diária às 6h da manhã
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


@app.on_event("shutdown")
async def shutdown_event():
    """Para o scheduler no shutdown."""
    scheduler.shutdown()
    logger.info("✓ Scheduler parado")


@app.get("/health")
async def health_check():
    """
    Health check endpoint para Railway e monitoramento.

    Retorna status da aplicação sem depender de eventos carregados.
    """
    try:
        eventos = load_latest_events()
        api_key_configured = bool(os.getenv("OPENROUTER_API_KEY"))

        return JSONResponse(content={
            "status": "healthy",
            "events_loaded": len(eventos),
            "api_key_configured": api_key_configured,
            "scheduler_active": scheduler.running if hasattr(scheduler, 'running') else False,
            "output_dir_exists": LATEST_OUTPUT.exists(),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


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
        # Executar busca em background
        scheduler.add_job(
            run_event_search,
            id="manual_refresh",
            replace_existing=True
        )
        return JSONResponse(content={"status": "success", "message": "Atualização iniciada"})

    except Exception as e:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
