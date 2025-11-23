-- Sample data for testing

-- Sample repository node
INSERT INTO nodes (id, type, name, path) VALUES
('repo:test', 'repository', 'test-repo', '/path/to/repo')
ON CONFLICT (id) DO NOTHING;

-- Sample file node
INSERT INTO nodes (id, type, name, path, language, file_hash) VALUES
('file:test.py', 'file', 'test.py', '/path/to/repo/test.py', 'python', 'abc123')
ON CONFLICT (id) DO NOTHING;

-- Sample symbol node
INSERT INTO nodes (id, type, name, path, language, start_line, end_line, signature, file_id) VALUES
('symbol:test_func', 'symbol', 'test_func', '/path/to/repo/test.py', 'python', 1, 10, 'def test_func():', 'file:test.py')
ON CONFLICT (id) DO NOTHING;
