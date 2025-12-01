from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT, 'data.sqlite')

Base = declarative_base()
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    product_id = Column(String, unique=True, nullable=False)  # e.g., "PRD-001"
    name = Column(String)
    description = Column(Text)
    metadata_json = Column(Text)  # canonical JSON string stored as text
    qr_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(engine)

def add_product(session, product_id, name, description, metadata_json, qr_path):
    p = Product(product_id=product_id, name=name, description=description, metadata_json=metadata_json, qr_path=qr_path)
    session.add(p)
    session.commit()
    return p

def get_product_by_id(session, product_id):
    return session.query(Product).filter_by(product_id=product_id).first()

def list_products(session):
    return session.query(Product).order_by(Product.created_at.desc()).all()
