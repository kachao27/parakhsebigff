from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # WhatsApp Cloud API
    wa_token: str = ""
    wa_phone_number_id: str = ""
    wa_verify_token: str = "parakh-verify"

    # Anthropic (L2 paraphrase->rule mapping, OCR assist)
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-8"

    # App
    database_path: str = "data/parakh.db"
    base_url: str = "http://localhost:8000"
    campaign_threshold: int = 3
    campaign_window_hours: int = 24

    # L3 memory: max Hamming distance (of 64 bits) for a pHash match
    phash_hamming_threshold: int = 10

    class Config:
        env_file = ".env"
        extra = "ignore"  # allow unrelated vars (SSL_CERT_FILE etc.) in .env


settings = Settings()
