"""Tests for MqttClient._configure_tls TLS gating (issue #94)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from meter.mqtt.client import MqttClient


def _make_client(mqtt_cfg: dict) -> MagicMock:
    """Instantiate MqttClient with paho Client patched; return the mock client."""
    cfg = {"host": "mqtt.local", **mqtt_cfg}
    with patch("meter.mqtt.client.mqtt.Client") as client_cls:
        client_instance = MagicMock()
        client_cls.return_value = client_instance
        MqttClient(cfg)
    return client_instance


def test_tls_not_enabled_when_key_absent() -> None:
    # Regression for #94: default config has no `tls` key.
    client = _make_client({})
    client.tls_set.assert_not_called()


def test_tls_not_enabled_when_false_with_insecure_false() -> None:
    # The exact #94 trigger: tls_insecure default False must not enable TLS.
    client = _make_client({"tls": False, "tls_insecure": False})
    client.tls_set.assert_not_called()


def test_tls_not_enabled_when_certs_present_but_tls_false() -> None:
    # No fallback: certs alone do not enable TLS.
    client = _make_client({"tls": False, "tls_ca": "/config/ca.pem"})
    client.tls_set.assert_not_called()


def test_tls_enabled_without_certs_uses_system_ca() -> None:
    client = _make_client({"tls": True})
    client.tls_set.assert_called_once_with(
        ca_certs=None, certfile=None, keyfile=None
    )


def test_tls_enabled_with_ca_and_insecure() -> None:
    client = _make_client(
        {
            "tls": True,
            "tls_ca": "/config/ca.pem",
            "tls_cert": "/config/client.pem",
            "tls_key": "/config/client.key",
            "tls_insecure": True,
        }
    )
    client.tls_set.assert_called_once_with(
        ca_certs="/config/ca.pem",
        certfile="/config/client.pem",
        keyfile="/config/client.key",
    )
    client.tls_insecure_set.assert_called_once_with(True)
