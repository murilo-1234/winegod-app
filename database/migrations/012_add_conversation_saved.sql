-- 012: Add saved flag to conversations (favoritos v1 = conversas salvas)

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS is_saved BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS saved_at TIMESTAMP NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_saved
ON conversations(user_id, is_saved, saved_at DESC NULLS LAST, updated_at DESC);
