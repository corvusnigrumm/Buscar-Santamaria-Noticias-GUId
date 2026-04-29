import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(log_dir="logs", level=logging.INFO):
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("BNAS")
    logger.setLevel(level)
    
    if logger.hasHandlers():
        logger.handlers.clear()
        
    formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (rotates at 5MB, keeps last 5)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "bnas_errores.log"),
        maxBytes=5*1024*1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    # Only log warnings and above to the file by default to avoid huge logs
    file_handler.setLevel(logging.WARNING) 
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()
