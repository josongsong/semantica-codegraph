# TRCR Constraint Reference

Standard constraints for atom matching. Use this as a reference when creating new atoms.

## Argument Type Constraints

### `arg_type: not_const`
**Matches**: Variables, function calls, expressions
**Doesn't match**: String literals, numbers, constants
**Use case**: Injection vulnerabilities (SQL, command, XSS)

```yaml
# Example: SQL injection only when query is dynamic
- base_type: sqlite3.Cursor
  call: execute
  args: [0]
  constraints:
    arg_type: not_const

# Matches: cursor.execute(user_query)
# Ignores: cursor.execute("SELECT * FROM users")
```

### `arg_type: const`
**Matches**: Only literals and constants
**Use case**: Hardcoded secrets, weak crypto detection

```yaml
# Example: Hardcoded password detection
- call: connect
  kwargs: [password]
  constraints:
    arg_type: const

# Matches: db.connect(password="hardcoded")
# Ignores: db.connect(password=env_var)
```

## Keyword Argument Constraints

### `kwargs: [key1, key2]`
**Matches**: When specified keyword arguments are present
**Use case**: Configuration-based vulnerabilities

```yaml
# Example: subprocess with shell=True
- call: subprocess.run
  args: [0]
  kwargs: [shell]
  constraints:
    kwarg_shell: true

# Matches: subprocess.run(cmd, shell=True)
# Ignores: subprocess.run(cmd, shell=False)
```

## Argument Count Constraints

### `arg_count: N`
**Matches**: Exactly N arguments
**Use case**: Distinguishing safe vs unsafe API usage

```yaml
# Example: Parameterized query (2 args = safe)
- base_type: sqlite3.Cursor
  call: execute
  constraints:
    arg_count: 2
  scope: return  # This is a sanitizer

# Matches: cursor.execute("SELECT ?", (id,))
# Ignores: cursor.execute(query)  # Only 1 arg
```

## Value Constraints

### `arg_value: [list]`
**Matches**: When argument is one of the listed values
**Use case**: Specific dangerous configurations

```yaml
# Example: JWT none algorithm
- call: jwt.decode
  kwargs: [algorithms]
  constraints:
    arg_value: ["none", "None", "NONE"]

# Matches: jwt.decode(token, algorithms=["none"])
```

## Pattern Constraints

### `arg_pattern: "regex"`
**Matches**: When argument matches regex pattern
**Use case**: Complex string pattern detection

```yaml
# Example: Weak crypto algorithm
- call: hashlib.new
  args: [0]
  constraints:
    arg_pattern: "md5|sha1|des"
```

## Scope (for Sanitizers)

### `scope: return`
**Effect**: Taint removed from return value
**Use case**: Functions that sanitize and return clean data

```yaml
- call: html.escape
  scope: return

# After: clean = html.escape(dirty)
# 'clean' is no longer tainted
```

### `scope: base`
**Effect**: Taint removed from the object itself
**Use case**: In-place sanitization methods

```yaml
- base_type: str
  call: encode
  scope: base
```

## Propagator Constraints

### `from_args: [indices]`
**Specifies**: Which arguments carry taint
**Use case**: Taint propagation tracking

```yaml
- call: str.format
  from_args: [0, 1, 2]  # All format args
  to: return

# If any arg is tainted, result is tainted
```

### `to: return | base | argN`
**Specifies**: Where taint flows to
**Options**:
- `return`: Return value is tainted
- `base`: Object is tainted
- `arg0`, `arg1`: Specific argument is tainted

## Common Patterns

### Injection Sink
```yaml
- id: sink.sql.example
  kind: sink
  tags: [injection, sql]
  severity: critical
  match:
  - base_type: example.Cursor
    call: execute
    args: [0]
    constraints:
      arg_type: not_const
```

### Parameterized Query Sanitizer
```yaml
- id: barrier.sql.example
  kind: sanitizer
  tags: [sql, safety]
  scope: return
  match:
  - base_type: example.Cursor
    call: execute
    constraints:
      arg_count: 2
    scope: return
```

### String Propagator
```yaml
- id: prop.string.concat
  kind: propagator
  tags: [flow, string]
  match:
  - base_type: str
    call: __add__
    from_args: [0]
    to: return
```
