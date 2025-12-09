-- ============================================================================
-- CHAT TABLES - Community Chat for Tradeul
-- Migration: 006_chat_tables.sql
-- 
-- Features:
-- - Public channels (#general, #trading, etc.)
-- - Private groups with invitations
-- - DMs between users
-- - Ticker mentions with price snapshots
-- - Message reactions
-- - Hypertable for messages (TimescaleDB)
-- ============================================================================

-- ============================================================================
-- CHAT CHANNELS (Public channels like #general, #trading, etc.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    icon VARCHAR(50),                    -- emoji or icon name
    is_default BOOLEAN DEFAULT FALSE,    -- auto-join on signup
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(255),             -- clerk user_id
    CONSTRAINT chat_channels_name_check CHECK (name ~ '^[a-z0-9_-]+$')
);

CREATE INDEX idx_chat_channels_sort ON chat_channels(sort_order);

-- ============================================================================
-- CHAT GROUPS (Private groups with invitations)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    is_dm BOOLEAN DEFAULT FALSE,         -- TRUE = DM between 2 users
    owner_id VARCHAR(255) NOT NULL,      -- clerk user_id of creator
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chat_groups_owner ON chat_groups(owner_id);
CREATE INDEX idx_chat_groups_is_dm ON chat_groups(is_dm);

-- ============================================================================
-- CHAT MEMBERS (Group membership)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES chat_groups(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,       -- clerk user_id
    user_name VARCHAR(255),              -- cached display name
    user_avatar VARCHAR(500),            -- cached avatar URL
    role VARCHAR(20) DEFAULT 'member',   -- 'owner', 'admin', 'member'
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    last_read_at TIMESTAMPTZ,            -- for unread count
    muted_until TIMESTAMPTZ,             -- if muted
    UNIQUE(group_id, user_id)
);

CREATE INDEX idx_chat_members_user ON chat_members(user_id);
CREATE INDEX idx_chat_members_group ON chat_members(group_id);

-- ============================================================================
-- CHAT MESSAGES (Hypertable for scale)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID DEFAULT gen_random_uuid(),
    -- Target: channel_id XOR group_id (one or the other, not both)
    channel_id UUID REFERENCES chat_channels(id) ON DELETE CASCADE,
    group_id UUID REFERENCES chat_groups(id) ON DELETE CASCADE,
    -- Author
    user_id VARCHAR(255) NOT NULL,
    user_name VARCHAR(255) NOT NULL,
    user_avatar VARCHAR(500),
    -- Content
    content TEXT NOT NULL,
    content_type VARCHAR(20) DEFAULT 'text', -- 'text', 'image', 'file', 'ticker'
    -- Metadata
    reply_to_id UUID,                    -- if reply to another message
    mentions TEXT[],                     -- array of user_ids mentioned
    tickers TEXT[],                      -- tickers mentioned ($AAPL)
    ticker_prices JSONB,                 -- {"AAPL": {"price": 150.25, "change": 2.5}}
    attachments JSONB,                   -- [{url, type, name, size}]
    reactions JSONB DEFAULT '{}',        -- {"👍": ["user1", "user2"], "🔥": [...]}
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edited_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,              -- soft delete
    -- Constraint: must have channel_id OR group_id, not both
    CONSTRAINT chat_messages_target_check CHECK (
        (channel_id IS NOT NULL AND group_id IS NULL) OR
        (channel_id IS NULL AND group_id IS NOT NULL)
    ),
    PRIMARY KEY (id, created_at)
);

-- Convert to hypertable (TimescaleDB) for scale
SELECT create_hypertable('chat_messages', 'created_at', 
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Optimized indexes
CREATE INDEX idx_chat_messages_channel ON chat_messages(channel_id, created_at DESC) 
    WHERE channel_id IS NOT NULL;
CREATE INDEX idx_chat_messages_group ON chat_messages(group_id, created_at DESC) 
    WHERE group_id IS NOT NULL;
CREATE INDEX idx_chat_messages_user ON chat_messages(user_id, created_at DESC);
CREATE INDEX idx_chat_messages_mentions ON chat_messages USING GIN(mentions);
CREATE INDEX idx_chat_messages_tickers ON chat_messages USING GIN(tickers);

-- Retention policy (optional): delete messages > 1 year
-- SELECT add_retention_policy('chat_messages', INTERVAL '1 year');

-- ============================================================================
-- CHAT INVITES (Group invitations)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES chat_groups(id) ON DELETE CASCADE,
    inviter_id VARCHAR(255) NOT NULL,    -- who invites
    invitee_id VARCHAR(255) NOT NULL,    -- who is invited
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'accepted', 'declined', 'expired'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days',
    responded_at TIMESTAMPTZ,
    UNIQUE(group_id, invitee_id)         -- no duplicate invites
);

CREATE INDEX idx_chat_invites_invitee ON chat_invites(invitee_id, status);
CREATE INDEX idx_chat_invites_group ON chat_invites(group_id);

-- ============================================================================
-- DEFAULT CHANNELS
-- ============================================================================
INSERT INTO chat_channels (name, description, icon, is_default, sort_order) VALUES
    ('general', 'General trading discussion', '💬', TRUE, 1),
    ('gappers', 'Daily gappers analysis', '📈', FALSE, 2),
    ('smallcaps', 'Small caps discussion', '🎯', FALSE, 3),
    ('news', 'News and catalysts', '📰', FALSE, 4),
    ('support', 'Help and support', '🆘', FALSE, 5)
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to get unread count for a user in a channel/group
CREATE OR REPLACE FUNCTION chat_unread_count(
    p_user_id VARCHAR(255),
    p_channel_id UUID DEFAULT NULL,
    p_group_id UUID DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_last_read TIMESTAMPTZ;
    v_count INTEGER;
BEGIN
    -- Get last read timestamp
    IF p_group_id IS NOT NULL THEN
        SELECT last_read_at INTO v_last_read
        FROM chat_members
        WHERE group_id = p_group_id AND user_id = p_user_id;
    END IF;
    
    -- If no last_read, count all messages
    IF v_last_read IS NULL THEN
        v_last_read := '1970-01-01'::TIMESTAMPTZ;
    END IF;
    
    -- Count unread messages
    SELECT COUNT(*) INTO v_count
    FROM chat_messages
    WHERE (
        (p_channel_id IS NOT NULL AND channel_id = p_channel_id) OR
        (p_group_id IS NOT NULL AND group_id = p_group_id)
    )
    AND created_at > v_last_read
    AND deleted_at IS NULL
    AND user_id != p_user_id;
    
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- Function to update last_read timestamp
CREATE OR REPLACE FUNCTION chat_mark_as_read(
    p_user_id VARCHAR(255),
    p_group_id UUID
) RETURNS VOID AS $$
BEGIN
    UPDATE chat_members
    SET last_read_at = NOW()
    WHERE group_id = p_group_id AND user_id = p_user_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- GRANTS (adjust based on your user)
-- ============================================================================
-- GRANT ALL ON chat_channels TO tradeul_user;
-- GRANT ALL ON chat_groups TO tradeul_user;
-- GRANT ALL ON chat_members TO tradeul_user;
-- GRANT ALL ON chat_messages TO tradeul_user;
-- GRANT ALL ON chat_invites TO tradeul_user;

