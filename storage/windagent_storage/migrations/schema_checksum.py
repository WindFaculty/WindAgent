"""
Schema Checksum for WindAgent Storage Layer.
Computes and verifies schema checksums to detect schema drift.
"""

from __future__ import annotations
import hashlib
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import Engine, MetaData, Table, inspect
from sqlalchemy.orm import DeclarativeBase


class SchemaChecksum:
    """
    Computes checksums for database schemas.
    
    Checksums are computed from:
    - Table names
    - Column names, types, and constraints
    - Indexes
    - Foreign key constraints
    - Primary key constraints
    """
    
    @staticmethod
    def compute_table_checksum(table: Table) -> str:
        """Compute checksum for a single table."""
        table_info: Dict[str, Any] = {
            "name": table.name,
            "columns": [],
            "indexes": [],
            "primary_key": [],
            "foreign_keys": [],
            "constraints": [],
        }
        
        # Process columns
        for column in table.columns:
            col_info = {
                "name": column.name,
                "type": str(column.type),
                "nullable": column.nullable,
                "default": str(column.default) if column.default else None,
                "autoincrement": getattr(column, "autoincrement", False),
                "primary_key": column.primary_key,
                "unique": column.unique,
            }
            table_info["columns"].append(col_info)
        
        # Process primary key
        if table.primary_key:
            table_info["primary_key"] = [pk.name for pk in table.primary_key.columns]
        
        # Process foreign keys
        for fk in table.foreign_keys:
            fk_info = {
                "name": fk.name,
                "column": fk.column.name,
                "target_table": fk.column.table.name,
                "target_column": fk.target_fullname,
            }
            table_info["foreign_keys"].append(fk_info)
        
        # Process indexes
        for index in table.indexes:
            index_info = {
                "name": index.name,
                "columns": [c.name for c in index.columns],
                "unique": index.unique,
            }
            table_info["indexes"].append(index_info)
        
        # Process table constraints
        for constraint in table.constraints:
            if constraint is not table.primary_key:
                constraint_info = {
                    "name": constraint.name,
                    "type": type(constraint).__name__,
                }
                table_info["constraints"].append(constraint_info)
        
        # Sort for deterministic ordering
        table_info["columns"].sort(key=lambda x: x["name"])
        table_info["indexes"].sort(key=lambda x: x["name"])
        table_info["foreign_keys"].sort(key=lambda x: x["name"])
        table_info["constraints"].sort(key=lambda x: x["name"])
        
        # Compute checksum
        json_str = json.dumps(table_info, sort_keys=True)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    
    @staticmethod
    def compute_schema_checksum(metadata: MetaData) -> str:
        """Compute checksum for entire schema."""
        table_checksums: List[str] = []
        
        for table in metadata.tables.values():
            table_checksum = SchemaChecksum.compute_table_checksum(table)
            table_checksums.append(f"{table.name}:{table_checksum}")
        
        # Sort by table name for deterministic ordering
        table_checksums.sort()
        
        # Compute overall checksum
        json_str = json.dumps(table_checksums, sort_keys=False)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    
    @staticmethod
    def compute_checksum_from_engine(engine: Engine) -> str:
        """Compute checksum directly from engine."""
        metadata = MetaData()
        metadata.reflect(bind=engine)
        return SchemaChecksum.compute_schema_checksum(metadata)
    
    @staticmethod
    def compute_checksum_from_orm_base(base_class: Type[DeclarativeBase]) -> str:
        """Compute checksum from SQLAlchemy ORM base class."""
        metadata = base_class.metadata
        return SchemaChecksum.compute_schema_checksum(metadata)
    
    @staticmethod
    def verify_checksum(engine: Engine, expected_checksum: str) -> bool:
        """Verify current schema matches expected checksum."""
        actual_checksum = SchemaChecksum.compute_checksum_from_engine(engine)
        return actual_checksum == expected_checksum
    
    @staticmethod
    def get_schema_snapshot(metadata: MetaData) -> Dict[str, Any]:
        """Get complete schema snapshot for audit purposes."""
        snapshot: Dict[str, Any] = {
            "tables": {},
            "checksum": None,
        }
        
        table_checksums = []
        for table in metadata.tables.values():
            table_info: Dict[str, Any] = {
                "columns": {},
                "primary_key": [],
                "foreign_keys": [],
                "indexes": [],
            }
            
            for column in table.columns:
                table_info["columns"][column.name] = {
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "default": str(column.default) if column.default else None,
                    "primary_key": column.primary_key,
                    "unique": column.unique,
                }
            
            if table.primary_key:
                table_info["primary_key"] = [pk.name for pk in table.primary_key.columns]
            
            for fk in table.foreign_keys:
                table_info["foreign_keys"].append({
                    "column": fk.column.name,
                    "target": fk.target_fullname,
                })
            
            for index in table.indexes:
                table_info["indexes"].append({
                    "name": index.name,
                    "columns": [c.name for c in index.columns],
                    "unique": index.unique,
                })
            
            snapshot["tables"][table.name] = table_info
            table_checksum = SchemaChecksum.compute_table_checksum(table)
            table_checksums.append(f"{table.name}:{table_checksum}")
        
        table_checksums.sort()
        snapshot["checksum"] = hashlib.sha256(json.dumps(table_checksums).encode()).hexdigest()
        
        return snapshot
