# 환경변수를 한곳에서 관리

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    DATABASE_URL: str

    # 직원 대시보드가 읽는 시뮬레이션 결과 폴더 (DB에 쓰지 않음)
    SIMULATION_RESULTS_DIR: Path = (
        BASE_DIR / "backend" / "module" / "results" / "four_scenario_v34"
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()