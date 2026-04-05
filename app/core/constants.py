from typing import Literal

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
DEFAULT_PAGE_LIMIT: int = 10
MAX_PAGE_LIMIT: int = 100
DEFAULT_PAGE_OFFSET: int = 0

# ---------------------------------------------------------------------------
# JWT / Auth
# ---------------------------------------------------------------------------
JWT_ALGORITHM: str = "HS256"
JWT_SUBJECT_CLAIM: str = "sub"

# ---------------------------------------------------------------------------
# File Upload
# ---------------------------------------------------------------------------
ALLOWED_AUDIO_EXTENSIONS: frozenset[str] = frozenset({".wav", ".mp3", ".m4a"})
AUDIO_CHUNK_SIZE: int = 1024 * 1024  # 1 MB
ALLOWED_CSV_EXTENSION: str = ".csv"

# ---------------------------------------------------------------------------
# AI / Integrations
# ---------------------------------------------------------------------------
GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"
GROQ_TRANSCRIPTION_FORMAT: Literal["json", "text", "verbose_json"] = "text"
GROQ_LLM_MODEL: str = "llama-3.3-70b-versatile"
LLM_MAX_RETRIES: int = 3
LLM_RETRY_MULTIPLIER: int = 1
LLM_RETRY_MIN_WAIT: int = 2
LLM_RETRY_MAX_WAIT: int = 10

# ---------------------------------------------------------------------------
# Config Defaults
# ---------------------------------------------------------------------------
DEFAULT_ENVIRONMENT: str = "development"
DEFAULT_AUDIO_MAX_SIZE_MB: int = 25

# ---------------------------------------------------------------------------
# CSV Validation
# ---------------------------------------------------------------------------
CSV_REQUIRED_HEADERS: frozenset[str] = frozenset({"note_type", "session_date", "content"})

# ---------------------------------------------------------------------------
# Error Messages
# ---------------------------------------------------------------------------
ERR_INVALID_TOKEN: str = "Invalid or missing token"
ERR_PROVIDER_NOT_FOUND: str = "Provider not found"
ERR_PATIENT_NOT_FOUND: str = "Patient not found"
ERR_NOTE_NOT_FOUND: str = "Note not found"
ERR_SESSION_NOT_FOUND: str = "Session not found"
ERR_EMAIL_ALREADY_REGISTERED: str = "Email already registered"
ERR_CSV_ONLY: str = "Only .csv files are accepted."
ERR_CSV_MISSING_HEADERS: str = "CSV must contain headers: note_type, session_date, content"
ERR_CSV_NO_DATA: str = "CSV file contains no data rows"
ERR_SESSION_DATE_FUTURE: str = "session_date cannot be in the future"
ERR_LLM_EMPTY_RESPONSE: str = "LLM returned empty response"
