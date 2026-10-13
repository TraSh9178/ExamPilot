-- Additive checks: existing rows remain readable for application validation.
-- PostgreSQL enforces NOT VALID checks on all subsequent inserts and updates.
ALTER TABLE courses ADD CONSTRAINT course_package_identity_matches
    CHECK (package_json ? 'course_id' AND package_json ->> 'course_id' = course_id) NOT VALID;
ALTER TABLE exam_sessions ADD CONSTRAINT session_questions_not_empty
    CHECK (jsonb_array_length(question_ids) > 0) NOT VALID;
