"""Teste de scraping do Blue Note Rio usando requests + BeautifulSoup."""

import httpx
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

def parse_month(month_str: str) -> str:
    """Converte mês abreviado para número."""
    months = {
        'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04',
        'mai': '05', 'jun': '06', 'jul': '07', 'ago': '08',
        'set': '09', 'out': '10', 'nov': '11', 'dez': '12'
    }
    return months.get(month_str.lower()[:3], '01')

def test_blue_note_scraping():
    """Testa extração de eventos do Blue Note Rio."""

    url = "https://bluenoterio.com.br/shows/"

    print("=" * 80)
    print("🎷 BLUE NOTE RIO - TESTE DE SCRAPING")
    print("=" * 80)
    print(f"URL: {url}\n")

    try:
        # Fazer request HTTP
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)

        print(f"✓ Status: {response.status_code}")
        print(f"✓ Tamanho: {len(response.text)} bytes\n")

        # Parse HTML com BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # Encontrar todos os artigos de eventos
        articles = soup.find_all('article')

        print("=" * 80)
        print(f"EXTRAÇÃO DE EVENTOS (encontrados {len(articles)} articles)")
        print("=" * 80)
        print()

        eventos = []

        for i, article in enumerate(articles, 1):
            try:
                # Extrair data: <p class='post-date'><span>08</span>nov</p>
                date_elem = article.find('p', class_='post-date')
                if not date_elem:
                    continue

                day_elem = date_elem.find('span')
                day = day_elem.get_text(strip=True) if day_elem else None
                month_text = date_elem.get_text(strip=True).replace(day, '') if day else None

                if not day or not month_text:
                    continue

                month = parse_month(month_text)
                year = "2025"  # Assumir 2025
                data = f"{day.zfill(2)}/{month}/{year}"

                # Extrair horário: <p class='post-time'>20H00</p>
                time_elem = article.find('p', class_='post-time')
                horario = time_elem.get_text(strip=True) if time_elem else None

                # Extrair título: <h2 class="blog-shortcode-post-title entry-title"><a>TÍTULO</a></h2>
                title_elem = article.find('h2', class_='blog-shortcode-post-title')
                if not title_elem:
                    continue

                title_link = title_elem.find('a')
                titulo = title_link.get_text(strip=True) if title_link else None
                page_link = title_link.get('href') if title_link else None

                if not titulo:
                    continue

                # Construir evento
                evento = {
                    "titulo": titulo,
                    "data": data,
                    "horario": horario,
                    "local": "Blue Note Rio",
                    "page_url": page_link,
                }

                eventos.append(evento)

                print(f"[{i}] {titulo}")
                print(f"    📅 {data} às {horario}")
                print(f"    🔗 {page_link}")
                print()

            except Exception as e:
                print(f"⚠️  Erro ao processar article {i}: {e}")
                continue

        # Resultado final
        print("=" * 80)
        print("RESULTADO FINAL")
        print("=" * 80)
        print(f"✅ {len(eventos)} eventos extraídos com sucesso!\n")

        if eventos:
            # Mostrar JSON formatado
            print("JSON estruturado:")
            print(json.dumps(eventos, ensure_ascii=False, indent=2))

            # Estatísticas
            datas_unicas = set(e['data'] for e in eventos)
            print(f"\n📊 Estatísticas:")
            print(f"   - {len(eventos)} eventos totais")
            print(f"   - {len(datas_unicas)} datas únicas: {sorted(datas_unicas)}")

            print("\n✅ CONCLUSÃO: Scraping VIÁVEL com requests + BeautifulSoup!")
            print("   - Todos os dados necessários estão no HTML inicial")
            print("   - Não precisa de Playwright/Selenium")
        else:
            print("❌ Nenhum evento encontrado - verificar estrutura HTML")

        # Salvar HTML para debug
        with open('/tmp/blue_note_html.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n💾 HTML salvo em: /tmp/blue_note_html.html")

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_blue_note_scraping()
