#!/bin/bash
# TRCR Batch Rule Generator - 대량 룰 자동 생성
# Usage: bash scripts/batch_generate_rules.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_ROOT/packages/codegraph-trcr/rules/atoms/extended"

cd "$PROJECT_ROOT"

echo "========================================================================"
echo "🚀 TRCR Batch Rule Generator"
echo "========================================================================"
echo ""

# =============================================================================
# Phase 1: Information Disclosure (10개)
# =============================================================================
echo "📦 Phase 1: Information Disclosure Rules (10개)"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.stack_trace \
  --cwe CWE-209 --owasp "A09:2021-Security Logging and Monitoring Failures" \
  --severity high \
  --patterns "traceback.format_exc:0,traceback.print_exc:0,sys.exc_info:0" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.debug_info \
  --cwe CWE-200 --severity medium \
  --patterns "pprint.pprint:0,pdb.set_trace:0" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.error_message \
  --cwe CWE-209 --severity high \
  --patterns "Exception:0,ValueError:0,RuntimeError:0" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.sql_error \
  --cwe CWE-209 --severity high \
  --patterns "sqlite3.Error,psycopg2.Error,pymysql.err.Error" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.path_disclosure \
  --cwe CWE-200 --severity medium \
  --patterns "__file__,os.getcwd:0,os.path.abspath:0" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.session_info \
  --cwe CWE-532 --severity high \
  --patterns "session.session_key,request.session" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.config_exposure \
  --cwe CWE-200 --severity critical \
  --patterns "os.environ,settings.SECRET_KEY,settings.DATABASE_PASSWORD" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.source_code \
  --cwe CWE-540 --severity medium \
  --patterns "inspect.getsource:0,inspect.getsourcefile:0" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.user_enumeration \
  --cwe CWE-200 --severity medium \
  --patterns "User.objects.get:0,User.objects.filter:0" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name info_leak.timing_attack \
  --cwe CWE-208 --severity high \
  --patterns "time.time:0,time.sleep:0" \
  --output "$OUTPUT_DIR/python-info-leak.yaml"

echo "✅ Generated 10 info_leak rules"

# =============================================================================
# Phase 2: Resource Management (10개)
# =============================================================================
echo ""
echo "📦 Phase 2: Resource Management Rules (10개)"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.file_descriptor_leak \
  --cwe CWE-772 --severity medium \
  --patterns "open:0,io.open:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.memory_leak \
  --cwe CWE-401 --severity high \
  --patterns "array.array:0,bytearray:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.connection_leak \
  --cwe CWE-404 --severity medium \
  --patterns "socket.socket:0,http.client.HTTPConnection:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.dos_regex \
  --cwe CWE-1333 --owasp "A03:2021-Injection" \
  --severity critical \
  --patterns "re.compile:0,re.match:0,re.search:0,re.findall:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.dos_zip \
  --cwe CWE-409 --severity high \
  --patterns "zipfile.ZipFile:0,tarfile.open:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.dos_xml \
  --cwe CWE-776 --severity high \
  --patterns "xml.etree.ElementTree.parse:0,xml.dom.minidom.parse:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.unbounded_allocation \
  --cwe CWE-770 --severity high \
  --patterns "list:0,dict:0,set:0,bytes:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.unbounded_loop \
  --cwe CWE-835 --severity critical \
  --patterns "while,itertools.cycle:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.unbounded_recursion \
  --cwe CWE-674 --severity high \
  --patterns "sys.setrecursionlimit:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name resource.thread_exhaustion \
  --cwe CWE-400 --severity high \
  --patterns "threading.Thread:0,multiprocessing.Process:0" \
  --output "$OUTPUT_DIR/python-resource.yaml"

echo "✅ Generated 10 resource rules"

# =============================================================================
# Phase 3: Cryptography Extended (10개)
# =============================================================================
echo ""
echo "📦 Phase 3: Cryptography Extended Rules (10개)"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name crypto.weak_key_size \
  --cwe CWE-326 --owasp "A02:2021-Cryptographic Failures" \
  --severity high \
  --patterns "RSA.generate:0,DSA.generate:0,Crypto.PublicKey.RSA.generate:0" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name crypto.ecb_mode \
  --cwe CWE-327 --owasp "A02:2021-Cryptographic Failures" \
  --severity critical \
  --patterns "AES.MODE_ECB,Crypto.Cipher.AES.new:1" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name crypto.static_iv \
  --cwe CWE-329 --severity high \
  --patterns "Crypto.Cipher.AES.new:2" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name crypto.no_integrity_check \
  --cwe CWE-354 --severity high \
  --patterns "Crypto.Cipher.AES.MODE_CBC,Crypto.Cipher.AES.MODE_CTR" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name crypto.weak_padding \
  --cwe CWE-326 --severity medium \
  --patterns "Crypto.Util.Padding.pad:1" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name crypto.null_cipher \
  --cwe CWE-327 --severity critical \
  --patterns "ssl.OP_NO_COMPRESSION" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name random.predictable_seed \
  --cwe CWE-330 --severity high \
  --patterns "random.seed:0" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name random.timestamp_seed \
  --cwe CWE-338 --severity medium \
  --patterns "time.time,datetime.now" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category barrier --name crypto.aes_gcm \
  --severity high \
  --patterns "Crypto.Cipher.AES.MODE_GCM,cryptography.hazmat.primitives.ciphers.modes.GCM" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category barrier --name crypto.key_derivation \
  --severity high \
  --patterns "hashlib.pbkdf2_hmac:0,bcrypt.hashpw:0,argon2.hash_password:0" \
  --output "$OUTPUT_DIR/python-crypto-ext.yaml"

