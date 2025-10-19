"""
File writing component for code generation.

Handles file writing with directory creation and optional backup.
"""

from pathlib import Path
from typing import Union


class FileWriter:
    """Handles file writing with directory creation and optional backup."""
    
    def write_file(self, file_path: Union[str, Path], content: str, backup: bool = False) -> None:
        """
        Write content to a file, creating directories as needed.
        
        Args:
            file_path: Path where to write the file
            content: Content to write to the file
            backup: If True, backup existing file with .bak extension
        """
        file_path = Path(file_path)
        
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup existing file if requested and it exists
        if backup and file_path.exists():
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            file_path.rename(backup_path)
        
        # Write the new content
        file_path.write_text(content, encoding='utf-8')

