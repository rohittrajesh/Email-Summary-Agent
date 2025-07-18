# src/email_summarizer/models.py

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
import datetime

Base = declarative_base()

class Mail(Base):
    __tablename__ = "mail"
    id             = Column(Integer, primary_key=True)
    message_id     = Column(String, unique=True, nullable=False)
    sender         = Column(String, nullable=False)
    subject        = Column(String)
    body_plain     = Column(Text)
    body_html      = Column(Text)
    status         = Column(String, default="pending")  # pending, completed, failed
    summary        = Column(Text)
    category       = Column(String)
    failure_reason = Column(Text)
    created_at     = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at     = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow
    )

    contents = relationship("MailContent", back_populates="mail")


class SkippedMail(Base):
    __tablename__ = "skipped_mail"
    id         = Column(Integer, primary_key=True)
    mail_id    = Column(Integer, ForeignKey("mail.id"), nullable=False)
    reason     = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class MailContent(Base):
    __tablename__ = "mail_content"
    id         = Column(Integer, primary_key=True)
    mail_id    = Column(Integer, ForeignKey("mail.id"), nullable=False)
    name       = Column(String, nullable=False)
    value      = Column(String)
    message    = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    mail = relationship("Mail", back_populates="contents")

class Contact(Base):
    __tablename__ = "contacts"

    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    email      = Column(String, nullable=False, unique=True)
    company    = Column(String, default="N/A")
    address    = Column(String, default="N/A")
    phone      = Column(String, default="N/A")
    job_title  = Column(String, default="N/A")
    importance = Column(
        String,
        default="LESS IMPORTANT",
        nullable=False,
        doc="‘HIGHLY IMPORTANT’ or ‘LESS IMPORTANT’"
    )