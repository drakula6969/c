from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config

connect_args = {}
if config.DATABASE_URL.startswith("sqlite"):
    # Нужно, т.к. FastAPI может обращаться к сессии из разных потоков.
    connect_args = {"check_same_thread": False}
    # Убедимся, что директория под файл БД существует.
    config.BASE_DIR.joinpath("data").mkdir(parents=True, exist_ok=True)

engine = create_engine(config.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
