"""Evaluation result records (R5, M3 minimal)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Index, String, Text
from sqlmodel import Field, SQLModel


class EvaluationResultRecord(SQLModel, table=True):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        Index("ix_evaluation_tenant_version", "tenant_id", "version_id"),
    )

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    version_id: str = Field(sa_column=Column(String(64), nullable=False))
    dataset: str = Field(sa_column=Column(String(128), nullable=False))
    score: float = Field(sa_column=Column(Float, nullable=False))
    passed: bool = Field(nullable=False)
    details_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
