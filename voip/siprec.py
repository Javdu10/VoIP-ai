"""SIPREC multipart and recording metadata parsing."""

from __future__ import annotations

import dataclasses
from email import policy
from email.parser import BytesParser
from xml.etree import ElementTree

from voip.sdp.messages import SessionDescription
from voip.sdp.types import MediaDescription
from voip.types import ByteSerializableObject

__all__ = [
    "RecordingMetadata",
    "RecordingParticipant",
    "RecordingStream",
    "SIPRECBody",
    "SIPRECBodyPart",
]


def local_name(tag: str) -> str:
    """Return an XML tag name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    """Return the first direct child with *name*, ignoring XML namespaces."""
    return next((item for item in element if local_name(item.tag) == name), None)


def child_text(element: ElementTree.Element, name: str) -> str | None:
    """Return stripped text from the first direct child with *name*."""
    if (item := child(element, name)) is not None and item.text:
        return item.text.strip()
    return None


@dataclasses.dataclass(slots=True)
class RecordingParticipant:
    """A SIPREC participant."""

    id: str
    aor: str | None = None
    name: str | None = None

    @property
    def display_name(self) -> str:
        """Return the best available participant label."""
        return self.name or self.aor or self.id


@dataclasses.dataclass(slots=True)
class RecordingStream:
    """A SIPREC media stream."""

    id: str
    label: str
    participant_id: str | None = None
    direction: str | None = None


@dataclasses.dataclass(slots=True)
class RecordingMetadata(ByteSerializableObject):
    """SIPREC recording metadata."""

    participants: dict[str, RecordingParticipant]
    streams: dict[str, RecordingStream]
    raw: bytes = dataclasses.field(repr=False)
    data_mode: str | None = None

    @classmethod
    def parse(cls, data: bytes | str) -> "RecordingMetadata":
        raw = data.encode() if isinstance(data, str) else data
        root = ElementTree.fromstring(raw)
        participants = cls.parse_participants(root)
        streams = cls.parse_streams(root)
        cls.apply_stream_associations(root, streams)
        return cls(
            participants=participants,
            streams=streams,
            raw=raw,
            data_mode=child_text(root, "datamode"),
        )

    @staticmethod
    def parse_participants(
        root: ElementTree.Element,
    ) -> dict[str, RecordingParticipant]:
        participants = {}
        for item in root.iter():
            if local_name(item.tag) != "participant":
                continue
            participant_id = item.attrib.get("participant_id") or item.attrib.get("id")
            if participant_id is None:
                continue
            name_id = child(item, "nameID")
            participants[participant_id] = RecordingParticipant(
                id=participant_id,
                aor=name_id.attrib.get("aor") if name_id is not None else None,
                name=child_text(name_id, "name") if name_id is not None else None,
            )
        return participants

    @staticmethod
    def parse_streams(root: ElementTree.Element) -> dict[str, RecordingStream]:
        streams = {}
        for item in root.iter():
            if local_name(item.tag) != "stream":
                continue
            stream_id = item.attrib.get("stream_id") or item.attrib.get("id")
            label = child_text(item, "label")
            if stream_id is not None and label is not None:
                streams[stream_id] = RecordingStream(id=stream_id, label=label)
        return streams

    @staticmethod
    def apply_stream_associations(
        root: ElementTree.Element, streams: dict[str, RecordingStream]
    ) -> None:
        for item in root.iter():
            if local_name(item.tag) != "participantstreamassoc":
                continue
            direction = None
            stream_id = item.attrib.get("stream_id")
            for part in item:
                if local_name(part.tag) in {"send", "recv"}:
                    direction = local_name(part.tag)
                    if part.text and part.text.strip():
                        stream_id = part.text.strip()
                    break
            if stream_id is None:
                continue
            if (stream := streams.get(stream_id)) is not None:
                stream.participant_id = item.attrib.get("participant_id")
                stream.direction = direction

    @property
    def streams_by_label(self) -> dict[str, RecordingStream]:
        """Return streams keyed by SDP label."""
        return {stream.label: stream for stream in self.streams.values()}

    def participant_for_label(self, label: str) -> RecordingParticipant | None:
        """Return the participant associated with an SDP label."""
        stream = self.streams_by_label.get(label)
        if stream is None or stream.participant_id is None:
            return None
        return self.participants.get(stream.participant_id)

    def transcript_prefix(self, label: str) -> str:
        """Return a transcript prefix for an SDP label."""
        participant = self.participant_for_label(label)
        name = participant.display_name if participant is not None else f"stream {label}"
        return f"{name} said: "

    def prefix_transcription(self, label: str, text: str) -> str:
        """Prefix a transcription with SIPREC participant metadata."""
        return f"{self.transcript_prefix(label)}{text}"

    def __bytes__(self) -> bytes:
        return self.raw


@dataclasses.dataclass(slots=True)
class SIPRECBodyPart:
    """One parsed SIPREC multipart body part."""

    content_type: str
    content: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(slots=True)
class SIPRECBody(ByteSerializableObject):
    """A SIPREC multipart body with SDP and recording metadata parts."""

    parts: list[SIPRECBodyPart]
    raw: bytes = dataclasses.field(repr=False)
    sdp: SessionDescription | None = None
    metadata: RecordingMetadata | None = None

    @classmethod
    def parse(cls, content_type: str, data: bytes) -> "SIPRECBody":
        message = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: "
            + content_type.encode()
            + b"\r\nMIME-Version: 1.0\r\n\r\n"
            + data
        )
        parts = []
        sdp = None
        metadata = None
        for part in message.iter_parts():
            payload = part.get_payload(decode=True) or b""
            body_part = SIPRECBodyPart(part.get_content_type(), payload)
            parts.append(body_part)
            match body_part.content_type:
                case "application/sdp":
                    sdp = SessionDescription.parse(payload)
                case "application/rs-metadata+xml":
                    metadata = RecordingMetadata.parse(payload)
        return cls(parts=parts, raw=data, sdp=sdp, metadata=metadata)

    @property
    def connection(self):
        """Return the session-level SDP connection, when present."""
        return self.sdp.connection if self.sdp is not None else None

    @property
    def media(self) -> list[MediaDescription]:
        """Return SDP media descriptions.

        This lets existing SIP INVITE handling consume SIPREC multipart bodies
        like regular SDP bodies.
        """
        return self.sdp.media if self.sdp is not None else []

    @property
    def media_by_label(self) -> dict[str, MediaDescription]:
        """Return SDP media descriptions keyed by `a=label`."""
        return {
            attr.value: media
            for media in self.media
            for attr in media.attributes
            if attr.name == "label" and attr.value is not None
        }

    def __bytes__(self) -> bytes:
        return self.raw
