"""
Integration Test: Role Detection with PythonIRGenerator

실제 Generator와 통합 테스트.
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile


def test_generator_role_detection_enabled():
    """역할 감지 활성화"""

    code = """
class UserService:
    def create_user(self): pass

class UserRepository:
    def save(self): pass

@app.route('/api/users')
def get_users():
    return []

def test_login():
    assert True
"""

    source = SourceFile(file_path="test.py", content=code, language="python")
    generator = _PythonIRGenerator(repo_id="test", enable_role_detection=True)
    ir_doc = generator.generate(source, snapshot_id="test")

    nodes_by_name = {n.name: n for n in ir_doc.nodes if n.name}

    # 검증
    assert nodes_by_name["UserService"].role == "service"
    assert nodes_by_name["UserRepository"].role == "repository"
    assert nodes_by_name["get_users"].role == "route"
    assert nodes_by_name["test_login"].role == "test"
    assert nodes_by_name["create_user"].role == "factory"


def test_generator_role_detection_disabled():
    """역할 감지 비활성화"""

    code = "class UserService:\n    pass"
    source = SourceFile(file_path="test.py", content=code, language="python")

    generator = _PythonIRGenerator(repo_id="test", enable_role_detection=False)
    ir_doc = generator.generate(source, snapshot_id="test")

    nodes_by_name = {n.name: n for n in ir_doc.nodes if n.name}

    # role이 None이어야 함
    assert nodes_by_name["UserService"].role is None


def test_real_world_django():
    """Django 프로젝트 시나리오"""

    code = """
from django.db import models

class User(models.Model):
    email = models.EmailField()

class UserRepository:
    def save(self, user):
        user.save()
"""

    source = SourceFile(file_path="models.py", content=code, language="python")
    generator = _PythonIRGenerator(repo_id="test", enable_role_detection=True)
    ir_doc = generator.generate(source, snapshot_id="test")

    nodes_by_name = {n.name: n for n in ir_doc.nodes if n.name}

    assert nodes_by_name["User"].role == "entity"
    assert nodes_by_name["UserRepository"].role == "repository"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
