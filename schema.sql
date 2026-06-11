-- =============================================================
-- realtime-hub database schema
-- =============================================================

CREATE TABLE users (
    id         SERIAL PRIMARY KEY,
    username   VARCHAR(50)  NOT NULL UNIQUE,
    email      VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_users_username ON users (username);
CREATE INDEX ix_users_email    ON users (email);


CREATE TABLE channels (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL UNIQUE,
    creator_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_channels_creator_id ON channels (creator_id);


CREATE TABLE messages (
    id         SERIAL PRIMARY KEY,
    channel_id INTEGER     NOT NULL REFERENCES channels (id) ON DELETE CASCADE,
    user_id    INTEGER              REFERENCES users    (id) ON DELETE SET NULL,
    content    TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_messages_channel_id      ON messages (channel_id);
CREATE INDEX ix_messages_user_id         ON messages (user_id);
-- composite: efficient "fetch last N messages in channel" queries
CREATE INDEX ix_messages_channel_created ON messages (channel_id, created_at DESC);


-- many-to-many join table
CREATE TABLE user_channels (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users    (id) ON DELETE CASCADE,
    channel_id INTEGER     NOT NULL REFERENCES channels (id) ON DELETE CASCADE,
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_channel UNIQUE (user_id, channel_id)
);

CREATE INDEX ix_user_channels_user_id    ON user_channels (user_id);
CREATE INDEX ix_user_channels_channel_id ON user_channels (channel_id);


CREATE TABLE notifications (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users    (id) ON DELETE CASCADE,
    message_id INTEGER     NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
    is_read    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_notification_user_message UNIQUE (user_id, message_id)
);

CREATE INDEX ix_notifications_user_id    ON notifications (user_id);
CREATE INDEX ix_notifications_message_id ON notifications (message_id);
-- covers the common query: "unread notifications for user X"
CREATE INDEX ix_notifications_user_unread ON notifications (user_id, is_read);


-- append-only audit log; rows are never updated or deleted
CREATE TABLE events (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER              REFERENCES users (id) ON DELETE SET NULL,
    action     VARCHAR(100) NOT NULL,
    data       JSONB,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_events_user_id    ON events (user_id);
CREATE INDEX ix_events_action     ON events (action);
CREATE INDEX ix_events_created_at ON events (created_at DESC);
-- GIN index enables querying inside the JSON payload
CREATE INDEX ix_events_data       ON events USING GIN (data);
