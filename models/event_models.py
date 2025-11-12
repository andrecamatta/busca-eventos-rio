"""Pydantic models para eventos."""

from datetime import datetime
from typing import Literal, Optional, List

from pydantic import BaseModel, Field, field_validator

from utils.prompt_loader import get_prompt_loader


# Gerar Literal de categorias dinamicamente baseado no YAML
def _get_dynamic_category_literals() -> tuple[list[str], str]:
    """
    Extrai nomes de categorias do YAML e gera lista para Literal.

    Returns:
        Tuple com (lista_categorias, nome_display_padrao)
    """
    try:
        loader = get_prompt_loader()
        categorias_ids = loader.get_all_categorias()

        # Extrair nome_display de cada categoria
        categorias = []
        for cat_id in categorias_ids:
            try:
                config = loader.get_categoria(cat_id, {})
                if "nome" in config:
                    categorias.append(config["nome"])
                else:
                    # Fallback para o ID se nome não existir
                    categorias.append(cat_id.replace("_", " ").title())
            except Exception:
                # Se falhar ao carregar categoria, usar ID formatado
                categorias.append(cat_id.replace("_", " ").title())

        # Deduplicar mantendo ordem
        categorias_unicas = list(dict.fromkeys(categorias))

        # Adicionar categorias alternativas comuns (compatibilidade)
        categorias_extras = ["Outdoor-FimDeSemana", "Outdoor", "Geral", "Jazz"]
        for extra in categorias_extras:
            if extra not in categorias_unicas:
                categorias_unicas.append(extra)

        return categorias_unicas, "categorias do YAML"
    except Exception as e:
        # Fallback para lista fixa em caso de erro
        print(f"Aviso: Não foi carregar categorias do YAML: {e}")
        print("Usando categorias padrão como fallback...")
        return [
            "Jazz",
            "Música Clássica",
            "Teatro",
            "Comédia",
            "Cinema",
            "Outdoor/Parques",
            "Outdoor-FimDeSemana",
            "Outdoor",
            "Geral"
        ], "fallback (erro ao carregar YAML)"


# Gerar Literal dinâmico
CATEGORY_LITERALS, CATEGORY_SOURCE = _get_dynamic_category_literals()


class EventoBase(BaseModel):
    """Base model para todos os eventos (campos normalizados)."""

    titulo: str = Field(..., min_length=1, description="Nome completo do evento")
    data: str = Field(..., pattern=r"^\d{2}/\d{2}/\d{4}$", description="Data DD/MM/YYYY (início)")
    horario: str = Field(..., pattern=r"^[\d:ogh\s às\-]+$", description="Horário (HH:MM, HHhMM, 16h às 22h, etc.)")
    local: str = Field(..., min_length=1, description="Venue + endereço completo")
    preco: str = Field(default="Consultar", description="Preço ou 'Consultar'")
    link_ingresso: Optional[str] = Field(None, description="URL de compra (opcional)")
    link_type: Optional[Literal["purchase", "info", "venue"]] = Field(
        None,
        description="Tipo de link: 'purchase' (plataforma de venda), 'info' (site informativo), 'venue' (página do local)"
    )
    descricao: Optional[str] = Field(None, description="Descrição do evento (opcional)")

    # Campos para eventos contínuos (exposições, mostras, temporadas)
    data_fim: Optional[str] = Field(None, pattern=r"^\d{2}/\d{2}/\d{4}$", description="Data final (para eventos contínuos)")
    is_temporada: bool = Field(default=False, description="Se é evento contínuo (exposição, mostra)")
    tipo_temporada: Optional[str] = Field(None, description="Tipo: 'exposição', 'mostra', 'feira contínua'")

    # Campos de julgamento de qualidade (preenchidos pelo QualityJudgeAgent)
    quality_score: Optional[float] = Field(None, ge=0, le=10, description="Nota geral de qualidade (0-10)")
    prompt_adherence: Optional[float] = Field(None, ge=0, le=10, description="Aderência ao prompt original (0-10)")
    link_match: Optional[float] = Field(None, ge=0, le=10, description="Correlação entre link e dados (0-10)")
    quality_notes: Optional[str] = Field(None, description="Observações do julgamento")
    judged_at: Optional[str] = Field(None, description="Timestamp ISO do julgamento")

    @field_validator("data")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Valida formato DD/MM/YYYY."""
        try:
            datetime.strptime(v, "%d/%m/%Y")
            return v
        except ValueError:
            raise ValueError(f"Data deve estar no formato DD/MM/YYYY, recebido: {v}")

    @field_validator("data_fim")
    @classmethod
    def validate_date_fim(cls, v: Optional[str], info) -> Optional[str]:
        """Valida data_fim e garante que seja posterior a data."""
        if v is None:
            return v

        try:
            data_fim_dt = datetime.strptime(v, "%d/%m/%Y")
        except ValueError:
            raise ValueError(f"data_fim deve estar no formato DD/MM/YYYY, recebido: {v}")

        # Validar que data_fim seja posterior a data
        if "data" in info.data:
            data_inicio_dt = datetime.strptime(info.data["data"], "%d/%m/%Y")
            if data_fim_dt < data_inicio_dt:
                raise ValueError(f"data_fim ({v}) deve ser posterior ou igual a data ({info.data['data']})")

        return v

    @field_validator("link_ingresso")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Valida URL se fornecida."""
        if v and v.strip() and v.lower() not in ("null", "none"):
            if not v.startswith(("http://", "https://")):
                raise ValueError(f"Link deve começar com http:// ou https://, recebido: {v}")
            return v
        return None


class EventoCategoria(EventoBase):
    """Evento baseado em categoria (categorias dinâmicas do YAML)."""

    categoria: Literal[tuple(CATEGORY_LITERALS)] = Field(
        ..., description=f"Categoria do evento ({CATEGORY_SOURCE})"
    )


class EventoVenue(EventoBase):
    """Evento baseado em venue específico."""

    venue: Literal[
        "Casa do Choro",
        "Sala Cecília Meireles",
        "Teatro Municipal do Rio de Janeiro",
        "Artemis - Torrefação Artesanal e Cafeteria",
        "CCBB Rio - Centro Cultural Banco do Brasil",
        "Oi Futuro",
        "IMS - Instituto Moreira Salles",
        "Parque Lage",
        "CCJF - Centro Cultural Justiça Federal",
        "MAM Cinema",
        "Theatro Net Rio",
        "CCBB Teatro e Cinema",
        "Istituto Italiano di Cultura",
        "Maze Jazz Club",
        "Teatro do Leblon",
        "Clube do Jazz / Teatro Rival",
        "Estação Net (Ipanema e Botafogo)",
    ] = Field(..., description="Venue do evento")


class ResultadoBuscaCategoria(BaseModel):
    """Resultado da busca para eventos de categoria."""

    eventos: list[EventoCategoria] = Field(default_factory=list, description="Lista de eventos")


class ResultadoBuscaVenue(BaseModel):
    """Resultado da busca para eventos de venues."""

    venue_name: str = Field(..., description="Nome do venue")
    eventos: list[EventoVenue] = Field(default_factory=list, description="Lista de eventos")
