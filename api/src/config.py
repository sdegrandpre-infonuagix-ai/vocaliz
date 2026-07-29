from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://salon:password@localhost:5432/salon"
    jwt_secret: str  # required — set JWT_SECRET env var; no default to prevent forged-token deploys
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    aws_region: str = "ca-central-1"
    sns_sender_id: str = "Salon"
    otp_expiry_minutes: int = 10
    otp_max_attempts: int = 5

    # LiveKit Cloud
    livekit_url: str = "wss://your-project.livekit.cloud"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str  # required — set LIVEKIT_API_SECRET env var

    # Session settings
    livekit_room_max_participants: int = 3  # host + guest + agent
    livekit_room_empty_timeout: int = 300   # 5 min (auto-close if no one joins)

    # Invitation join links sent via SMS to non-registered contacts
    salon_web_base_url: str = "https://salon.app"


settings = Settings()
