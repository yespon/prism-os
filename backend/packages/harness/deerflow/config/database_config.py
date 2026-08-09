from pydantic import BaseModel, Field


class AuthDatabaseConfig(BaseModel):
    """Database configuration for Better Auth identity tables (user, account, session)."""
    type: str = Field(default="sqlite", description="Database type: sqlite, postgres")
    url: str = Field(default="sqlite+aiosqlite:///.prismos/auth.db", description="Database connection URL for auth tables")


class DatabaseConfig(BaseModel):
    """Database configuration for storage of configurations and tenant data."""
    type: str = Field(default="sqlite", description="Database type: sqlite, postgres")
    url: str = Field(default="sqlite+aiosqlite:///.prismos/tenant.db", description="Database connection URL")
    echo: bool = Field(default=False, description="Whether to echo SQL logs")
    auth: AuthDatabaseConfig = Field(default_factory=AuthDatabaseConfig, description="Auth database configuration (Better Auth identity tables)")
