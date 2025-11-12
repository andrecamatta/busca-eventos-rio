"""Utilitário para gerenciamento de arquivos de eventos."""

import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class EventFileManager:
    """Responsável por salvar e carregar eventos em diferentes formatos."""

    def __init__(self, output_dir: str | Path = "output", use_timestamp: bool = True):
        """
        Inicializa o gerenciador de arquivos.

        Args:
            output_dir: Diretório base onde arquivos serão salvos
            use_timestamp: Se True, cria subpasta com timestamp da execução
        """
        self.base_output_dir = Path(output_dir)
        self.base_output_dir.mkdir(exist_ok=True)

        if use_timestamp:
            # Criar pasta com timestamp: YYYY-MM-DD_HH-MM-SS
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.output_dir = self.base_output_dir / timestamp
            self.output_dir.mkdir(exist_ok=True)

            # Criar/atualizar symlink 'latest' apontando para esta execução
            self._update_latest_symlink()
        else:
            self.output_dir = self.base_output_dir

    def _update_latest_symlink(self):
        """Cria ou atualiza symlink 'latest' para a pasta da execução atual."""
        latest_link = self.base_output_dir / "latest"

        # Remover symlink/diretório antigo se existir (com retry para Windows)
        if latest_link.exists() or latest_link.is_symlink():
            for attempt in range(3):
                try:
                    if latest_link.is_dir() and not latest_link.is_symlink():
                        # É um diretório real, não um symlink - remover com shutil
                        shutil.rmtree(latest_link, ignore_errors=True)
                    else:
                        # É um symlink - remover com unlink
                        latest_link.unlink()
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.5)  # Aguardar e tentar novamente
                    else:
                        logger.warning(f"⚠️  Não foi possível remover '{latest_link}' (em uso). Pulando atualização do link 'latest'.")
                        return

        # Criar novo symlink relativo (fallback para diretório se symlink falhar no Windows)
        relative_target = self.output_dir.name
        try:
            latest_link.symlink_to(relative_target)
            logger.info(f"✓ Symlink 'latest' atualizado: {latest_link} -> {relative_target}")
        except (OSError, NotImplementedError):
            # Windows sem privilégios de admin - criar diretório junction como fallback
            try:
                import subprocess
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(latest_link), str(self.output_dir)],
                    check=True,
                    capture_output=True
                )
                logger.info(f"✓ Diretório 'latest' criado (Windows): {latest_link}")
            except Exception as e:
                logger.warning(f"⚠️  Não foi possível criar link 'latest': {e}")

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
