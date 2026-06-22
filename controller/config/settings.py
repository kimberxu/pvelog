from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    db_url: str = "sqlite+aiosqlite:///./pve_aiops.db"
    psk_secret: str = "YOUR_SECURE_PSK_HERE"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = "YOUR_API_KEY_HERE"  # 默认 key
    llm_model: str = "deepseek-v3.2"

    # SMTP Config
    smtp_server: str = "smtp.example.com"
    smtp_port: int = 465
    smtp_username: str = "your_email@example.com"
    smtp_password: str = "your_email_password"
    email_from: str = "your_email@example.com"
    alert_email_to: str = "admin@example.com"

    class Config:
        env_file = ".env"

settings = Settings()
