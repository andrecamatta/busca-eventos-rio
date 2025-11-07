"""Pydantic models para eventos."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EventoBase(BaseModel):
    """Base model para todos os eventos (campos normalizados)."""

    titulo: str = Field(..., min_length=1, description="Nome completo do evento")
    data: str = Field(..., pattern=r"^\d{2}/\d{2}/\d{4}$", description="Data DD/MM/YYYY")
    horario: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="Horário HH:MM")
    local: str = Field(..., min_length=1, description="Venue + endereço completo")
    preco: str = Field(default="Consultar", description="Preço ou 'Consultar'")
    link_ingresso: Optional[str] = Field(None, description="URL de compra (opcional)")
    descricao: Optional[str] = Field(None, description="Descrição do evento (opcional)")

    @field_validator("data")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Valida formato DD/MM/YYYY."""
        try:
            datetime.strptime(v, "%d/%m/%Y")
            return v
        except ValueError:
            raise ValueError(f"Data deve estar no formato DD/MM/YYYY, recebido: {v}")

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
    """Evento baseado em categoria (Jazz, Comédia, Outdoor)."""

    categoria: Literal["Jazz", "Teatro-Comédia", "Outdoor-FimDeSemana"] = Field(
        ..., description="Categoria do evento"
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
        "Sesc Copacabana",
        "Sesc Flamengo",
        "Sesc Tijuca",
        "Sesc Engenho de Dentro",
        "Casa Natura Musical",
        "MAM Cinema",
        "Theatro Net Rio",
        "CCBB Teatro e Cinema",
    ] = Field(..., description="Venue do evento")


class ResultadoBuscaCategoria(BaseModel):
    """Resultado da busca para eventos de categoria."""

    eventos: list[EventoCategoria] = Field(default_factory=list, description="Lista de eventos")


class ResultadoBuscaVenue(BaseModel):
    """Resultado da busca para eventos de venues."""

    venue_name: str = Field(..., description="Nome do venue")
    eventos: list[EventoVenue] = Field(default_factory=list, description="Lista de eventos")
