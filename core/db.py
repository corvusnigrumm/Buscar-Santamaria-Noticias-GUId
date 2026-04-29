import os
import hashlib
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from core.logger import logger
from dotenv import load_dotenv

load_dotenv()

# Configuración de rutas
DATA_DIR = os.getenv("BUSCADOR_NOTICIAS_DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "historico.db")

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
Base = declarative_base()

class ArticuloHistorico(Base):
    __tablename__ = 'articulos_historico'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    url_hash = Column(String(64), unique=True, nullable=False, index=True)
    url = Column(String(1000), nullable=False)
    titulo = Column(String(500))
    fuente = Column(String(100))
    categoria = Column(String(50))
    fecha_publicacion = Column(String(50))
    fecha_registro = Column(DateTime, default=datetime.utcnow)

class MedioProhibido(Base):
    __tablename__ = 'medios_prohibidos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ancla = Column(String(200), unique=True, nullable=False, index=True)
    nombre_medio = Column(String(100))
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    
class OllamaCache(Base):
    __tablename__ = 'ollama_cache'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    texto_hash = Column(String(64), unique=True, nullable=False, index=True)
    es_relevante = Column(Boolean, nullable=False)
    fecha_consulta = Column(DateTime, default=datetime.utcnow)

# Crear tablas
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class DBManager:
    @staticmethod
    def get_session():
        return SessionLocal()
    
    @staticmethod
    def hash_string(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    @staticmethod
    def existe_articulo(url: str) -> bool:
        url_hash = DBManager.hash_string(url)
        with DBManager.get_session() as session:
            return session.query(ArticuloHistorico).filter_by(url_hash=url_hash).first() is not None

    @staticmethod
    def registrar_articulo(url: str, titulo: str, fuente: str, categoria: str, fecha_publicacion: str):
        url_hash = DBManager.hash_string(url)
        with DBManager.get_session() as session:
            if not session.query(ArticuloHistorico).filter_by(url_hash=url_hash).first():
                nuevo = ArticuloHistorico(
                    url_hash=url_hash, url=url, titulo=titulo, 
                    fuente=fuente, categoria=categoria, fecha_publicacion=fecha_publicacion
                )
                session.add(nuevo)
                session.commit()

    @staticmethod
    def limpiar_historial_articulos(max_records=4000):
        with DBManager.get_session() as session:
            count = session.query(ArticuloHistorico).count()
            if count > max_records:
                # Borrar los más antiguos
                to_delete = count - max_records
                ids = session.query(ArticuloHistorico.id).order_by(ArticuloHistorico.fecha_registro.asc()).limit(to_delete).all()
                if ids:
                    ids_to_delete = [i[0] for i in ids]
                    session.query(ArticuloHistorico).filter(ArticuloHistorico.id.in_(ids_to_delete)).delete(synchronize_session=False)
                    session.commit()
                    logger.info(f"Se limpiaron {to_delete} artículos antiguos del historial.")

    # ------ Medios Prohibidos ------
    @staticmethod
    def existe_medio_prohibido(ancla: str) -> bool:
        with DBManager.get_session() as session:
            return session.query(MedioProhibido).filter_by(ancla=ancla).first() is not None

    @staticmethod
    def registrar_medio_prohibido(ancla: str, nombre_medio: str):
        with DBManager.get_session() as session:
            if not session.query(MedioProhibido).filter_by(ancla=ancla).first():
                nuevo = MedioProhibido(ancla=ancla, nombre_medio=nombre_medio)
                session.add(nuevo)
                session.commit()

    # ------ Ollama Cache ------
    @staticmethod
    def obtener_cache_ollama(texto: str):
        texto_hash = DBManager.hash_string(texto)
        with DBManager.get_session() as session:
            record = session.query(OllamaCache).filter_by(texto_hash=texto_hash).first()
            if record:
                return record.es_relevante
            return None

    @staticmethod
    def guardar_cache_ollama(texto: str, es_relevante: bool):
        texto_hash = DBManager.hash_string(texto)
        with DBManager.get_session() as session:
            if not session.query(OllamaCache).filter_by(texto_hash=texto_hash).first():
                nuevo = OllamaCache(texto_hash=texto_hash, es_relevante=es_relevante)
                session.add(nuevo)
                session.commit()
