CREATE TABLE IF NOT EXISTS demo_users (
    demo_user_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(btrim(demo_user_id)) BETWEEN 1 AND 100)
);

CREATE TABLE IF NOT EXISTS courses (
    demo_user_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    course_name TEXT NOT NULL,
    package_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (demo_user_id, course_id),
    FOREIGN KEY (demo_user_id)
        REFERENCES demo_users (demo_user_id)
        ON DELETE CASCADE,
    CHECK (jsonb_typeof(package_json) = 'object')
);

CREATE TABLE IF NOT EXISTS exam_sessions (
    demo_user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('mock', 'topic')),
    question_ids JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (demo_user_id, session_id),
    FOREIGN KEY (demo_user_id, course_id)
        REFERENCES courses (demo_user_id, course_id)
        ON DELETE CASCADE,
    CHECK (jsonb_typeof(question_ids) = 'array')
);

CREATE INDEX IF NOT EXISTS exam_sessions_history_idx
    ON exam_sessions (demo_user_id, course_id, created_at);

CREATE TABLE IF NOT EXISTS attempt_results (
    demo_user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    selected_index SMALLINT NULL
        CHECK (selected_index IS NULL OR selected_index BETWEEN 0 AND 3),
    is_correct BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (demo_user_id, session_id, question_id),
    FOREIGN KEY (demo_user_id, session_id)
        REFERENCES exam_sessions (demo_user_id, session_id)
        ON DELETE CASCADE,
    CHECK (selected_index IS NOT NULL OR is_correct = FALSE)
);
