-- Auth identity tables for Better Auth.
-- Run after the databases are created (init-databases.sql).
-- Target database: prismos_auth_db

-- user identity table (managed by Better Auth, augmented with custom fields)
CREATE TABLE IF NOT EXISTS "user" (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    "emailVerified" INTEGER NOT NULL DEFAULT 0,
    image TEXT,
    "createdAt" TEXT NOT NULL,
    "updatedAt" TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    status TEXT DEFAULT 'active',
    "mustChangePassword" INTEGER DEFAULT 0,
    "isBootstrapAdmin" INTEGER DEFAULT 0
);

-- account / credential table (Better Auth)
CREATE TABLE IF NOT EXISTS account (
    id TEXT NOT NULL PRIMARY KEY,
    "accountId" TEXT NOT NULL,
    "providerId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    password TEXT,
    "createdAt" TEXT NOT NULL,
    "updatedAt" TEXT NOT NULL
);

-- session table (Better Auth)
CREATE TABLE IF NOT EXISTS session (
    id TEXT NOT NULL PRIMARY KEY,
    "expiresAt" TEXT NOT NULL,
    token TEXT NOT NULL,
    "createdAt" TEXT NOT NULL,
    "updatedAt" TEXT NOT NULL,
    "ipAddress" TEXT,
    "userAgent" TEXT,
    "userId" TEXT NOT NULL
);

-- email verification table (Better Auth)
CREATE TABLE IF NOT EXISTS verification (
    id TEXT NOT NULL PRIMARY KEY,
    identifier TEXT NOT NULL,
    value TEXT NOT NULL,
    "expiresAt" TEXT NOT NULL,
    "createdAt" TEXT,
    "updatedAt" TEXT
);

-- JWKS key table (Better Auth JWT plugin)
CREATE TABLE IF NOT EXISTS jwks (
    id TEXT NOT NULL PRIMARY KEY,
    "publicKey" TEXT NOT NULL,
    "privateKey" TEXT NOT NULL,
    "createdAt" TEXT NOT NULL,
    "expiresAt" TEXT
);

-- useful indexes
CREATE INDEX IF NOT EXISTS idx_user_email ON "user" (email);
CREATE INDEX IF NOT EXISTS idx_account_userId ON account ("userId");
CREATE INDEX IF NOT EXISTS idx_session_userId ON session ("userId");
CREATE INDEX IF NOT EXISTS idx_session_token ON session (token);
