"""Eval para FASE 1: Busca com Perplexity.

Verifica se as expectativas quantitativas e qualitativas dos prompts foram atendidas.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import SEARCH_CONFIG


class SearchEvaluator:
    """Avalia resultados da busca do Perplexity (FASE 1)."""

    # Expectativas definidas nos prompts
    EXPECTED_EVENTOS_GERAIS = {
        "Jazz": {"min": 3, "max": None},
        "Teatro-Comédia": {"min": 3, "max": None},
        "Outdoor-FimDeSemana": {"min": 3, "max": None},
    }

    EXPECTED_VENUES = {
        "Casa do Choro": {"min": 1, "max": None},
        "Sala Cecília Meireles": {"min": 1, "max": None},
        "Teatro Municipal do Rio de Janeiro": {"min": 1, "max": None},
        "Artemis - Torrefação Artesanal e Cafeteria": {"min": 1, "max": None},
    }

    # Campos obrigatórios para completude (segundo prompt linha 216)
    REQUIRED_FIELDS = ["data", "horario", "local", "descricao"]

    def __init__(self, structured_events_path: str, verified_events_path: str | None = None):
        """Inicializa avaliador com caminho do arquivo."""
        self.path = Path(structured_events_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {structured_events_path}")

        with open(self.path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        # Carregar verified_events se fornecido (para validação HTTP)
        self.verified_data = None
        if verified_events_path:
            verified_path = Path(verified_events_path)
            if verified_path.exists():
                with open(verified_path, "r", encoding="utf-8") as f:
                    self.verified_data = json.load(f)

        self.results = {}

        # Usar intervalo de datas do config (dinâmico)
        self.expected_start_date = SEARCH_CONFIG["start_date"]
        self.expected_end_date = SEARCH_CONFIG["end_date"]

    def eval_eventos_gerais(self) -> dict[str, Any]:
        """Avalia eventos gerais por categoria."""
        eventos = self.data.get("eventos_gerais", {}).get("eventos", [])

        # Contar por categoria
        categorias = {}
        for evento in eventos:
            cat = evento.get("categoria", "Unknown")
            categorias[cat] = categorias.get(cat, 0) + 1

        # Avaliar cada categoria esperada
        results = {}
        for cat, expected in self.EXPECTED_EVENTOS_GERAIS.items():
            count = categorias.get(cat, 0)
            status = self._get_status(count, expected["min"], expected["max"])

            # Formatar expectativa (range ou mínimo)
            if expected["max"] is None:
                expected_str = f">={expected['min']}"
            else:
                expected_str = f"{expected['min']}-{expected['max']}"

            results[cat] = {
                "count": count,
                "expected": expected_str,
                "status": status,
            }

        return {
            "total_eventos": len(eventos),
            "categorias": results,
        }

    def eval_eventos_venues(self) -> dict[str, Any]:
        """Avalia eventos de venues específicos."""
        eventos_locais = self.data.get("eventos_locais_especiais", {})

        # Avaliar cada venue esperado
        results = {}
        for venue, expected in self.EXPECTED_VENUES.items():
            eventos = eventos_locais.get(venue, [])
            # Filtrar arrays (ignorar campos como "_fontesPesquisadas")
            if isinstance(eventos, list):
                count = len(eventos)
            else:
                count = 0

            status = self._get_status(count, expected["min"], expected["max"])

            # Formatar expectativa (range ou mínimo)
            if expected["max"] is None:
                expected_str = f">={expected['min']}"
            else:
                expected_str = f"{expected['min']}-{expected['max']}"

            results[venue] = {
                "count": count,
                "expected": expected_str,
                "status": status,
            }

        # Contar total de eventos de venues
        total_venue_eventos = sum(
            len(v) if isinstance(v, list) else 0
            for k, v in eventos_locais.items()
            if not k.endswith("_fontesPesquisadas")
        )

        return {
            "total_eventos": total_venue_eventos,
            "venues": results,
        }

    def eval_completude(self) -> dict[str, Any]:
        """Avalia completude dos campos obrigatórios."""
        todos_eventos = []

        # Coletar todos os eventos (gerais + venues)
        eventos_gerais = self.data.get("eventos_gerais", {}).get("eventos", [])
        todos_eventos.extend(eventos_gerais)

        eventos_locais = self.data.get("eventos_locais_especiais", {})
        for venue, eventos in eventos_locais.items():
            # Ignorar campos "_fontesPesquisadas"
            if venue.endswith("_fontesPesquisadas"):
                continue
            # Apenas processar listas de dicts (eventos)
            if isinstance(eventos, list):
                # Filtrar apenas dicts (eventos), ignorar strings
                eventos_validos = [e for e in eventos if isinstance(e, dict)]
                todos_eventos.extend(eventos_validos)

        if not todos_eventos:
            return {"status": "NO_EVENTS", "message": "Nenhum evento encontrado"}

        # Verificar campos obrigatórios
        field_stats = {field: 0 for field in self.REQUIRED_FIELDS}
        field_stats["link"] = 0  # Link é opcional, mas vamos contar

        valid_data_count = 0

        for evento in todos_eventos:
            # Campos obrigatórios (normalizar nomes diferentes)
            for field in self.REQUIRED_FIELDS:
                value = None

                # Normalizar nomes de campos (eventos gerais vs venues)
                if field == "horario":
                    value = evento.get("horario") or evento.get("hora")
                elif field == "descricao":
                    value = evento.get("descricao") or evento.get("descrição")
                else:
                    value = evento.get(field)

                if value:
                    field_stats[field] += 1

            # Link (opcional)
            link = evento.get("link_ingresso") or evento.get("link")
            if link:
                field_stats["link"] += 1

            # Validar formato de data (DD/MM/YYYY)
            data = evento.get("data")
            if data and self._validate_date_format(data):
                valid_data_count += 1

        # Validar intervalo de datas (05/11 - 26/11)
        valid_interval_count = 0
        for evento in todos_eventos:
            data = evento.get("data")
            if data and self._validate_date_interval(data):
                valid_interval_count += 1

        total = len(todos_eventos)
        completude = {}
        for field, count in field_stats.items():
            percentage = (count / total * 100) if total > 0 else 0
            is_required = field in self.REQUIRED_FIELDS
            completude[field] = {
                "count": count,
                "total": total,
                "percentage": percentage,
                "required": is_required,
                "status": "✅" if percentage == 100 or not is_required else "❌",
            }

        # Status de data válida
        valid_data_percentage = (valid_data_count / total * 100) if total > 0 else 0
        valid_interval_percentage = (valid_interval_count / total * 100) if total > 0 else 0

        return {
            "total_eventos": total,
            "completude": completude,
            "valid_data_format": {
                "count": valid_data_count,
                "total": total,
                "percentage": valid_data_percentage,
            },
            "valid_date_interval": {
                "count": valid_interval_count,
                "total": total,
                "percentage": valid_interval_percentage,
            },
        }

    def _get_status(self, count: int, min_expected: int, max_expected: int | None = None) -> str:
        """Determina status baseado na contagem."""
        if count == 0:
            return "❌ CRITICAL"
        elif count < min_expected:
            return "⚠️  BELOW"
        elif max_expected is None:
            # Sem máximo: só precisa estar >= mínimo
            return "✅ OK"
        elif min_expected <= count <= max_expected:
            return "✅ OK"
        else:
            return "✅ ABOVE"

    def _validate_date_format(self, date_str: str) -> bool:
        """Valida formato DD/MM/YYYY."""
        try:
            # Remove horário se presente
            date_only = date_str.split()[0] if " " in date_str else date_str
            datetime.strptime(date_only, "%d/%m/%Y")
            return True
        except (ValueError, AttributeError):
            return False

    def _validate_date_interval(self, date_str: str) -> bool:
        """Valida se a data está no intervalo esperado (dinâmico: hoje + 21 dias)."""
        try:
            # Remove horário se presente
            date_only = date_str.split()[0] if " " in date_str else date_str
            date_obj = datetime.strptime(date_only, "%d/%m/%Y")
            return self.expected_start_date <= date_obj <= self.expected_end_date
        except (ValueError, AttributeError):
            return False

    def eval_link_accessibility(self) -> dict[str, Any] | None:
        """Avalia acessibilidade HTTP dos links (requer verified_events.json)."""
        if not self.verified_data:
            return None

        # Pegar eventos validados
        verified_events = self.verified_data.get("verified_events", [])
        if not verified_events:
            return None

        # Estatísticas de links
        total_eventos = len(verified_events)
        sem_link = 0
        http_200 = 0
        http_erros = 0
        corrigidos_ia = 0
        erros_por_status = {}

        for evento in verified_events:
            link = evento.get("link_ingresso") or evento.get("link")

            if not link:
                sem_link += 1
                continue

            # Verificar se link foi validado
            link_valid = evento.get("link_valid")
            link_status = evento.get("link_status_code")
            link_updated = evento.get("link_updated_by_ai", False)

            if link_updated:
                corrigidos_ia += 1

            if link_status == 200:
                http_200 += 1
            elif link_status:
                http_erros += 1
                # Contar por tipo de erro
                status_key = f"HTTP {link_status}"
                erros_por_status[status_key] = erros_por_status.get(status_key, 0) + 1

        # Calcular percentuais
        com_link = total_eventos - sem_link
        perc_http_200 = (http_200 / com_link * 100) if com_link > 0 else 0
        perc_http_erros = (http_erros / com_link * 100) if com_link > 0 else 0

        return {
            "total_eventos": total_eventos,
            "sem_link": sem_link,
            "com_link": com_link,
            "http_200": http_200,
            "http_200_perc": perc_http_200,
            "http_erros": http_erros,
            "http_erros_perc": perc_http_erros,
            "corrigidos_ia": corrigidos_ia,
            "erros_por_status": erros_por_status,
        }

    def generate_report(self) -> int:
        """Gera relatório completo e retorna score (0-100)."""
        print("\n" + "=" * 70)
        print("EVAL: Busca Perplexity (FASE 1)")
        print("=" * 70)
        print(f"Arquivo: {self.path}")
        print()

        # Avaliar eventos gerais
        eventos_gerais_results = self.eval_eventos_gerais()
        print("📊 EVENTOS GERAIS:")
        print(f"   Total: {eventos_gerais_results['total_eventos']} eventos")
        print()

        criterios_ok = 0
        total_criterios = 0

        for cat, result in eventos_gerais_results["categorias"].items():
            status_symbol = result["status"]
            print(f"   {cat}: {result['count']}/{result['expected']} {status_symbol}")
            total_criterios += 1
            if "✅" in result["status"]:
                criterios_ok += 1

        print()

        # Avaliar eventos de venues
        eventos_venues_results = self.eval_eventos_venues()
        print("🏛️  EVENTOS DE VENUES:")
        print(f"   Total: {eventos_venues_results['total_eventos']} eventos")
        print()

        for venue, result in eventos_venues_results["venues"].items():
            status_symbol = result["status"]
            print(f"   {venue}: {result['count']}/{result['expected']} {status_symbol}")
            total_criterios += 1
            if "✅" in result["status"]:
                criterios_ok += 1

        print()

        # Avaliar completude
        completude_results = self.eval_completude()
        if completude_results.get("status") == "NO_EVENTS":
            print("⚠️  COMPLETUDE: Nenhum evento encontrado")
            score = 0
        else:
            print("📋 COMPLETUDE DOS CAMPOS:")
            print()

            for field, stats in completude_results["completude"].items():
                required_label = "(obrigatório)" if stats["required"] else "(opcional)"
                print(
                    f"   {stats['status']} {field.capitalize()} {required_label}: "
                    f"{stats['count']}/{stats['total']} ({stats['percentage']:.0f}%)"
                )

                if stats["required"]:
                    total_criterios += 1
                    if stats["percentage"] == 100:
                        criterios_ok += 1

            print()
            print(
                f"   Data válida (formato): {completude_results['valid_data_format']['count']}/"
                f"{completude_results['valid_data_format']['total']} "
                f"({completude_results['valid_data_format']['percentage']:.0f}%)"
            )

            # Intervalo dinâmico de datas
            start_str = self.expected_start_date.strftime("%d/%m")
            end_str = self.expected_end_date.strftime("%d/%m")
            print(
                f"   Data no intervalo esperado ({start_str}-{end_str}): {completude_results['valid_date_interval']['count']}/"
                f"{completude_results['valid_date_interval']['total']} "
                f"({completude_results['valid_date_interval']['percentage']:.0f}%)"
            )

        print()

        # Avaliar acessibilidade HTTP dos links (se verified_events disponível)
        link_results = self.eval_link_accessibility()
        if link_results:
            print("📡 VALIDAÇÃO HTTP DE LINKS:")
            print()
            print(f"   Total de eventos: {link_results['total_eventos']}")
            print(f"   Eventos com link: {link_results['com_link']}")
            print(f"   Eventos sem link: {link_results['sem_link']}")
            print()
            print(
                f"   ✅ Links acessíveis (HTTP 200): {link_results['http_200']}/{link_results['com_link']} "
                f"({link_results['http_200_perc']:.0f}%)"
            )
            print(
                f"   ❌ Links com erro: {link_results['http_erros']}/{link_results['com_link']} "
                f"({link_results['http_erros_perc']:.0f}%)"
            )

            if link_results["erros_por_status"]:
                print()
                print("   Detalhamento dos erros:")
                for status, count in sorted(link_results["erros_por_status"].items()):
                    print(f"      {status}: {count}")

            if link_results["corrigidos_ia"] > 0:
                print()
                print(f"   🤖 Links corrigidos pela IA: {link_results['corrigidos_ia']}")

            print()

        print("=" * 70)

        # Calcular score final
        score = (criterios_ok / total_criterios * 100) if total_criterios > 0 else 0
        status_final = "✅ PASS" if score >= 80 else "❌ FAIL"

        print(f"SCORE FINAL: {score:.0f}% ({criterios_ok}/{total_criterios} critérios OK)")
        print(f"STATUS: {status_final}")
        print("=" * 70)
        print()

        return int(score)


def main():
    """Executa eval."""
    parser = argparse.ArgumentParser(description="Eval de busca Perplexity (FASE 1)")
    parser.add_argument(
        "--output",
        default="output/structured_events.json",
        help="Caminho do arquivo structured_events.json",
    )
    parser.add_argument(
        "--verified",
        default=None,
        help="Caminho do arquivo verified_events.json (opcional, para validação HTTP)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=80,
        help="Score mínimo para passar (0-100)",
    )

    args = parser.parse_args()

    try:
        evaluator = SearchEvaluator(args.output, args.verified)
        score = evaluator.generate_report()

        # Exit code: 0 se passou, 1 se falhou
        sys.exit(0 if score >= args.threshold else 1)

    except FileNotFoundError as e:
        print(f"❌ ERRO: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"❌ ERRO inesperado: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
