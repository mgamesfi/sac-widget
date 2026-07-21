from extractor.rfc_connection import RfcCallError, RfcConnection


def _conn_with_fake_call(responses):
    conn = RfcConnection(ashost="bw-app.cliente.com", sysnr="00", client="100", user="CPIC_TECH", password="x")
    conn._conn = object()  # evita reconectar via pyrfc real dentro de test_connection()

    def fake_call(function_name, **params):
        if function_name in responses:
            outcome = responses[function_name]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        raise AssertionError(f"sem resposta configurada para: {function_name}")

    conn.call = fake_call  # type: ignore[method-assign]
    return conn


def test_test_connection_ok_when_rfc_ping_succeeds():
    conn = _conn_with_fake_call({"RFC_PING": {}})
    info = conn.test_connection()
    assert info["ok"] is True
    assert info["host"] == "bw-app.cliente.com"
    assert info["client"] == "100"


def test_test_connection_reports_failure_when_ping_fails():
    conn = _conn_with_fake_call({"RFC_PING": RfcCallError("sem autorização S_RFC")})
    info = conn.test_connection()
    assert info["ok"] is False
    assert "S_RFC" in info["error"]


def test_call_raises_rfc_call_error_when_not_connected():
    conn = RfcConnection(ashost="h", sysnr="00", client="100", user="u", password="p")
    try:
        conn.call("RFC_PING")
        assert False, "esperava erro por conexão não estabelecida"
    except Exception as exc:
        assert "não estabelecida" in str(exc)
