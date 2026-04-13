-- Rollback 012: Remove saved flag from conversations

DROP INDEX IF EXISTS idx_conversations_saved;
ALTER TABLE conversations DROP COLUMN IF EXISTS saved_at;
ALTER TABLE conversations DROP COLUMN IF EXISTS is_saved;
