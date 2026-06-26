from voip.sip import messages
from voip.siprec import SIPRECBody


RFC_RECORDING_METADATA = b"""--kamailio-siprec-auto
Content-Type: application/sdp

v=0
o=sipp 1 1 IN IP4 127.0.0.1
s=-
t=0 0
m=audio 38234 RTP/AVP 8
c=IN IP4 127.0.0.1
a=label:0
a=rtpmap:8 PCMA/8000
a=sendonly
m=audio 37070 RTP/AVP 8
c=IN IP4 127.0.0.1
a=label:1
a=rtpmap:8 PCMA/8000
a=sendonly

--kamailio-siprec-auto
Content-Type: application/rs-metadata+xml

<recording xmlns="urn:ietf:params:xml:ns:recording:1">
  <datamode>complete</datamode>
  <session session_id="1-12756@127.0.0.1"/>
  <participant participant_id="1-12756@127.0.0.1-caller">
    <nameID aor="sip:sipp@127.0.0.1"/>
  </participant>
  <participant participant_id="1-12756@127.0.0.1-callee">
    <nameID aor="sip:123@127.0.0.1"/>
  </participant>
  <stream stream_id="stream-0" session_id="1-12756@127.0.0.1">
    <label>0</label>
  </stream>
  <stream stream_id="stream-1" session_id="1-12756@127.0.0.1">
    <label>1</label>
  </stream>
  <participantstreamassoc participant_id="1-12756@127.0.0.1-caller">
    <send>stream-0</send>
  </participantstreamassoc>
  <participantstreamassoc participant_id="1-12756@127.0.0.1-callee">
    <recv>stream-1</recv>
  </participantstreamassoc>
</recording>

--kamailio-siprec-auto--
"""


def test_siprecbody_parse__rfc_recording_metadata():
    """Parse RFC-compliant SIPREC SDP and XML metadata."""
    result = SIPRECBody.parse(
        "multipart/mixed; boundary=kamailio-siprec-auto", RFC_RECORDING_METADATA
    )

    assert result.media_by_label["0"].port == 38234
    assert result.media_by_label["1"].port == 37070
    assert result.metadata is not None
    assert result.metadata.data_mode == "complete"
    assert result.metadata.participant_for_label("0").aor == "sip:sipp@127.0.0.1"
    assert result.metadata.participant_for_label("1").aor == "sip:123@127.0.0.1"


def test_message_parse__request__with_siprec_multipart_body():
    """Parse a SIP request with a SIPREC multipart body."""
    result = messages.Message.parse(
        b"INVITE sip:recorder@example.com SIP/2.0\r\n"
        b"Content-Type: multipart/mixed; boundary=kamailio-siprec-auto\r\n\r\n"
        + RFC_RECORDING_METADATA
    )

    assert isinstance(result.body, SIPRECBody)
    assert result.body.media_by_label["0"].port == 38234
    assert result.body.metadata is not None
    assert result.body.metadata.data_mode == "complete"


def test_recordingmetadata_prefix_transcription__with_aor():
    """Prefix transcription text with participant AoR."""
    result = SIPRECBody.parse(
        "multipart/mixed; boundary=kamailio-siprec-auto", RFC_RECORDING_METADATA
    )

    assert (
        result.metadata.prefix_transcription("1", "hello")
        == "sip:123@127.0.0.1 said: hello"
    )
