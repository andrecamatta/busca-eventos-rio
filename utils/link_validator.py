"""Utilitário centralizado para validação e classificação de links de eventos."""

import logging
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class LinkValidator:
    """
    Classe centralizada para validação e classificação de links.

    Elimina duplicação entre verify_agent e validation_agent,
    consolidando lógica de:
    - Detecção de links genéricos (páginas de busca/categoria)
    - Validação de qualidade de links
    - Detecção de sites de artista/venue
    - Classificação de tipo de link (purchase/info/venue)
    """

    def __init__(self):
        """Inicializa validador com padrões conhecidos."""
        # Padrões de links genéricos
        self.generic_patterns = [
            r'/eventos/[^/]+\?',  # /eventos/categoria?params
            r'/eventos\?',         # /eventos?params
            r'/eventos/?$',        # /eventos ou /eventos/ no final
            r'/shows/?$',          # /shows ou /shows/ no final (Blue Note, etc)
            r'/agenda/?$',         # /agenda ou /agenda/ no final
            r'/programacao/?$',    # /programacao ou /programacao/ no final
            r'/calendar/?$',       # /calendar ou /calendar/ no final
            r'/schedule/?$',       # /schedule ou /schedule/ no final
            r'/busca\?',          # /busca?query=
            r'/search\?',         # /search?q=
            r'[?&]city=',         # query param de cidade
            r'[?&]partnership=',  # query param de partnership
            r'/d/brazil--',       # eventbrite listings
            r'/eventos/rio-de-janeiro',  # páginas de listagem por cidade
            r'/events/rio-de-janeiro',   # páginas de listagem por cidade
        ]

        # URLs confiáveis que não são genéricas (exceções)
        self.trusted_listing_pages = [
            'bluenoterio.com.br/shows',
            'eventim.com.br/artist/blue-note-rio',
        ]

        # Plataformas de venda conhecidas
        self.purchase_platforms = [
            'sympla.com',
            'eventbrite.com',
            'ticketmaster.com',
            'ingresso.com',
            'ingressodigital.com',
            'tickets.com',
            'eventim.com.br/artist',
            'eleventickets.com',
        ]

        # Plataformas conhecidas (NÃO são sites de artistas)
        self.known_platforms = [
            'sympla', 'eventbrite', 'ticketmaster', 'ingresso', 'ticket',
            'bluenoterio', 'eleventickets', 'ingressodigital',
            'gov.br',
        ]

    def is_generic_link(self, url: str) -> bool:
        """
        Detecta se um link é genérico (página de busca/categoria/listagem).

        Args:
            url: URL a verificar

        Returns:
            True se o link for genérico (não específico de um evento)
        """
        if not url or not isinstance(url, str):
            return False

        # EXCEÇÕES: URLs conhecidas e confiáveis (não marcar como genérico)
        for trusted in self.trusted_listing_pages:
            if trusted in url.lower():
                return False  # Não é genérico, é confiável

        # Verificar padrões de URLs genéricas
        for pattern in self.generic_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        # Verificar se URL é homepage (muito curta)
        # Ex: salaceliciameireles.com.br/ ou casadochoro.com.br/
        path = url.split('?')[0]  # Remover query params
        path_parts = [p for p in path.split('/') if p and p not in ['http:', 'https:', '']]

        # URL com apenas domínio (homepage) é genérica
        if len(path_parts) == 1:
            return True

        # URL com domínio + apenas 1 segmento genérico também é genérica
        # Ex: bluenoterio.com.br/shows (2 partes, mas shows é genérico)
        if len(path_parts) == 2:
            generic_segments = ['shows', 'eventos', 'events', 'agenda', 'programacao', 'calendar', 'schedule']
            last_segment = path_parts[-1].lower().rstrip('/')
            if last_segment in generic_segments:
                return True

        return False

    def is_artist_or_venue_site(self, url: str, event_title: str) -> bool:
        """
        Detecta se URL é site institucional de artista/venue (não venda).

        Args:
            url: URL a verificar
            event_title: Título do evento

        Returns:
            True se for site genérico que deve ser rejeitado
        """
        # Extrair domínio
        domain = urlparse(url).netloc.lower()

        # Se é plataforma conhecida, não é site de artista
        if any(platform in domain for platform in self.known_platforms):
            return False

        # Heurística: domínio contém nome do evento = provável site do artista
        # Remover palavras comuns/stop words para comparação
        stop_words = {'e', 'de', 'da', 'do', 'para', 'com', 'ao', 'a', 'o', 'no', 'na'}

        event_words = set(w.lower() for w in event_title.split() if len(w) > 3 and w.lower() not in stop_words)
        domain_cleaned = domain.replace('.com', '').replace('.br', '').replace('.', ' ').replace('-', ' ')
        domain_words = set(w for w in domain_cleaned.split() if len(w) > 3 and w not in stop_words)

        # Se domínio tem >40% das palavras do título = provável site do artista
        if event_words and domain_words:
            common = event_words & domain_words
            match_ratio = len(common) / len(event_words)

            if match_ratio > 0.4:
                logger.info(f"🚫 Site de artista detectado: {domain} (match: {match_ratio:.0%} com '{event_title}')")
                return True

        return False

    def classify_link_type(self, url: str, event: dict) -> str:
        """
        Classifica o tipo de link do evento.

        Args:
            url: URL do link
            event: Dados do evento (para contexto)

        Returns:
            "purchase" (plataforma de venda), "info" (site informativo), ou "venue" (página do local)
        """
        if not url:
            return "info"  # Default para links ausentes

        url_lower = url.lower()

        # 1. PLATAFORMAS DE VENDA (maior prioridade)
        for platform in self.purchase_platforms:
            if platform in url_lower:
                return "purchase"

        # 2. VENUES COM PÁGINAS ESPECÍFICAS DE EVENTOS
        venue_event_patterns = [
            ('bluenoterio.com.br/shows/', 5),  # Blue Note com slug do show
            ('salaceliciameireles.rj.gov.br/programacao/', 5),  # Sala Cecília com evento específico
        ]

        for pattern, min_length in venue_event_patterns:
            if pattern in url_lower:
                # Verificar se tem slug/ID significativo no final
                slug = url.split('/')[-1].rstrip('/')
                if len(slug) > min_length:
                    return "purchase"  # Página específica de evento

        # 3. VERIFICAR SE É LINK GENÉRICO (listagem/homepage)
        if self.is_generic_link(url):
            return "venue"  # Links genéricos geralmente são páginas do venue

        # 4. VERIFICAR SE É SITE DE ARTISTA (informativo)
        titulo = event.get("titulo", "")
        if titulo and self.is_artist_or_venue_site(url, titulo):
            return "info"

        # 5. DOMÍNIOS .GOV.BR = venue
        if '.gov.br' in url_lower:
            return "venue"

        # 6. FALLBACK: Link externo genérico = info
        return "info"

    def validate_link_quality(self, extracted_data: dict, event: dict,
                            quality_threshold: int = 50,
                            accept_generic_events: list[str] | None = None) -> dict[str, Any]:
        """
        Valida qualidade do link baseado nos dados extraídos.

        Args:
            extracted_data: Dados extraídos da página do link
            event: Dados do evento original
            quality_threshold: Score mínimo para considerar link de qualidade
            accept_generic_events: Lista de tipos de eventos que aceitam informações genéricas

        Returns:
            dict com: score (0-100), is_quality, issues (lista de problemas), threshold
        """
        if accept_generic_events is None:
            accept_generic_events = []

        score = 0
        issues = []

        # PENALIDADE CRÍTICA: Site de artista/venue (-50 pontos)
        url = extracted_data.get("url", "")
        event_title = event.get("titulo", "")
        if url and self.is_artist_or_venue_site(url, event_title):
            score -= 50
            issues.append("⚠️ Link é site institucional do artista/venue (não é plataforma de venda)")

        # Peso: Título específico (30 pontos)
        if extracted_data.get("title"):
            title = extracted_data["title"].lower()
            event_title_lower = event.get("titulo", "").lower()

            # Verificar se título da página corresponde ao evento
            # Tolerância: pelo menos 50% de palavras em comum
            title_words = set(title.split())
            event_words = set(event_title_lower.split())

            if title_words and event_words:
                common_words = title_words & event_words
                similarity = len(common_words) / max(len(event_words), 1)

                if similarity > 0.5:
                    score += 30
                elif similarity > 0.3:
                    score += 15
                    issues.append("Título da página não corresponde bem ao evento")
                else:
                    issues.append("Título da página muito diferente do evento")
            else:
                score += 10  # Pelo menos tem um título
        else:
            issues.append("Página sem título identificável")

        # Peso: Artistas específicos (25 pontos)
        if extracted_data.get("artists") and len(extracted_data["artists"]) > 0:
            score += 25
        else:
            # Verificar se é tipo de evento que aceita genérico
            event_title_lower = event.get("titulo", "").lower()
            is_acceptable_generic = any(
                generic_type in event_title_lower
                for generic_type in accept_generic_events
            )

            if is_acceptable_generic:
                score += 20  # Eventos genéricos aceitáveis têm menos penalidade
                issues.append("Evento sem artistas específicos (aceitável para este tipo)")
            else:
                score += 10  # Dar crédito parcial mesmo sem artistas
                issues.append("Artistas não identificados (crédito parcial concedido)")

        # Peso: Data encontrada (10 pontos)
        if extracted_data.get("extracted_date", {}).get("found"):
            score += 10
        else:
            issues.append("Data não encontrada na página")

        # Peso: Horário específico (5 pontos)
        if extracted_data.get("time"):
            score += 5
        else:
            issues.append("Horário não encontrado")

        # Peso: Preço ou indicação de valor (5 pontos)
        if extracted_data.get("price"):
            score += 5
        elif "consultar" in event.get("preco", "").lower():
            score += 3  # Aceita "consultar" com penalidade

        # Peso: Link de compra funcional (10 pontos)
        if extracted_data.get("purchase_links") and len(extracted_data["purchase_links"]) > 0:
            score += 10
        else:
            issues.append("Link de compra de ingresso não encontrado na página")

        # Bônus: Descrição detalhada (5 pontos adicionais)
        if extracted_data.get("description") and len(extracted_data.get("description", "")) > 100:
            score += 5

        # Penalidade: Link é homepage genérica (-20 pontos)
        if extracted_data.get("is_generic_page"):
            score -= 20
            issues.append("Link é página genérica (homepage/listagem)")

        # Garantir score entre 0-100
        score = max(0, min(100, score))

        return {
            "score": score,
            "is_quality": score >= quality_threshold,
            "issues": issues,
            "threshold": quality_threshold,
        }
