"""Configuración centralizada del agente — cargada desde variables de entorno / .env."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Agente ---
    agent_mode: str = Field(default="SIMULATION", description="SIMULATION | LIVE")
    initial_capital_usd: float = Field(default=300.0)
    cycle_interval_minutes: int = Field(default=10)
    position_check_seconds: int = Field(default=15, description="Segundos entre chequeos de TP/SL")

    # --- Base de Datos ---
    database_url: str = Field(
        default="postgresql+asyncpg://agent:agent_secret_pw@localhost:5432/agente_mercado"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    # --- Crypto Exchanges ---
    binance_api_key: str = Field(default="")
    binance_api_secret: str = Field(default="")
    binance_testnet: bool = Field(default=True)
    bybit_api_key: str = Field(default="")
    bybit_api_secret: str = Field(default="")

    # --- Datos Externos ---
    coingecko_api_key: str = Field(default="")
    etherscan_api_key: str = Field(default="")
    gnews_api_key: str = Field(default="")
    newsapi_key: str = Field(default="")
    reddit_client_id: str = Field(default="")
    reddit_client_secret: str = Field(default="")

    # --- LLM ---
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3.1-pro-preview")
    gemini_fallback_model: str = Field(default="gemini-3.1-flash-lite-preview")
    gemini_temperature: float = Field(default=0.2)
    gemini_max_output_tokens: int = Field(default=16384)
    llm_batch_size: int = Field(default=15, description="Pares por llamada LLM")
    llm_max_rpd: int = Field(default=1500, description="Max requests per day (Gemini pagado)")
    llm_max_rpm: int = Field(default=30, description="Max requests per minute (Gemini pagado)")
    deep_analysis_interval: int = Field(default=12, description="Cada N ciclos usar modelo Pro (1 = siempre Pro)")

    # --- Notificaciones ---
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    # --- Seguridad API REST ---
    jwt_secret_key: str = Field(default="change_this_to_a_random_secret_key_at_least_32_chars")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=1440)  # 24 horas

    # --- Risk Management ---
    fractional_kelly: float = Field(default=0.50, description="Fracción del Kelly óptimo")
    max_per_trade_pct: float = Field(default=0.06, description="6% máx por operación")
    max_daily_loss_pct: float = Field(default=0.10, description="10% pérdida diaria máxima")
    max_weekly_loss_pct: float = Field(default=0.20, description="20% pérdida semanal máxima")
    max_drawdown_pct: float = Field(default=0.25, description="25% drawdown máximo desde peak")
    max_concurrent_positions: int = Field(default=20)
    min_volume_usd: float = Field(default=50_000, description="Volumen 24h mínimo del par")
    deviation_threshold: float = Field(default=0.015, description="1.5% desviación mínima")
    min_confidence: float = Field(default=0.45, description="Confianza mínima del LLM")
    min_trade_size_usd: float = Field(default=2.0, description="Mínimo $2 por trade")

    # --- Pay-or-die ---
    survival_warning_days: int = Field(default=7)
    survival_shutdown_days: int = Field(default=14)


settings = Settings()
