"""
HTTP Client centralizado com retry, parsing e tratamento de erros.
Elimina duplicação de código HTTP em validation_agent e verify_agent.
"""

import logging
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from config import HTTP_TIMEOUT, MAX_RETRIES

logger = logging.getLogger(__name__)


class HttpClientWrapper:
    """
    Wrapper centralizado para operações HTTP com retry automático e parsing.

    Fornece métodos convenientes para:
    - Fetch com retry automático
    - Fetch + parse HTML em uma operação
    - Tratamento padronizado de erros e status codes
    """

    def __init__(self, timeout: int = HTTP_TIMEOUT, max_retries: int = MAX_RETRIES):
        """
        Inicializa HTTP client.

        Args:
            timeout: Timeout em segundos para requests (padrão: de config)
            max_retries: Número máximo de tentativas em caso de falha (padrão: de config)
        """
        self.timeout = timeout
        self.max_retries = max_retries

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
    )
    async def fetch_with_retry(
        self,
        url: str,
        method: str = "GET",
        **kwargs
    ) -> httpx.Response:
        """
        Faz HTTP request com retry automático em caso de timeout/conexão.

        Args:
            url: URL a ser acessada
            method: Método HTTP (GET, HEAD, POST, etc.)
            **kwargs: Parâmetros adicionais para httpx (headers, etc.)

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: Em caso de erro HTTP após todas as tentativas
        """
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True
        ) as client:
            if method.upper() == "GET":
                return await client.get(url, **kwargs)
            elif method.upper() == "HEAD":
                return await client.head(url, **kwargs)
            elif method.upper() == "POST":
                return await client.post(url, **kwargs)
            else:
                raise ValueError(f"Método HTTP não suportado: {method}")

    async def fetch_and_parse(
        self,
        url: str,
        extract_text: bool = True,
        text_max_length: int = 3000,
        clean_html: bool = True
    ) -> Dict[str, Any]:
        """
        Faz fetch de URL e retorna conteúdo parseado.

        Combina HTTP request + BeautifulSoup parsing em uma operação.

        Args:
            url: URL a ser acessada
            extract_text: Se deve extrair texto limpo (padrão: True)
            text_max_length: Comprimento máximo do texto extraído (padrão: 3000)
            clean_html: Se deve remover scripts/styles (padrão: True)

        Returns:
            Dict com:
            - status_code: HTTP status code
            - success: True se 200 OK
            - soup: BeautifulSoup object (ou None se erro)
            - text: Texto extraído e limpo (ou "" se erro)
            - html: HTML raw (ou "" se erro)
            - error: Mensagem de erro (ou None se sucesso)

        Examples:
            >>> client = HttpClientWrapper()
            >>> result = await client.fetch_and_parse("https://example.com")
            >>> if result["success"]:
            >>>     print(result["text"])
        """
        try:
            response = await self.fetch_with_retry(url)

            status_code = response.status_code

            if status_code != 200:
                return {
                    "status_code": status_code,
                    "success": False,
                    "soup": None,
                    "text": "",
                    "html": "",
                    "error": f"HTTP {status_code}"
                }

            # Parse HTML com BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Limpar HTML se solicitado
            if clean_html:
                for element in soup(["script", "style", "noscript"]):
                    element.decompose()

            # Extrair texto se solicitado
            page_text = ""
            if extract_text:
                page_text = soup.get_text(separator=' ', strip=True)
                # Normalizar espaços e limitar comprimento
                page_text = " ".join(page_text.split())
                if text_max_length > 0:
                    page_text = page_text[:text_max_length]

            return {
                "status_code": 200,
                "success": True,
                "soup": soup,
                "text": page_text,
                "html": response.text,
                "error": None
            }

        except httpx.TimeoutException:
            logger.warning(f"Timeout ao acessar {url}")
            return {
                "status_code": None,
                "success": False,
                "soup": None,
                "text": "",
                "html": "",
                "error": "Timeout"
            }

        except Exception as e:
            logger.error(f"Erro ao fazer fetch de {url}: {e}")
            return {
                "status_code": None,
                "success": False,
                "soup": None,
                "text": "",
                "html": "",
                "error": str(e)
            }

    async def check_link_status(self, url: str) -> Dict[str, Any]:
        """
        Verifica status de um link (usa HEAD request quando possível).

        Mais rápido que fetch completo para apenas checar se link está acessível.

        Args:
            url: URL a ser verificada

        Returns:
            Dict com:
            - accessible: True se link acessível (200 OK)
            - status_code: HTTP status code
            - reason: Mensagem descritiva
        """
        try:
            # Tentar HEAD primeiro (mais rápido)
            response = await self.fetch_with_retry(url, method="HEAD")
            status_code = response.status_code

            # Se HEAD não retornar 200, tentar GET (alguns servidores não suportam HEAD)
            if status_code not in [200, 301, 302]:
                response = await self.fetch_with_retry(url, method="GET")
                status_code = response.status_code

            if status_code == 200:
                return {
                    "accessible": True,
                    "status_code": 200,
                    "reason": "OK"
                }
            elif status_code == 404:
                return {
                    "accessible": False,
                    "status_code": 404,
                    "reason": "Not Found"
                }
            elif status_code == 403:
                return {
                    "accessible": False,
                    "status_code": 403,
                    "reason": "Forbidden"
                }
            elif status_code in [301, 302, 307, 308]:
                # Redirects já são seguidos automaticamente, então isso não deveria acontecer
                return {
                    "accessible": True,
                    "status_code": status_code,
                    "reason": "Redirect (followed)"
                }
            else:
                return {
                    "accessible": False,
                    "status_code": status_code,
                    "reason": f"HTTP {status_code}"
                }

        except httpx.TimeoutException:
            return {
                "accessible": False,
                "status_code": None,
                "reason": "Timeout"
            }

        except Exception as e:
            return {
                "accessible": False,
                "status_code": None,
                "reason": f"Error: {str(e)}"
            }


# Singleton global para uso conveniente (opcional)
_default_client: Optional[HttpClientWrapper] = None


def get_http_client() -> HttpClientWrapper:
    """
    Retorna instância global do HTTP client (singleton).

    Útil quando não precisa customizar timeout/retries.
    """
    global _default_client
    if _default_client is None:
        _default_client = HttpClientWrapper()
    return _default_client
