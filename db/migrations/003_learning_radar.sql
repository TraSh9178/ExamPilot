CREATE TABLE IF NOT EXISTS radar_flags (
    demo_user_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (demo_user_id, course_id, topic_id),
    FOREIGN KEY (demo_user_id)
        REFERENCES demo_users (demo_user_id)
        ON DELETE CASCADE,
    CHECK (reason IS NULL OR reason IN ('concept', 'calculation', 'wording', 'start'))
);
CREATE INDEX IF NOT EXISTS radar_flags_course_topic_idx
    ON radar_flags (course_id, topic_id);
