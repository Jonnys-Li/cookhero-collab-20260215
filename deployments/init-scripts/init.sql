-- init-scripts/init.sql
-- PostgreSQL initialization script for CookHero
-- This script runs when the container is first created

-- Enable UUID extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    user_id VARCHAR(255),
    title VARCHAR(255),
    metadata JSONB
);

-- Create messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    sources JSONB,
    intent VARCHAR(50),
    thinking JSONB
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS ix_conversations_user_updated ON conversations(user_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS ix_messages_conv_created ON messages(conversation_id, created_at);

-- Create function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for auto-updating updated_at on conversations
DROP TRIGGER IF EXISTS update_conversations_updated_at ON conversations;
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users(username);

-- Add occupation and bio columns to users table (profile fields)
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS occupation VARCHAR(100),
  ADD COLUMN IF NOT EXISTS bio TEXT;

-- Optional: index on occupation for filtering
CREATE INDEX IF NOT EXISTS ix_users_occupation ON users(occupation);

-- Grant permissions (if using different roles)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cookhero;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cookhero;

-- Print success message
DO $$
BEGIN
    RAISE NOTICE 'CookHero database initialized successfully!';
END $$;
