CREATE SCHEMA IF NOT EXISTS exampilot_auth;

CREATE TABLE IF NOT EXISTS exampilot_auth.users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ NULL,
    FOREIGN KEY (user_id)
        REFERENCES public.demo_users (demo_user_id)
        ON DELETE RESTRICT,
    CHECK (username ~ '^[a-z0-9_.-]{3,32}$'),
    CHECK (failed_attempts BETWEEN 0 AND 5)
);