echo "✅ Generated 10 crypto rules"

# =============================================================================
# Phase 4: Session & Auth Extended (10개)
# =============================================================================
echo ""
echo "📦 Phase 4: Session & Auth Extended Rules (10개)"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name session.fixation \
  --cwe CWE-384 --owasp "A07:2021-Identification and Authentication Failures" \
  --severity high \
  --patterns "session.session_key,request.session.cycle_key" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name session.no_timeout \
  --cwe CWE-613 --severity medium \
  --patterns "SESSION_COOKIE_AGE,SESSION_EXPIRE_AT_BROWSER_CLOSE" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name session.weak_token \
  --cwe CWE-330 --severity high \
  --patterns "uuid.uuid1:0,uuid.uuid4:0" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name auth.missing_mfa \
  --cwe CWE-308 --severity medium \
  --patterns "login:0,authenticate:0" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name auth.password_plaintext \
  --cwe CWE-256 --owasp "A02:2021-Cryptographic Failures" \
  --severity critical \
  --patterns "password,passwd,pwd" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name auth.no_rate_limit \
  --cwe CWE-307 --severity high \
  --patterns "login:0,authenticate:0,check_password:0" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name auth.default_credentials \
  --cwe CWE-798 --severity critical \
  --patterns "admin,password,12345" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name auth.weak_password_policy \
  --cwe CWE-521 --severity medium \
  --patterns "PASSWORD_MIN_LENGTH,PASSWORD_VALIDATORS" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category barrier --name session.secure_cookie \
  --severity high \
  --patterns "SESSION_COOKIE_SECURE,SESSION_COOKIE_HTTPONLY,SESSION_COOKIE_SAMESITE" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category barrier --name auth.constant_time_compare \
  --severity high \
  --patterns "hmac.compare_digest:0,secrets.compare_digest:0" \
  --output "$OUTPUT_DIR/python-session-auth.yaml"

echo "✅ Generated 10 session/auth rules"

# =============================================================================
# Phase 5: Input Validation Extended (10개)
# =============================================================================
echo ""
echo "📦 Phase 5: Input Validation Extended Rules (10개)"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name validation.missing_length_check \
  --cwe CWE-1284 --severity medium \
  --patterns "len:0,__len__:0" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name validation.missing_type_check \
  --cwe CWE-20 --severity medium \
  --patterns "isinstance:0,type:0" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name validation.missing_range_check \
  --cwe CWE-129 --severity high \
  --patterns "range:0,min:0,max:0" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name validation.missing_format_check \
  --cwe CWE-1286 --severity medium \
  --patterns "re.match:0,re.fullmatch:0" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name validation.integer_overflow \
  --cwe CWE-190 --severity high \
  --patterns "int:0,float:0" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name validation.array_index_negative \
  --cwe CWE-129 --severity high \
  --patterns "__getitem__:0,__setitem__:0" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name validation.null_pointer \
  --cwe CWE-476 --severity high \
  --patterns "None,null" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category sink --name validation.division_by_zero \
  --cwe CWE-369 --severity high \
  --patterns "__truediv__:0,__floordiv__:0,__mod__:0" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category barrier --name validation.length_check \
  --severity medium \
  --patterns "len:0,maxlen:0" \
  --output "$OUTPUT_DIR/python-validation.yaml"

PYTHONPATH=. python scripts/generate_rule.py \
  --category barrier --name validation.whitelist \
  --severity high \
  --patterns "choices,ALLOWED_VALUES" \
  --output "$OUTPUT_DIR/python-validation.yaml"

echo "✅ Generated 10 validation rules"

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "========================================================================"
echo "📊 Generation Summary"
echo "========================================================================"

PYTHONPATH=. python scripts/validate_rules.py \
  "$OUTPUT_DIR"/*.yaml

echo ""
echo "✅ Batch generation complete!"
echo ""
echo "Generated files:"
ls -lh "$OUTPUT_DIR"/*.yaml

echo ""
echo "Next steps:"
echo "  1. Review generated rules: ls $OUTPUT_DIR"
echo "  2. Generate tests: python scripts/generate_test.py --rules $OUTPUT_DIR/*.yaml --output scripts/test_extended.py"
echo "  3. Run tests: python scripts/test_extended.py"
