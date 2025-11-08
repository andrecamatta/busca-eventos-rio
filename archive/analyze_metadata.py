#!/usr/bin/env python3
"""Analisa completude de metadados entre Sonar e Sonar Pro."""

import json
from pathlib import Path

def analyze_metadata(results_file: Path, model_name: str):
    """Analisa completude de metadados dos eventos."""
    with open(results_file) as f:
        results = json.load(f)

    print(f"\n{'=' * 80}")
    print(f"ANÁLISE DE METADADOS: {model_name}")
    print(f"{'=' * 80}\n")

    total_events = 0
    total_with_link = 0
    total_with_valid_link = 0
    total_with_data = 0
    total_with_horario = 0
    total_with_preco = 0
    total_with_descricao = 0

    for category_result in results:
        if not category_result.get('success'):
            continue

        category = category_result['category']
        events = category_result.get('events', [])

        if not events:
            continue

        print(f"📂 {category} ({len(events)} eventos)")
        print(f"{'-' * 80}")

        for event in events:
            total_events += 1
            titulo = event.get('titulo', 'Sem título')[:50]

            # Link
            link = event.get('link_ingresso', '')
            has_link = bool(link and link.strip() and link.lower() not in ['null', 'none', ''])
            is_valid_link = has_link and link.startswith('http')

            if has_link:
                total_with_link += 1
            if is_valid_link:
                total_with_valid_link += 1

            # Data
            data = event.get('data', '')
            has_data = bool(data and data.strip())
            if has_data:
                total_with_data += 1

            # Horário
            horario = event.get('horario', '')
            has_horario = bool(horario and horario.strip())
            if has_horario:
                total_with_horario += 1

            # Preço
            preco = event.get('preco', '')
            has_preco = bool(preco and preco.strip() and preco.lower() not in ['null', 'none'])
            if has_preco:
                total_with_preco += 1

            # Descrição
            desc = event.get('descricao', '')
            has_desc = bool(desc and len(desc) > 20)
            if has_desc:
                total_with_descricao += 1

            # Status visual
            link_status = "✅" if is_valid_link else ("⚠️" if has_link else "❌")
            data_status = "✅" if has_data else "❌"
            hora_status = "✅" if has_horario else "❌"
            preco_status = "✅" if has_preco else "⚠️"
            desc_status = "✅" if has_desc else "⚠️"

            print(f"  • {titulo}")
            print(f"    Link: {link_status}  Data: {data_status}  Horário: {hora_status}  Preço: {preco_status}  Desc: {desc_status}")

            if is_valid_link:
                print(f"    🔗 {link[:80]}")

        print()

    # Resumo final
    print(f"{'=' * 80}")
    print(f"RESUMO - {model_name}")
    print(f"{'=' * 80}\n")

    if total_events > 0:
        print(f"Total de eventos: {total_events}")
        print(f"  Links válidos:  {total_with_valid_link}/{total_events} ({total_with_valid_link/total_events*100:.1f}%)")
        print(f"  Com data:       {total_with_data}/{total_events} ({total_with_data/total_events*100:.1f}%)")
        print(f"  Com horário:    {total_with_horario}/{total_events} ({total_with_horario/total_events*100:.1f}%)")
        print(f"  Com preço:      {total_with_preco}/{total_events} ({total_with_preco/total_events*100:.1f}%)")
        print(f"  Com descrição:  {total_with_descricao}/{total_events} ({total_with_descricao/total_events*100:.1f}%)")

    return {
        'total_events': total_events,
        'links_validos': total_with_valid_link,
        'com_data': total_with_data,
        'com_horario': total_with_horario,
        'com_preco': total_with_preco,
        'com_descricao': total_with_descricao,
    }

if __name__ == "__main__":
    results_dir = Path("test_results")

    # Encontrar arquivos mais recentes
    sonar_files = sorted(results_dir.glob("sonar_results_*.json"))
    sonar_pro_files = sorted(results_dir.glob("sonar_pro_results_*.json"))

    if not sonar_files or not sonar_pro_files:
        print("Arquivos de teste não encontrados!")
        exit(1)

    sonar_file = sonar_files[-1]
    sonar_pro_file = sonar_pro_files[-1]

    print(f"\nAnalisando:")
    print(f"  Sonar:     {sonar_file}")
    print(f"  Sonar Pro: {sonar_pro_file}")

    sonar_stats = analyze_metadata(sonar_file, "Sonar")
    sonar_pro_stats = analyze_metadata(sonar_pro_file, "Sonar Pro")

    # Comparação final
    print(f"\n{'=' * 80}")
    print(f"COMPARAÇÃO FINAL: Sonar vs Sonar Pro")
    print(f"{'=' * 80}\n")

    metrics = [
        ('Total de eventos', 'total_events'),
        ('Links válidos', 'links_validos'),
        ('Com data', 'com_data'),
        ('Com horário', 'com_horario'),
        ('Com preço', 'com_preco'),
        ('Com descrição', 'com_descricao'),
    ]

    print(f"{'Métrica':<20} {'Sonar':>10} {'Sonar Pro':>12} {'Diferença':>15}")
    print(f"{'-' * 80}")

    for label, key in metrics:
        sonar_val = sonar_stats.get(key, 0)
        pro_val = sonar_pro_stats.get(key, 0)
        diff = sonar_val - pro_val
        diff_pct = (diff / pro_val * 100) if pro_val > 0 else 0

        print(f"{label:<20} {sonar_val:>10} {pro_val:>12} {diff:>+8} ({diff_pct:>+5.1f}%)")

    # Qualidade média (score)
    print(f"\n{'=' * 80}")
    print(f"SCORE DE QUALIDADE (média de completude)")
    print(f"{'=' * 80}\n")

    def calc_quality_score(stats):
        if stats['total_events'] == 0:
            return 0
        return (
            (stats['links_validos'] / stats['total_events'] * 100 * 2) +  # Link é 2x importante
            (stats['com_data'] / stats['total_events'] * 100) +
            (stats['com_horario'] / stats['total_events'] * 100) +
            (stats['com_preco'] / stats['total_events'] * 100 * 0.5) +  # Preço é menos crítico
            (stats['com_descricao'] / stats['total_events'] * 100 * 0.5)
        ) / 5

    sonar_score = calc_quality_score(sonar_stats)
    pro_score = calc_quality_score(sonar_pro_stats)

    print(f"Sonar:     {sonar_score:.1f}/100")
    print(f"Sonar Pro: {pro_score:.1f}/100")
    print(f"Diferença: {sonar_score - pro_score:+.1f} pontos")

    # Recomendação
    print(f"\n{'=' * 80}")
    print(f"RECOMENDAÇÃO BASEADA EM METADADOS")
    print(f"{'=' * 80}\n")

    if sonar_score >= pro_score * 0.85:  # Sonar mantém 85%+ da qualidade
        print("✅ Sonar mantém qualidade similar ou superior aos metadados")
        print(f"   Score: {sonar_score:.1f}/100 vs {pro_score:.1f}/100")
        print("   Migração para Sonar é SEGURA")
    elif sonar_score >= pro_score * 0.70:
        print("⚠️  Sonar tem qualidade ligeiramente inferior nos metadados")
        print(f"   Score: {sonar_score:.1f}/100 vs {pro_score:.1f}/100")
        print("   Considerar teste mais amplo antes de migrar")
    else:
        print("❌ Sonar tem qualidade significativamente inferior")
        print(f"   Score: {sonar_score:.1f}/100 vs {pro_score:.1f}/100")
        print("   Manter Sonar Pro recomendado")
