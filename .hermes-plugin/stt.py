"""Hermes STT configuration bridge for VoIP transcription."""

from faster_whisper import WhisperModel


def resolve_voip_stt_model_from_hermes_config(config: dict) -> WhisperModel:
    """Create the VoIP Whisper model from Hermes local STT settings."""
    stt = config.get("stt", {})
    provider = stt.get("provider", "local")

    if provider != "local":
        raise RuntimeError(
            "sip-voip-gateway currently supports Hermes local faster-whisper STT only"
        )

    local_config = stt.get("local", {}) or stt.get("faster_whisper", {})
    model_name = local_config.get("model") or stt.get("model") or "base"
    device = local_config.get("device") or "auto"
    compute_type = local_config.get("compute_type") or "default"

    kwargs = {"device": device}
    if compute_type != "default":
        kwargs["compute_type"] = compute_type

    return WhisperModel(model_name, **kwargs)
