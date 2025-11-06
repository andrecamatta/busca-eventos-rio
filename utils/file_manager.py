"""Utilitário para gerenciamento de arquivos de eventos."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class EventFileManager:
    """Responsável por salvar e carregar eventos em diferentes formatos."""

    def __init__(self, output_dir: str | Path = "output"):
        """
        Inicializa o gerenciador de arquivos.

        Args:
            output_dir: Diretório onde arquivos serão salvos
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def save_json(self, data: dict | str, filename: str) -> Path:
        """
        Salva dados em arquivo JSON.

        Args:
            data: Dados para salvar (dict ou string JSON)
            filename: Nome do arquivo (ex: "eventos.json")

        Returns:
            Path do arquivo salvo

        Raises:
            ValueError: Se data é string e não é JSON válido
        """
        filepath = self.output_dir / filename

        # Converter string para dict se necessário
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error(f"Não foi possível parsear JSON para {filename}: {e}")
                raise ValueError(f"JSON inválido: {str(e)}")

        # Salvar com formatação bonita
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"✓ Salvo: {filepath}")
        return filepath

    def save_text(self, text: str, filename: str) -> Path:
        """
        Salva texto em arquivo.

        Args:
            text: Conteúdo de texto
            filename: Nome do arquivo (ex: "eventos.txt")

        Returns:
            Path do arquivo salvo
        """
        filepath = self.output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)

        logger.info(f"✓ Salvo: {filepath}")
        return filepath

    def load_json(self, filename: str) -> dict:
        """
        Carrega dados de arquivo JSON.

        Args:
            filename: Nome do arquivo

        Returns:
            Dicionário com dados carregados

        Raises:
            FileNotFoundError: Se arquivo não existe
            json.JSONDecodeError: Se arquivo não é JSON válido
        """
        filepath = self.output_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_text(self, filename: str) -> str:
        """
        Carrega texto de arquivo.

        Args:
            filename: Nome do arquivo

        Returns:
            Conteúdo do arquivo como string

        Raises:
            FileNotFoundError: Se arquivo não existe
        """
        filepath = self.output_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def list_files(self, pattern: str = "*") -> list[Path]:
        """
        Lista arquivos no diretório de output.

        Args:
            pattern: Padrão glob (ex: "*.json", "eventos_*.txt")

        Returns:
            Lista de Paths dos arquivos encontrados
        """
        return sorted(self.output_dir.glob(pattern))

    def clear_output(self, pattern: str = "*"):
        """
        Remove arquivos do diretório de output.

        Args:
            pattern: Padrão glob dos arquivos a remover
        """
        files = self.list_files(pattern)
        for file in files:
            file.unlink()
            logger.info(f"🗑️  Removido: {file}")

        logger.info(f"✓ {len(files)} arquivo(s) removido(s)")
