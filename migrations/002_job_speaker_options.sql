ALTER TABLE jobs ADD COLUMN speaker_count_mode TEXT DEFAULT 'auto';
ALTER TABLE jobs ADD COLUMN exact_speakers INTEGER;
ALTER TABLE jobs ADD COLUMN min_speakers INTEGER;
ALTER TABLE jobs ADD COLUMN max_speakers INTEGER;
