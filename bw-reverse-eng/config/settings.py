"""Configuração da aplicação via .env / variáveis de ambiente (RF01, NFR Segurança).

Nenhuma credencial deve ser hardcoded. Todos os valores sensíveis (host, usuário,
senha/certificado) vêm de variáveis de ambiente ou de um arquivo `.env` local
(nunca versionado — ver `.gitignore`).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HanaSettings(BaseSettings):
    """Parâmetros de conexão ao HANA subjacente ao BW."""

    model_config = SettingsConfigDict(
        env_prefix="HANA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(..., description="Hostname/IP do HANA, alcançável via VPN")
    port: int = Field(30015, description="Porta SQL do HANA (tipicamente 3<inst>15)")
    user: str = Field(..., description="Usuário técnico com SELECT em SYS/_SYS_BI/BW")
    password: str | None = Field(None, description="Senha do usuário técnico")
    client_cert: Path | None = Field(None, description="Certificado cliente, alternativa à senha")
    client_key: Path | None = Field(None, description="Chave privada do certificado cliente")
    encrypt: bool = Field(True, description="Força TLS na conexão (recomendado via VPN)")
    validate_cert: bool = Field(True, description="Valida certificado do servidor HANA")
    connect_timeout_s: int = Field(30, description="Timeout de conexão em segundos")

    @model_validator(mode="after")
    def _require_credential(self) -> "HanaSettings":
        if not self.password and not (self.client_cert and self.client_key):
            raise ValueError(
                "Informe HANA_PASSWORD ou (HANA_CLIENT_CERT e HANA_CLIENT_KEY) para autenticação."
            )
        return self


class AppSettings(BaseSettings):
    """Configurações gerais da aplicação (extração, filtros, saída)."""

    model_config = SettingsConfigDict(
        env_prefix="BWREVENG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_language: str = Field("EN", description="Idioma preferencial para textos (RSD*T)")
    default_output_dir: Path = Field(Path("./data"), description="Diretório base de snapshots")
    log_level: str = Field("INFO", description="Nível de log (DEBUG/INFO/WARNING/ERROR)")
    composite_provider_source_threshold: int = Field(
        5, description="Nº de fontes acima do qual um CompositeProvider é reportado como complexo"
    )
    transformation_rule_threshold: int = Field(
        10, description="Nº de regras acima do qual uma Transformação é reportada como complexa"
    )


def load_hana_settings() -> HanaSettings:
    return HanaSettings()


def load_app_settings() -> AppSettings:
    return AppSettings()
