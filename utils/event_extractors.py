"""Utilitários para extração de eventos de estruturas JSON complexas."""


def extract_event_list(events_data: dict | list) -> list[dict]:
    """Extrai lista plana de eventos de estruturas JSON variadas.

    Suporta múltiplos formatos:
    - Lista simples de eventos
    - Estrutura com "verified_events"
    - Estrutura com "eventos_gerais" + "eventos_locais_especiais"

    Args:
        events_data: Estrutura contendo eventos (dict ou list)

    Returns:
        Lista plana de dicionários de eventos

    Examples:
        >>> # Lista simples
        >>> events = extract_event_list([{"titulo": "Jazz Show"}, {"titulo": "Comédia"}])
        >>> len(events)
        2

        >>> # Estrutura verified_events
        >>> data = {"verified_events": [{"titulo": "Show"}]}
        >>> events = extract_event_list(data)
        >>> len(events)
        1

        >>> # Estrutura eventos_gerais + eventos_locais_especiais
        >>> data = {
        ...     "eventos_gerais": {"eventos": [{"titulo": "Jazz"}]},
        ...     "eventos_locais_especiais": {
        ...         "blue_note": [{"titulo": "Blues"}]
        ...     }
        ... }
        >>> events = extract_event_list(data)
        >>> len(events)
        2
    """
    # Caso 1: Já é uma lista
    if isinstance(events_data, list):
        return events_data

    # Caso 2: É um dict
    if isinstance(events_data, dict):
        # Formato "verified_events"
        if "verified_events" in events_data:
            return events_data["verified_events"]

        # Formato "eventos_gerais" + "eventos_locais_especiais"
        event_list = []

        if "eventos_gerais" in events_data:
            event_list.extend(events_data["eventos_gerais"].get("eventos", []))

        if "eventos_locais_especiais" in events_data:
            for local_name, local_events in events_data["eventos_locais_especiais"].items():
                if isinstance(local_events, list):
                    # Filtrar apenas dicts válidos (ignora __checagem e outros metadados)
                    valid_events = [
                        e for e in local_events
                        if isinstance(e, dict) and not e.get("__checagem")
                    ]
                    event_list.extend(valid_events)

        return event_list

    # Caso 3: Formato desconhecido
    return []


def get_event_title(event: dict) -> str:
    """Extrai título de evento com fallbacks.

    Args:
        event: Dicionário do evento

    Returns:
        Título do evento ou string vazia

    Examples:
        >>> event = {"titulo": "Jazz Show"}
        >>> get_event_title(event)
        'Jazz Show'

        >>> event = {"nome": "Blues Night"}
        >>> get_event_title(event)
        'Blues Night'

        >>> event = {"titulo_evento": "Rock Festival"}
        >>> get_event_title(event)
        'Rock Festival'
    """
    return (
        event.get("titulo")
        or event.get("nome")
        or event.get("titulo_evento")
        or ""
    )


def filter_duplicate_events(events: list[dict]) -> list[dict]:
    """Remove eventos duplicados baseado em título e data.

    Args:
        events: Lista de eventos

    Returns:
        Lista sem duplicatas

    Examples:
        >>> events = [
        ...     {"titulo": "Jazz Show", "data": "15/01/2025"},
        ...     {"titulo": "Jazz Show", "data": "15/01/2025"},  # duplicata
        ...     {"titulo": "Blues Night", "data": "16/01/2025"},
        ... ]
        >>> unique = filter_duplicate_events(events)
        >>> len(unique)
        2
    """
    seen = set()
    unique_events = []

    for event in events:
        title = get_event_title(event).lower().strip()
        date = event.get("data", "").strip()

        # Criar chave única
        key = f"{title}|{date}"

        if key not in seen and title:  # Ignora eventos sem título
            seen.add(key)
            unique_events.append(event)

    return unique_events
