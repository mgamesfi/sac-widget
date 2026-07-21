from extractor.connection import HanaConnection, QueryError


def _conn_with_fake_execute(responses):
    conn = HanaConnection(host="hana.cliente.com", port=30015, user="BWREVENG_TECH", password="x")
    conn._conn = object()  # evita reconectar via hdbcli real dentro de test_connection()

    def fake_execute(sql, params=None):
        for needle, outcome in responses.items():
            if needle in sql:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"sem resposta configurada para: {sql}")

    conn.execute = fake_execute  # type: ignore[method-assign]
    return conn


def test_test_connection_ok_when_all_permissions_present():
    conn = _conn_with_fake_execute(
        {
            "SYS.M_DATABASE": [{"VERSION": "2.00.070.00"}],
            "RSDIOBJ": [{"CNT": 100}],
            "RSDCUBE": [{"CNT": 20}],
            "SYS.VIEWS": [{"CNT": 5}],
        }
    )
    info = conn.test_connection()
    assert info["ok"] is True
    assert info["hana_version"] == "2.00.070.00"
    assert all(info["permissions"].values())


def test_test_connection_reports_missing_permission():
    conn = _conn_with_fake_execute(
        {
            "SYS.M_DATABASE": [{"VERSION": "2.00.070.00"}],
            "RSDIOBJ": [{"CNT": 100}],
            "RSDCUBE": [{"CNT": 20}],
            "SYS.VIEWS": QueryError("sem permissão de leitura"),
        }
    )
    info = conn.test_connection()
    assert info["ok"] is False
    assert info["permissions"]["SYS.VIEWS"] is False
    assert info["permissions"]["RSDIOBJ"] is True
