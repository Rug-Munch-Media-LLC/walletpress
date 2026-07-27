"""Tests: Standardized API response helpers."""

import os
import tempfile

os.environ["WP_VAULT_PASSWORD"] = "test-response"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_resp_")

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.response import (
    success,
    error,
    created,
    no_content,
    bad_request,
    unauthorized,
    forbidden,
    not_found,
    conflict,
    too_many_requests,
    server_error,
)


def test_success_response():
    resp = success({"id": "abc", "name": "test"})
    assert resp.status_code == 200
    body = resp.body
    assert b'"data"' in body
    assert b'"name"' in body
    assert b'"meta"' in body


def test_success_with_meta():
    resp = success([], meta={"total": 42, "page": 1})
    assert resp.status_code == 200
    body = resp.body
    assert b'"total"' in body
    assert b'"page"' in body


def test_created_response():
    resp = created({"id": "new"})
    assert resp.status_code == 201


def test_no_content_response():
    resp = no_content()
    assert resp.status_code == 204
    assert resp.body == b"null" or resp.body == b""


def test_error_basic():
    resp = error("bad_request", "Invalid input")
    assert resp.status_code == 400
    body = resp.body
    assert b'"detail"' in body
    assert b'"Invalid input"' in body
    assert b'"code"' in body
    assert b'"request_id"' in body
    assert b'"timestamp"' in body


def test_error_with_details():
    resp = error("validation_error", "Field errors", details={"field": "must be positive"})
    body = resp.body
    assert b'"errors"' in body


def test_error_with_instance():
    resp = error("not_found", "Missing", instance="/api/v1/wallets/xyz")
    body = resp.body
    assert b'"instance"' in body


def test_error_type_conversion():
    resp = error("auth.invalid_token", "Bad token")
    body = resp.body.decode()
    assert "/errors/auth/invalid_token" in body


def test_bad_request():
    resp = bad_request("Invalid parameter")
    assert resp.status_code == 400


def test_unauthorized():
    resp = unauthorized()
    assert resp.status_code == 401


def test_forbidden():
    resp = forbidden()
    assert resp.status_code == 403


def test_not_found():
    resp = not_found()
    assert resp.status_code == 404


def test_conflict():
    resp = conflict("Already exists")
    assert resp.status_code == 409


def test_too_many_requests():
    resp = too_many_requests()
    assert resp.status_code == 429


def test_server_error():
    resp = server_error()
    assert resp.status_code == 500


def test_internal_error_type():
    resp = error("internal_error", "Server error")
    body = resp.body.decode()
    assert '"type": "about:blank"' in body
