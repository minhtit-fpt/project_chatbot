CREATE TABLE IF NOT EXISTS conversations (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(36)     NOT NULL,
    timestamp     DATETIME        NOT NULL,
    question      TEXT            NOT NULL,
    answer        TEXT            NOT NULL,
    sources       JSON,
    latency_ms    INT,
    user_feedback TINYINT         DEFAULT NULL,
    INDEX idx_session   (session_id),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
