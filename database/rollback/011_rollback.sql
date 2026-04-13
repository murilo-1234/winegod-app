-- Rollback: remove tabela conversations e indice
DROP INDEX IF EXISTS idx_conversations_user;
DROP TABLE IF EXISTS conversations;
